"""Phase 4: failed/partial transfers remain visible without repeating financial imports."""
import io
import json
from copy import deepcopy
from pathlib import Path

import pytest
from investment_workspace import pipeline,object_storage,workspace_requests
from investment_workspace.object_storage import StorageRequest,PullObject,artifact,execute as cli_execute
from investment_workspace.workspace_requests import execute
from investment_workspace.storage import dumps,digest,read_json,git,head,committed,PublicationError


class Missing(Exception):response={'Error':{'Code':'NoSuchKey'}}


class FakeS3:
    def __init__(self):self.data={};self.gets=0;self.puts=0;self.head_failures=0;self.put_failures=0;self.fail_manifest=False
    def get_object(self,**kw):
        self.gets+=1
        if kw['Key'] not in self.data:raise Missing()
        value=self.data[kw['Key']];return {'Body':io.BytesIO(value),'ContentLength':len(value)}
    def head_object(self,**kw):
        if self.head_failures:self.head_failures-=1;raise OSError('temporary head failure')
        if kw['Key'] not in self.data:raise Missing()
        return {}
    def put_object(self,**kw):
        if self.put_failures:self.put_failures-=1;raise OSError('temporary upload failure')
        if self.fail_manifest and kw['Key'].endswith('/manifest.json'):raise OSError('manifest upload failure')
        self.puts+=1;self.data[kw['Key']]=kw['Body'];return {}


@pytest.fixture
def ready(repo,monkeypatch):
    full=json.loads(pipeline.fixture_bytes(completion=True));run=pipeline.run(repo,dumps(full));assert run['status']!='FAILED'
    policy=json.loads(Path('config/storage.json').read_bytes());policy['enabled']=True
    (repo/'config').mkdir(exist_ok=True);(repo/'config/storage.json').write_bytes(dumps(policy))
    git(repo,'add','config/storage.json');git(repo,'-c','user.name=Test','-c','user.email=test@localhost','commit','-qm','Synthetic storage policy')
    monkeypatch.setenv('R2_BUCKET','synthetic-only');monkeypatch.setattr(object_storage.time,'sleep',lambda _:None)
    return repo,full,FakeS3()


def request(repo,rid,operation,**kw):
    state=read_json(repo,pipeline.STATE)
    data={'request_id':rid,'operation':operation,'dataset_id':state['dataset']['dataset_id'],
        'expected_run_id':state['published_run_id'],'as_of':'2026-10-09','authorized_by':'Synthetic test',
        'instruction':'Synthetic recovery verification',**kw}
    path=repo/'requests/workspace'/(rid+'.json');path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(dumps(data))
    git(repo,'add',str(path.relative_to(repo)));git(repo,'-c','user.name=Test','-c','user.email=test@localhost','commit','-qm','Synthetic request')
    return path


def pull(repo,rid,objects):return request(repo,rid,'storage.pull',storage={'request_id':rid,'operation':'pull','objects':objects})


def test_failed_workspace_pull_has_durable_status_provenance_and_idempotency(ready):
    repo,_,s3=ready;before=committed(repo,pipeline.STATE)
    path=pull(repo,'missing',[{'key':'approved/missing','sha256':'0'*64}]);revision=head(repo)
    result=execute(repo,path,local_demo=True,s3=s3);saved=read_json(repo,'reports/storage/missing.json')
    assert result['status']=='FAILED' and result['transfer']['status']=='FAILED' and result['modules']=={}
    assert saved['source_head']==revision and saved['source_run_id']==read_json(repo,pipeline.STATE)['published_run_id']
    assert saved['financial_acceptance'] is False and saved['request_hash']
    assert saved['objects'][0]['status']=='FAILED' and saved['objects'][0]['attempts']==3
    assert saved['objects'][0]['expected_sha256']=='0'*64
    assert result['transfer_receipt']=='reports/storage/missing.json'
    assert b'Transfer: FAILED' in committed(repo,'reports/requests/missing.md')
    count=s3.gets;assert execute(repo,path,local_demo=True,s3=s3)['idempotent'];assert s3.gets==count
    status=execute(repo,request(repo,'check','storage.status',transfer_receipt_id='missing'),local_demo=True,s3=s3)
    assert status['status']=='FAILED' and status['transfer']==saved
    assert status['transfer_receipt']=='reports/storage/missing.json'
    assert committed(repo,pipeline.STATE)==before


