"""Typed chat requests. Calculate in a sandbox; publish through the existing journal."""

import json
import os
import math
import tempfile
from uuid import uuid4
from datetime import date
from pathlib import Path
from typing import Literal

from pydantic import Field, ValidationError

from . import pipeline
from .intake import merge_sources
from .schemas import StrictModel, Identifier, Source, Wealth, Bundle
from .storage import (PublicationError, atomic_write, committed, digest, dumps, git,
                      head, publish, read_json, require_clean, rollback_pending, writer_lock)


class WealthPacket(StrictModel):
    sources: list[Source] = Field(default_factory=list)
    wealth: Wealth
    market_cutoff: date | None = None


class WealthRequest(StrictModel):
    schema_version: Literal['1.0'] = '1.0'
    request_id: Identifier
    operation: Literal['validate', 'simulate', 'accept-and-run']
    dataset_id: Identifier
    expected_run_id: Identifier
    as_of: date
    modules: list[Literal['retirement', 'cross-asset']] = Field(default_factory=lambda: ['retirement','cross-asset'], min_length=1, max_length=2)
    instruction: str = Field(min_length=1, max_length=2000)
    authorized_by: str = Field(min_length=1, max_length=200)
    package: WealthPacket | None = None


def error_text(exc):
    if isinstance(exc, ValidationError):
        return json.dumps(exc.errors(include_input=False, include_url=False), default=str)
    return str(exc)


def candidate(root, request):
    state=read_json(root,pipeline.STATE)
    if not state or state.get('dataset',{}).get('dataset_id')!=request.dataset_id:
        raise ValueError('request dataset does not match accepted dataset')
    if state['published_run_id']!=request.expected_run_id:
        raise ValueError('stale accepted revision; read the current report before requesting again')
    if len(set(request.modules))!=len(request.modules):
        raise ValueError('duplicate requested module')
    data=json.loads(pipeline.current_input(root))
    if request.package:
        merge_sources(data,request.package.sources)
        data['wealth']=request.package.wealth.model_dump(mode='json')
        if request.package.market_cutoff:
            if request.package.market_cutoff.isoformat()<data['market_cutoff']:
                raise ValueError('observation cutoff cannot regress')
            data['market_cutoff']=request.package.market_cutoff.isoformat()
    bundle=Bundle.model_validate(data)
    if bundle.wealth is None:
        raise ValueError('wealth inputs missing; supply a wealth package')
    if request.as_of<bundle.market_cutoff:
        raise ValueError('assessment date precedes observation cutoff')
    return data


def sandbox(root, data, as_of, *, max_units=2000, max_seconds=300, recalculate=False):
    """Caller owns the temporary directory; no canonical files in root are changed."""
    temporary=tempfile.TemporaryDirectory(prefix='wealth-request-')
    work=Path(temporary.name)/'workspace'
    try:
        git(root,'clone','--quiet','--no-hardlinks',str(root),str(work))
        result=pipeline.run(work,dumps(data),workflow='wealth-request',as_of=as_of,
                            max_units=max_units,max_seconds=max_seconds,recalculate=recalculate)
        state=read_json(work,pipeline.STATE)
        if result['status']=='FAILED':
            raise ValueError(result.get('error') or 'wealth validation failed')
        pipeline.validate(work)
        return temporary,work,result,state
    except BaseException:
        temporary.cleanup()
        raise


def preflight(root, packet, *, as_of=None):
    """Read-only to the caller's checkout, including invalid input diagnostics."""
    try:
        parsed=WealthPacket.model_validate(packet)
        data=json.loads(pipeline.current_input(root))
        merge_sources(data,parsed.sources)
        data['wealth']=parsed.wealth.model_dump(mode='json')
        if parsed.market_cutoff:
            if parsed.market_cutoff.isoformat()<data['market_cutoff']:
                raise ValueError('observation cutoff cannot regress')
            data['market_cutoff']=parsed.market_cutoff.isoformat()
        Bundle.model_validate(data)
        temporary,work,result,state=sandbox(root,data,as_of)
        try:
            return summary(state, ['retirement','cross-asset'])
        finally:
            temporary.cleanup()
    except (ValueError,TypeError,KeyError,OSError,PublicationError) as exc:
        return {'status':'INVALID','errors':[error_text(exc)]}


