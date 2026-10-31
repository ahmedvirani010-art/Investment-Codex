"""Transport/activation tests use only a temporary local bare remote, never a service."""

import json
from copy import deepcopy

import pytest

from investment_workspace import automation, pipeline, storage
from investment_workspace.storage import dumps, read_json


@pytest.fixture
def activated(repo,tmp_path,monkeypatch):
    data={'dataset_id':'production','mode':'USER_IMPORT','market_cutoff':'2026-10-09',
       'sources':[{'source_id':'test.user.1','title':'Test user confirmation','publisher':'unit test','effective_date':'2026-10-09',
                   'locator':'test record','evidence_label':'CONFIRMED'}],
       'securities':[],'prices':[],'transactions':[],
       'opening':{'timestamp':'2026-10-08T18:00:00Z','source_id':'test.user.1','cash':'1000','positions':[]},
       'closing':{'timestamp':'2026-10-09T18:00:00Z','source_id':'test.user.1','cash':'1000','positions':[]}}
    pipeline.run(repo,dumps(data))
    branch=storage.git(repo,'symbolic-ref','--short','HEAD').stdout.decode().strip()
    policy={'enabled':True,'private_repository_verified':True,'manual_parity_verified':True,'auto_push':True,
            'dataset_id':'production','branch':branch,'remote':'origin','publication_authorized_by':'synthetic test policy',
            'allowed_workflows':['daily'],'max_work_units':100,'max_seconds':30,'required_macro_indicators':[]}
    (repo/'config').mkdir()
    (repo/'config/production.json').write_bytes(dumps(policy))
    (repo/'config/schedules.json').write_bytes(dumps({'enabled':True}))
    storage.git(repo,'add','config')
    storage.git(repo,'-c','user.name=Test','-c','user.email=test@localhost','commit','-qm','test policy')
    remote=tmp_path/'remote.git'
    storage.git(repo,'init','--bare','-q',str(remote))
    storage.git(repo,'remote','add','origin',str(remote))
    storage.git(repo,'push','-q','origin','HEAD:refs/heads/'+branch)
    monkeypatch.setenv('GITHUB_ACTIONS','true')
    # Separate the runner protocol from the independently tested readiness calculation.
    monkeypatch.setattr(automation,'committed_report',lambda root:{'deployment':'READY'})
    return repo,remote,branch


def test_dry_run_never_mutates_or_pushes(activated):
    repo,remote,branch=activated
    original=storage.head(repo)
    result=automation.execute(repo,'daily','2026-10-10',dry_run=True)
    assert result['status']=='READY_DRY_RUN'
    assert storage.head(repo)==original
    assert storage.git(repo,'ls-remote','origin','refs/heads/'+branch).stdout.decode().split()[0]==original


def test_authorized_partial_run_publishes_diagnostics_and_verifies_sha(activated):
    repo,remote,branch=activated
    original=storage.head(repo)
    result=automation.execute(repo,'daily','2026-10-10',scheduled=True)
    # Portfolio-only input cannot satisfy an integrated daily run.
    assert result['status']=='PARTIAL'
    assert result['coverage_status']=='BLOCKED_INPUT'
    assert result['publication']['status']=='PUSHED'
    assert result['commit']!=original
    assert storage.git(repo,'ls-remote','origin','refs/heads/'+branch).stdout.decode().split()[0]==result['commit']
    assert read_json(repo,pipeline.STATE)['evaluation_as_of']=='2026-10-10'


def test_remote_divergence_stops_before_calculation(activated):
    repo,remote,branch=activated
    storage.git(repo,'-c','user.name=Test','-c','user.email=test@localhost','commit','--allow-empty','-qm','unpublished local change')
    original=storage.head(repo)
    count=len(read_json(repo,pipeline.STATE)['run_log'])
    with pytest.raises(storage.PublicationError,match='remote canonical HEAD differs'):
        automation.execute(repo,'daily','2026-10-10')
    assert storage.head(repo)==original
    assert len(read_json(repo,pipeline.STATE)['run_log'])==count


def test_push_failure_retains_local_calculation(activated,monkeypatch):
    repo,remote,branch=activated
    original=storage.head(repo)
    def failed(*args,**kwargs):
        raise storage.PublicationError('simulated push rejection')
    monkeypatch.setattr(pipeline,'push',failed)
    with pytest.raises(storage.PublicationError,match='push rejection'):
        automation.execute(repo,'daily','2026-10-10')
    assert storage.head(repo)!=original
    assert read_json(repo,pipeline.STATE)['evaluation_as_of']=='2026-10-10'
    assert storage.git(repo,'ls-remote','origin','refs/heads/'+branch).stdout.decode().split()[0]==original


def test_branch_and_runner_mismatch_do_not_start(activated,monkeypatch):
    repo,remote,branch=activated
    original=storage.head(repo)
    monkeypatch.delenv('GITHUB_ACTIONS')
    assert automation.execute(repo,'daily','2026-10-10')['status']=='BLOCKED'
    assert storage.head(repo)==original