def test_partial_pull_keeps_object_progress_but_is_not_importable(ready):
    repo,_,s3=ready;s3.data['approved/first']=b'first';sha=digest(b'first')
    objects=[{'key':'approved/first','sha256':sha},{'key':'approved/missing','sha256':'0'*64},{'key':'approved/later'}]
    result=execute(repo,pull(repo,'partial',objects),local_demo=True,s3=s3)['transfer']
    assert result['status']=='FAILED' and result['bytes']==5
    assert [o['status'] for o in result['objects']]==['VERIFIED','FAILED','NOT_ATTEMPTED']
    assert result['objects'][0]['sha256']==sha and result['objects'][0]['size']==5
    assert result['objects'][2]['attempts']==0
    with pytest.raises(ValueError,match='successful'):artifact(repo,'partial',sha)


def test_checksum_failure_records_actual_hash_without_pinning(ready):
    repo,_,s3=ready;s3.data['approved/file']=b'actual'
    result=execute(repo,pull(repo,'checksum',[{'key':'approved/file','sha256':'0'*64}]),local_demo=True,s3=s3)['transfer']
    item=result['objects'][0]
    assert result['status']=='FAILED' and item['verified'] is False
    assert item['observed_sha256']==digest(b'actual') and item['bytes_read']==6
    assert item['size']==6 and 'artifact_id' not in item
    assert not (repo/'.runtime/r2/artifacts'/digest(b'actual')).exists()


def test_stream_interruption_retains_partial_byte_hash_and_closes_body(ready):
    repo,_,_=ready
    class Broken(io.BytesIO):
        def read(self,*args):
            if self.tell():raise OSError('interrupted')
            return super().read(2)
    class Interrupted(FakeS3):
        def __init__(self):super().__init__();self.bodies=[]
        def get_object(self,**kw):
            body=Broken(b'abcd');self.bodies.append(body);return {'Body':body,'ContentLength':4}
    s3=Interrupted();result=execute(repo,pull(repo,'interrupted',[{'key':'approved/file','sha256':digest(b'abcd')}]),local_demo=True,s3=s3)['transfer']
    item=result['objects'][0]
    assert result['status']=='FAILED' and item['bytes_read']==2 and item['response_size']==4
    assert item['observed_sha256']==digest(b'ab') and item['attempts']==3
    assert all(b.closed for b in s3.bodies)


@pytest.mark.parametrize('failure',['put','manifest','readback'])
def test_failed_push_preserves_verified_objects_and_manifest_status(ready,failure):
    repo,_,s3=ready;run=read_json(repo,pipeline.STATE)['published_run_id']
    if failure=='put':s3.put_failures=3
    if failure=='manifest':s3.fail_manifest=True
    if failure=='readback':
        def corrupt(**kw):return {'Body':io.BytesIO(b'wrong'),'ContentLength':5}
        s3.get_object=corrupt
    path=request(repo,'archive','storage.push',storage={'request_id':'archive','operation':'push','run_id':run,'paths':[pipeline.WORKBOOK]})
    result=execute(repo,path,local_demo=True,s3=s3)['transfer'];assert result['status']=='FAILED'
    if failure=='manifest':
        assert result['objects'][0]['status']=='VERIFIED'
        assert result['archive_manifest']['status']=='FAILED' and result['archive_manifest']['verified'] is False
    else:assert result['objects'][0]['status']=='FAILED' and not result['objects'][0]['verified']
    assert read_json(repo,'reports/storage/archive.json')['status']=='FAILED'


def test_head_retries_are_bounded_and_success_is_recorded(ready):
    repo,_,s3=ready;s3.head_failures=2;run=read_json(repo,pipeline.STATE)['published_run_id']
    spec=StorageRequest(request_id='head-retry',operation='push',run_id=run,paths=[pipeline.WORKBOOK])
    result=cli_execute(repo,spec,s3=s3)
    assert result['status']=='COMPLETE' and result['objects'][0]['retries']==2
    assert result['objects'][0]['attempts']==5


def test_accepted_import_survives_archive_failure_then_transfer_only_retry(ready):
    repo,full,s3=ready;s3.put_failures=3
    source=deepcopy(full['sources'][0]);source['source_id']='synthetic.phase4.price'
    portfolio={k:deepcopy(full[k]) for k in ('securities','opening','closing','transactions','prices')}
    for price in portfolio['prices']:price['source_id']=source['source_id']
    portfolio['prices'][0]['close']='126'
    path=request(repo,'accepted','accept-and-run',package={'sources':[source],'portfolio':portfolio},workflows=['valuation'],archive_paths=[pipeline.WORKBOOK])
    result=execute(repo,path,local_demo=True,s3=s3)
    assert result['status']=='PARTIAL' and result['accepted_inputs_changed'],result.get('errors')
    assert result['modules']['valuation']=='COMPLETE' and result['archive']['status']=='FAILED'
    assert read_json(repo,'reports/storage/accepted.json')['status']=='FAILED'
    assert json.loads(pipeline.current_input(repo))['prices'][0]['close']=='126'
    accepted=committed(repo,pipeline.STATE);input_bytes=pipeline.current_input(repo);wb=committed(repo,pipeline.WORKBOOK)
    retry=request(repo,'archive-retry','storage.push',storage={'request_id':'archive-retry','operation':'push','run_id':result['result_run_id'],'paths':[pipeline.WORKBOOK]})
    transfer=execute(repo,retry,local_demo=True,s3=s3)
    assert transfer['status']=='COMPLETE' and not transfer['accepted_inputs_changed']
    assert committed(repo,pipeline.STATE)==accepted and pipeline.current_input(repo)==input_bytes and committed(repo,pipeline.WORKBOOK)==wb
    assert read_json(repo,'reports/storage/accepted.json')['status']=='FAILED'
    assert pipeline.validate(repo)['integrity']=='PASS'