def summary(state, modules):
    wealth=state.get('wealth',{})
    statuses={m:wealth.get('summary',{}).get('retirement_status' if m=='retirement' else 'cross_asset_status','BLOCKED_INPUT') for m in modules}
    return {'status':'COMPLETE' if all(s=='COMPLETE' for s in statuses.values()) else 'PARTIAL',
        'modules':statuses,'wealth':wealth.get('summary',{}),
        'retirement':wealth.get('projections',[]) if 'retirement' in modules else [],
        'cross_asset':wealth.get('cross_asset',[]) if 'cross-asset' in modules else [],
        'comparisons':wealth.get('correlations',[]) if 'cross-asset' in modules else [],
        'missing_inputs':[g for g in state.get('data_gaps',[]) if g.get('field')=='wealth'],
        'deferred_work':state.get('deferred_work',[])}


def markdown(receipt):
    rows=['# Wealth request '+receipt['request_id'],'', 'Status: '+receipt['status'],'',
          'Operation: '+str(receipt.get('operation')), 'Base run: '+str(receipt.get('base_run_id')), '',
          'Calculations are deterministic scenarios; declared assets only. No trades or inferred tax policy.','']
    for module,status in receipt.get('modules',{}).items():
        rows.append('- '+module+': '+status)
    for row in receipt.get('retirement',[]):
        rows.append('- '+str(row.get('scenario'))+': '+str(row.get('status'))+
                    '; ending real PKR '+str(row.get('ending_real_balance'))+
                    '; first shortfall '+str(row.get('first_depletion_date')))
    if receipt.get('errors'):
        rows+=['','Errors:']+['- '+e.replace('\n',' ') for e in receipt['errors']]
    if receipt.get('missing_inputs'):
        rows+=['','Missing inputs:']+['- '+str(g.get('ticker') or 'wealth')+': '+g['reason'] for g in receipt['missing_inputs']]
    rows+=['','Read the adjacent JSON receipt for full assumptions, evidence and dated comparisons.']
    return ('\n'.join(rows)+'\n').encode()


def gate(root, *, local_demo=False):
    state=read_json(root,pipeline.STATE,{})
    if local_demo:
        data=json.loads(pipeline.current_input(root))
        if state.get('dataset',{}).get('mode')!='DEMO' or any(not s['source_id'].startswith(('demo.','synthetic.')) for s in data['sources']):
            raise ValueError('local-demo is restricted to synthetic demo datasets')
        return {'max_work_units':2000,'max_seconds':300,'max_request_bytes':5242880}
    policy=read_json(root,'config/wealth-requests.json',{})
    if (os.environ.get('GITHUB_ACTIONS')!='true' or os.environ.get('WEALTH_PRIVATE_REPOSITORY')!='true'
            or policy.get('enabled') is not True):
        raise ValueError('wealth request processing disabled or repository privacy not verified by Actions')
    if policy.get('repository')!=os.environ.get('GITHUB_REPOSITORY'):
        raise ValueError('configured repository does not match Actions repository')
    if not policy.get('authorized_by'):
        raise ValueError('wealth request policy authorization missing')
    for key in ('max_work_units','max_seconds','max_request_bytes'):
        if type(policy.get(key)) not in (int,float) or not math.isfinite(policy[key]) or policy[key]<=0 or key!='max_seconds' and type(policy[key]) is not int:
            raise ValueError('positive request limits required: '+key)
    return policy


