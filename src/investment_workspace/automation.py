"""Explicitly activated private-runner operation; never acquires market data."""

import os
from datetime import date

from .readiness import committed_report, workflow_status
from .storage import read_json, git, head, PublicationError


def execute(root, workflow, as_of, *, dry_run=False, scheduled=False):
    from . import pipeline
    date.fromisoformat(as_of)
    policy=read_json(root,'config/production.json',{})
    schedules=read_json(root,'config/schedules.json',{})
    state=read_json(root,pipeline.STATE)
    dependencies=[]
    if not policy.get('enabled'):
        dependencies.append('production policy disabled')
    for flag in ('private_repository_verified','manual_parity_verified','auto_push'):
        if policy.get(flag) is not True:
            dependencies.append(flag+' is not explicitly confirmed')
    if not policy.get('publication_authorized_by'):
        dependencies.append('publication authorization missing')
    if scheduled and schedules.get('enabled') is not True:
        dependencies.append('schedules disabled')
    if workflow not in policy.get('allowed_workflows',[]):
        dependencies.append('workflow not enabled')
    if not state or state.get('dataset',{}).get('mode')!='USER_IMPORT' or state.get('dataset',{}).get('dataset_id')!=policy.get('dataset_id'):
        dependencies.append('confirmed production dataset missing or mismatched')
    if policy.get('max_work_units') is None or policy.get('max_seconds') is None:
        dependencies.append('runtime/work budgets missing')
    readiness=committed_report(root)
    if readiness.get('deployment')!='READY':
        dependencies.append('source coverage, methodology or legacy/manual parity incomplete')
    if state:
        observations={m['indicator'] for m in state.get('integration',{}).get('input',{}).get('macro',[])}
        for indicator in sorted(set(policy.get('required_macro_indicators',[]))-observations):
            dependencies.append('missing controlled export: '+indicator)
    if dependencies or dry_run:
        return {'status':'BLOCKED' if dependencies else 'READY_DRY_RUN','dependencies':dependencies,
                'as_of':as_of,'workflow':workflow,'data_acquisition':'CONTROLLED_IMPORTS_ONLY','mutated':False}
    if os.environ.get('GITHUB_ACTIONS')!='true':
        return {'status':'BLOCKED','dependencies':['production execution is restricted to the configured GitHub Actions runner'],'mutated':False}
    branch=git(root,'symbolic-ref','--short','HEAD',check=False).stdout.decode().strip()
    if branch!=policy.get('branch'):
        raise PublicationError('canonical production branch mismatch')
    remote=policy.get('remote','origin')
    expected=git(root,'ls-remote',remote,'refs/heads/'+branch,check=False)
    if expected.returncode or not expected.stdout or expected.stdout.decode().split()[0]!=head(root):
        raise PublicationError('remote canonical HEAD differs; inspect/fetch a fresh checkout and rerun, never merge workbooks')
    result=pipeline.run(root,pipeline.current_input(root),workflow=workflow,as_of=as_of,
                        max_units=policy['max_work_units'],max_seconds=policy['max_seconds'])
    # Authorized publication includes diagnostics/last-good snapshots for incomplete attempts.
    publication=pipeline.push(root,remote,branch)
    accepted=read_json(root,pipeline.STATE)
    complete=workflow_status(accepted,workflow)=='COMPLETE'
    return {'status':result['status'] if complete else 'PARTIAL' if result['status']!='FAILED' else 'FAILED',
            'coverage_status':workflow_status(accepted,workflow),'run_id':result['run_id'],
            'commit':result['commit'],'publication':publication,'as_of':as_of,
            'data_acquisition':'CONTROLLED_IMPORTS_ONLY','mutated':True}