def test_prefix_limits_and_disabled_policy_have_failed_receipts_without_network(ready):
    repo,_,s3=ready
    r=execute(repo,pull(repo,'unsafe',[{'key':'outside/file'}]),local_demo=True,s3=s3)
    assert r['status']=='FAILED' and read_json(repo,'reports/storage/unsafe.json')['status']=='FAILED'
    objects=[{'key':'approved/'+str(i)} for i in range(51)]
    r=execute(repo,pull(repo,'limit',objects),local_demo=True,s3=s3)
    assert r['status']=='FAILED' and 'limit' in r['transfer']['errors'][0]
    p=json.loads((repo/'config/storage.json').read_bytes());p['enabled']=False;(repo/'config/storage.json').write_bytes(dumps(p))
    git(repo,'add','config/storage.json');git(repo,'-c','user.name=Test','-c','user.email=test@localhost','commit','-qm','Disable synthetic policy')
    r=execute(repo,pull(repo,'disabled',[{'key':'approved/file'}]),local_demo=True,s3=s3)
    assert r['status']=='FAILED' and 'disabled' in r['transfer']['errors'][0]
    assert s3.gets==0 and s3.puts==0


def test_storage_receipt_id_collision_never_overwrites_original(ready):
    repo,_,s3=ready;s3.data['approved/file']=b'{}'
    spec=StorageRequest(request_id='collision',operation='pull',objects=[PullObject(key='approved/file',sha256=digest(b'{}'))])
    cli_execute(repo,spec,s3=s3);before=committed(repo,'reports/storage/collision.json')
    result=execute(repo,pull(repo,'collision',[{'key':'approved/other'}]),local_demo=True,s3=s3)
    assert result['status']=='INVALID' and 'immutable' in result['errors'][0]
    assert committed(repo,'reports/storage/collision.json')==before


def test_transfer_publication_retry_never_reimports_financial_data(ready,monkeypatch):
    repo,_,s3=ready;s3.data['approved/file']=b'{}'
    path=pull(repo,'recover',[{'key':'approved/file','sha256':digest(b'{}')}]);before=committed(repo,pipeline.STATE)
    publish=workspace_requests.publish
    def fail(*args,**kwargs):raise PublicationError('synthetic publication interruption')
    monkeypatch.setattr(workspace_requests,'publish',fail)
    with pytest.raises(PublicationError):execute(repo,path,local_demo=True,s3=s3)
    assert committed(repo,pipeline.STATE)==before and read_json(repo,'reports/storage/recover.json') is None
    monkeypatch.setattr(workspace_requests,'publish',publish)
    assert execute(repo,path,local_demo=True,s3=s3)['status']=='COMPLETE'
    assert committed(repo,pipeline.STATE)==before


def test_missing_sdk_is_a_failed_transfer_not_a_lost_receipt(ready,monkeypatch):
    repo,_,_=ready
    def missing():raise ImportError('synthetic missing SDK')
    monkeypatch.setattr(object_storage,'client',missing)
    result=execute(repo,pull(repo,'no-sdk',[{'key':'approved/file'}]),local_demo=True)
    assert result['status']=='FAILED' and 'SDK unavailable' in result['transfer']['errors'][0]
    assert read_json(repo,'reports/storage/no-sdk.json')['status']=='FAILED'


def test_dry_run_has_no_storage_receipt_or_network_access(ready):
    repo,_,s3=ready;before=head(repo)
    spec=StorageRequest(request_id='dry',operation='pull',objects=[PullObject(key='approved/file')])
    result=cli_execute(repo,spec,dry_run=True,s3=s3)
    assert result['status']=='DRY_RUN' and head(repo)==before
    assert read_json(repo,'reports/storage/dry.json') is None and s3.gets==0 and s3.puts==0