def execute(root, path, *, local_demo=False):
    root=root.resolve()
    # No read of request content until privacy policy is verified.
    policy=gate(root,local_demo=local_demo)
    relative=path.resolve().relative_to(root).as_posix()
    if Path(relative).parent.as_posix()!='requests/wealth' or Path(relative).suffix!='.json':
        raise ValueError('request must be a committed requests/wealth/<id>.json file')
    request_id=Path(relative).stem
    # Validate filename before constructing any result paths.
    from pydantic import TypeAdapter
    TypeAdapter(Identifier).validate_python(request_id)
    if request_id in {'.','..'}:
        raise ValueError('invalid request filename')
    with writer_lock(root):
        rollback_pending(root)
        require_clean(root)
        raw=committed(root,relative)
        if raw is None:
            raise ValueError('request must be committed')
        receipt_path='reports/requests/'+request_id+'.json'
        existing=read_json(root,receipt_path)
        fingerprint=digest(raw)
        if existing:
            if existing['request_hash']!=fingerprint:
                raise ValueError('request ID immutable; submit a new request')
            return {**existing,'idempotent':True,'publication_commit':git(root,'log','-1','--format=%H','--',receipt_path).stdout.decode().strip()}
        additions=git(root,'log','--diff-filter=A','--format=%H','HEAD','--',relative).stdout.decode().splitlines()
        submitted_commit=additions[-1] if additions else head(root)
        original=git(root,'show',submitted_commit+':'+relative).stdout
        base=head(root)
        state=read_json(root,pipeline.STATE,{})
        receipt={'request_id':request_id,'request_hash':fingerprint,'status':'INVALID',
                 'base_commit':base,'base_run_id':state.get('published_run_id'),'dataset':state.get('dataset'),
                 'submitted_commit':submitted_commit,'submitted_hash':digest(original),
                 'result_run_id':None,'accepted_inputs_changed':False,'errors':[]}
        payloads={}
        temporary=None
        try:
            if original!=raw:
                raise ValueError('submitted request contents are immutable; use a new request ID')
            if len(raw)>policy['max_request_bytes']:
                raise ValueError('request exceeds configured byte limit')
            request=WealthRequest.model_validate_json(raw)
            if request.request_id!=request_id:
                raise ValueError('request ID does not match filename')
            receipt.update(operation=request.operation,authorized_by=request.authorized_by,
                           instruction=request.instruction,as_of=request.as_of.isoformat())
            data=candidate(root,request)
            if local_demo and any(not s['source_id'].startswith(('demo.','synthetic.')) for s in data['sources']):
                raise ValueError('local-demo request contains non-synthetic sources')
            temporary,work,result,calculated=sandbox(root,data,request.as_of,
                max_units=policy['max_work_units'],max_seconds=policy['max_seconds'])
            receipt.update(summary(calculated,request.modules))
            receipt['result_run_id']=result['run_id']
            receipt['assumptions']=calculated.get('wealth',{}).get('input',{})
            receipt['result_code_hash']=result['code_hash']
            if request.operation=='accept-and-run':
                changed=git(work,'diff','--name-only',base,'HEAD').stdout.decode().splitlines()
                for name in changed:
                    blob=committed(work,name)
                    if blob is None:
                        raise ValueError('request cannot delete canonical files')
                    payloads[name]=blob
                receipt['accepted_inputs_changed']=(Bundle.model_validate(data).model_dump(mode='json')!=Bundle.model_validate_json(pipeline.current_input(root)).model_dump(mode='json'))
            if request.operation!='validate':
                workbook='reports/requests/'+request_id+'/Investment_Workspace.xlsx'
                payloads[workbook]=committed(work,'workbooks/Investment_Workspace.xlsx')
                snapshot='reports/requests/'+request_id+'/snapshot.json'
                payloads[snapshot]=dumps(calculated)
                receipt['outputs']={'workbook':workbook,'snapshot':snapshot,'report':'reports/requests/'+request_id+'.md'}
        except (ValueError,TypeError,KeyError,OSError,PublicationError) as exc:
            payloads={}
            receipt.update(status='INVALID',errors=[error_text(exc)],accepted_inputs_changed=False,result_run_id=None)
        finally:
            if temporary: temporary.cleanup()
        payloads[receipt_path]=dumps(receipt)
        payloads['reports/requests/'+request_id+'.md']=markdown(receipt)
        stage=root/'.runtime'/'staging'/('wealth-'+request_id+'-'+uuid4().hex)
        for name,blob in payloads.items():
            atomic_write(stage/name,blob)
        commit=publish(root,stage,list(payloads),'wealth-'+request_id,receipt['status'],commit_marker=receipt_path)
        return {**receipt,'publication_commit':commit}


def pending(root, *, local_demo=False, push=False):
    policy=gate(root,local_demo=local_demo)
    remote='origin'
    branch=git(root,'symbolic-ref','--short','HEAD').stdout.decode().strip()
    if push:
        if local_demo or policy.get('auto_push') is not True:
            raise ValueError('normal push requires explicit private request policy authorization')
        expected=git(root,'ls-remote',remote,'refs/heads/'+branch,check=False)
        if expected.returncode or not expected.stdout or expected.stdout.decode().split()[0]!=head(root):
            raise PublicationError('remote HEAD differs; use a fresh canonical checkout, never merge workbooks')
    paths=git(root,'ls-tree','-r','--name-only','HEAD','--','requests/wealth').stdout.decode().splitlines()
    results=[]
    for name in sorted(paths):
        if not name.endswith('.json'): continue
        try:
            results.append(execute(root,root/name,local_demo=local_demo))
        except ValueError as exc:
            results.append({'request_id':Path(name).stem,'status':'REJECTED','errors':[error_text(exc)]})
    publication=pipeline.push(root,remote,branch) if push else None
    return {'status':'PARTIAL' if any(r['status'] not in {'COMPLETE'} for r in results) else 'PROCESSED','requests':results,'publication':publication}
