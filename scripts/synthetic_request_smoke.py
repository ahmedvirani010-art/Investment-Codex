"""CI-only fixed-fixture request proof. Never reads or changes real accepted inputs."""
import json
import tempfile
from pathlib import Path

from investment_workspace import pipeline
from investment_workspace.storage import dumps,digest,git,read_json,committed,atomic_write
from investment_workspace.workspace_requests import WorkspaceRequest,execute


def run(root):
    spec=json.loads((root/'requests/smoke/verify-v06.json').read_bytes())
    if set(spec)!={'request_id','fixture_sha256','workflows'}: raise ValueError('synthetic smoke accepts no financial inputs or arbitrary paths')
    raw=pipeline.fixture_bytes(completion=True)
    if digest(raw)!=spec['fixture_sha256']: raise ValueError('synthetic fixture differs from submitted request')
    data=json.loads(raw)
    if data['mode']!='DEMO' or any(not s['source_id'].startswith(('synthetic.','demo.')) for s in data['sources']):
        raise ValueError('synthetic fixture identities required')
    before=committed(root,pipeline.STATE)
    with tempfile.TemporaryDirectory(prefix='github-request-smoke-') as folder:
        work=Path(folder)/'workspace'
        pipeline.run(work,raw)
        seed=read_json(work,pipeline.STATE)
        request=WorkspaceRequest.model_validate({'request_id':spec['request_id'],'operation':'simulate','dataset_id':seed['dataset']['dataset_id'],
           'expected_run_id':seed['published_run_id'],'as_of':data['market_cutoff'],'authorized_by':'Synthetic CI verification',
           'instruction':'Verify immutable fixed-fixture GitHub request routing only','workflows':spec['workflows']})
        path=work/'requests/workspace'/(request.request_id+'.json');atomic_write(path,dumps(request.model_dump(mode='json')))
        git(work,'add','--',str(path.relative_to(work)))
        git(work,'-c','user.name=Synthetic CI','-c','user.email=synthetic-ci@localhost','commit','-qm','create synthetic workspace request')
        receipt=execute(work,path,local_demo=True)
        if receipt['status']!='COMPLETE' or receipt['accepted_inputs_changed']: raise ValueError('synthetic request failed or changed accepted inputs')
        target='reports/smoke/'+request.request_id+'/'
        for key in ('workbook','snapshot'):
            source=receipt['outputs'][key]
            name='Investment_Workspace.xlsx' if key=='workbook' else 'snapshot.json'
            atomic_write(root/target/name,committed(work,source))
            receipt['outputs'][key]=target+name
        receipt.update(synthetic_only=True,canonical_unchanged=committed(root,pipeline.STATE)==before,fixture_sha256=digest(raw),
                       origin_request='requests/smoke/verify-v06.json',expected_run_resolution='DYNAMIC_SYNTHETIC_SEED_ONLY')
        if not receipt['canonical_unchanged']: raise ValueError('canonical data changed during synthetic verification')
        atomic_write(root/target/'receipt.json',dumps(receipt))
        print(json.dumps({'status':receipt['status'],'modules':receipt['modules'],'synthetic_only':True,'canonical_unchanged':True,'receipt':target+'receipt.json'}))


if __name__=='__main__': run(Path.cwd())
