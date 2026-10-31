"""One typed GitHub request queue for calculations, decisions and R2 transfers."""
import json
import tempfile
from pathlib import Path
from typing import Literal
from uuid import uuid4
from datetime import date
from pydantic import Field,TypeAdapter
from . import pipeline
from .schemas import (StrictModel,Identifier,Source,Research,Integration,Wealth,FinancialFact,ScenarioProfile,ICDecision,EvidenceDocument,Bundle,Security,Snapshot,Transaction,Price,Policy)
from .intake import merge_sources
from .storage import (git,head,committed,read_json,digest,dumps,atomic_write,publish,writer_lock,rollback_pending,require_clean,PublicationError)
from .wealth_requests import gate,error_text,execute as legacy_execute
from .object_storage import StorageRequest,transfer,artifact
from .readiness import workflow_status

Workflow=Literal['portfolio','valuation','update-dividends','timing','macro','watchlist','ic','retirement','cross-asset','daily','event']


class TransferRef(StrictModel):
    receipt_id: Identifier
    artifact_id: str = Field(pattern=r'^[a-f0-9]{64}$')


class TransferDocument(TransferRef):
    document: EvidenceDocument


class PortfolioUpdate(StrictModel):
    securities: list[Security]
    opening: Snapshot
    closing: Snapshot
    transactions: list[Transaction]
    prices: list[Price]
    policy: Policy | None = None


class WorkspacePackage(StrictModel):
    portfolio: PortfolioUpdate | None = None
    sources: list[Source] = Field(default_factory=list)
    market_cutoff: str | None = None
    research: Research | None = None
    integration: Integration | None = None
    wealth: Wealth | None = None
    financials: list[FinancialFact] | None = None
    scenario_profiles: list[ScenarioProfile] | None = None
    decisions: list[ICDecision] | None = None
    originals: list[TransferDocument] = Field(default_factory=list,max_length=50)


class WorkspaceRequest(StrictModel):
    schema_version: Literal['1.0'] = '1.0'
    request_id: Identifier
    operation: Literal['run','simulate','accept-and-run','import','decision','validate','storage.pull','storage.push','storage.status']
    dataset_id: Identifier
    expected_run_id: Identifier
    as_of: date
    authorized_by: str = Field(min_length=1,max_length=200)
    instruction: str = Field(min_length=1,max_length=2000)
    workflows: list[Workflow] = Field(default_factory=lambda:['portfolio'],min_length=1,max_length=11)
    package: WorkspacePackage | None = None
    package_artifact: TransferRef | None = None
    storage: StorageRequest | None = None
    transfer_receipt_id: Identifier | None = None
    archive_paths: list[str] = Field(default_factory=list,max_length=50)


def prepare(root,request):
    state=read_json(root,pipeline.STATE,{})
    if state.get('dataset',{}).get('dataset_id')!=request.dataset_id or state.get('published_run_id')!=request.expected_run_id:
        raise ValueError('dataset or accepted revision mismatch; read the latest committed report')
    if len(set(request.workflows))!=len(request.workflows): raise ValueError('duplicate requested workflow')
    if request.package and request.package_artifact: raise ValueError('choose an inline or transferred package')
    package=request.package
    if request.package_artifact:
        ref=request.package_artifact
        package=WorkspacePackage.model_validate_json(artifact(root,ref.receipt_id,ref.artifact_id))
    if request.operation=='run' and package: raise ValueError('run cannot change inputs; use explicit import or simulation')
    if request.operation in {'accept-and-run','import','decision'} and package is None: raise ValueError('explicit update requires a package')
    if request.operation=='decision' and (not package.decisions or any(getattr(package,k) is not None for k in ('portfolio','research','integration','wealth','financials','scenario_profiles')) or package.originals):
        raise ValueError('decision operation accepts only decisions, sources and cutoff')
    data=json.loads(pipeline.current_input(root));artifacts={}
    if package:
        merge_sources(data,package.sources)
        if package.portfolio:
            data.update(package.portfolio.model_dump(mode='json',exclude_none=True))
        if package.market_cutoff:
            if package.market_cutoff<data['market_cutoff']: raise ValueError('observation cutoff cannot regress')
            data['market_cutoff']=package.market_cutoff
        for key in ('research','integration','wealth','financials','scenario_profiles','decisions'):
            supplied=getattr(package,key)
            if supplied is not None:
                data[key]=[v.model_dump(mode='json') for v in supplied] if isinstance(supplied,list) else supplied.model_dump(mode='json')
        docs=list(data.get('documents',[]))
        for ref in package.originals:
            doc=ref.document
            if ref.artifact_id!=doc.sha256: raise ValueError('original document must match verified transfer hash')
            blob=artifact(root,ref.receipt_id,ref.artifact_id)
            source=next((s for s in data['sources'] if s['source_id']==doc.source_id),None)
            if source is None or source.get('document_sha256',doc.sha256)!=doc.sha256: raise ValueError('original document/source mismatch')
            record=doc.model_dump(mode='json')
            if record not in docs: docs.append(record)
            artifacts['data/evidence/blobs/'+doc.sha256+doc.suffix]=blob
        data['documents']=docs
    bundle=Bundle.model_validate(data)
    if request.as_of<bundle.market_cutoff: raise ValueError('assessment cannot predate observation cutoff')
    return data,artifacts


def execute(root,path,*,local_demo=False,s3=None):
    root=root.resolve();limits=gate(root,local_demo=local_demo)
    relative=path.resolve().relative_to(root).as_posix()
    if Path(relative).parent.as_posix()!='requests/workspace' or not relative.endswith('.json'): raise ValueError('committed workspace request path required')
    rid=Path(relative).stem;TypeAdapter(Identifier).validate_python(rid)
    if rid in {'.','..'}: raise ValueError('invalid request ID')
    with writer_lock(root):
        rollback_pending(root);require_clean(root)
        raw=committed(root,relative)
        if raw is None: raise ValueError('request must be committed')
        marker='reports/requests/'+rid+'.json';old=read_json(root,marker);fingerprint=digest(raw)
        if old:
            if old['request_hash']!=fingerprint: raise ValueError('request ID/content is immutable')
            return {**old,'idempotent':True}
        base=head(root);state=read_json(root,pipeline.STATE,{})
        receipt={'request_id':rid,'request_hash':fingerprint,'base_commit':base,'base_run_id':state.get('published_run_id'),
                 'status':'INVALID','accepted_inputs_changed':False,'errors':[]}
        payloads={};temp=None
        try:
            if len(raw)>limits['max_request_bytes']: raise ValueError('request exceeds configured byte limit')
            additions=git(root,'log','--diff-filter=A','--format=%H','HEAD','--',relative).stdout.decode().splitlines()
            first=git(root,'show',additions[-1]+':'+relative).stdout
            if first!=raw: raise ValueError('submitted request is immutable; use a new ID')
            request=WorkspaceRequest.model_validate_json(raw)
            if request.request_id!=rid: raise ValueError('request ID must match filename')
            if request.dataset_id!=state.get('dataset',{}).get('dataset_id') or request.expected_run_id!=state.get('published_run_id'):
                raise ValueError('dataset or accepted revision mismatch')
            receipt.update(operation=request.operation,instruction=request.instruction,authorized_by=request.authorized_by,as_of=str(request.as_of))
            if request.operation.startswith('storage.'):
                if request.package or request.package_artifact or request.archive_paths: raise ValueError('storage operations cannot update financial inputs')
                if request.operation=='storage.status':
                    if not request.transfer_receipt_id or request.transfer_receipt_id in {'.','..'}: raise ValueError('transfer receipt ID required')
                    result=read_json(root,'reports/storage/'+request.transfer_receipt_id+'.json')
                    if not result: raise ValueError('transfer receipt not found')
                else:
                    if request.storage is None or request.storage.request_id!=rid or request.storage.operation!=request.operation.split('.')[1]:
                        raise ValueError('storage request operation/ID mismatch')
                    result=transfer(root,request.storage,s3=s3)
                    payloads['reports/storage/'+rid+'.json']=dumps({**result,'request_hash':digest(dumps(request.storage.model_dump(mode='json')))})
                receipt.update(status=result['status'],transfer=result,modules={})
            else:
                if request.storage or request.transfer_receipt_id: raise ValueError('calculation cannot contain an unrelated storage operation')
                data,artifacts=prepare(root,request)
                if local_demo and any(not s['source_id'].startswith(('demo.','synthetic.')) for s in data['sources']):
                    raise ValueError('local demo requires synthetic sources')
                temp=tempfile.TemporaryDirectory(prefix='workspace-request-');work=Path(temp.name)/'workspace'
                git(root,'clone','--quiet','--no-hardlinks',str(root),str(work))
                workflow='valuation' if 'valuation' in request.workflows else request.workflows[0]
                result=pipeline.run(work,dumps(data),workflow=workflow,as_of=request.as_of,artifacts=artifacts,
                    max_units=limits['max_work_units'],max_seconds=limits['max_seconds'])
                if result['status']=='FAILED': raise ValueError(result.get('error') or 'calculation failed')
                calculated=read_json(work,pipeline.STATE);pipeline.validate(work)
                statuses={m:workflow_status(calculated,m) for m in request.workflows}
                receipt.update(status='COMPLETE' if all(s=='COMPLETE' for s in statuses.values()) else 'PARTIAL',modules=statuses,
                               result_run_id=result['run_id'],source_code_hash=result['code_hash'],
                               missing_inputs=calculated.get('data_gaps',[]),deferred_work=calculated.get('deferred_work',[]))
                if request.operation in {'run','accept-and-run','import','decision'}:
                    for name in git(work,'diff','--name-only',base,'HEAD').stdout.decode().splitlines():
                        blob=committed(work,name)
                        if blob is None: raise ValueError('request cannot delete canonical files')
                        payloads[name]=blob
                    receipt['accepted_inputs_changed']=request.operation!='run' and Bundle.model_validate(data).model_dump(mode='json')!=Bundle.model_validate_json(pipeline.current_input(root)).model_dump(mode='json')
                if request.operation!='validate':
                    prefix='reports/requests/'+rid+'/'
                    payloads[prefix+'Investment_Workspace.xlsx']=committed(work,pipeline.WORKBOOK)
                    payloads[prefix+'snapshot.json']=dumps(calculated)
                    receipt['outputs']={'workbook':prefix+'Investment_Workspace.xlsx','snapshot':prefix+'snapshot.json'}
                if request.archive_paths:
                    if request.operation=='validate': raise ValueError('validate does not upload archives')
                    try:
                        archive=transfer(work,StorageRequest(request_id=rid,operation='push',run_id=result['run_id'],paths=request.archive_paths),s3=s3)
                        receipt['archive']=archive;payloads['reports/storage/'+rid+'.json']=dumps(archive)
                    except (ValueError,OSError) as exc:
                        receipt['archive']={'status':'FAILED','errors':[str(exc)]};receipt['status']='PARTIAL'
        except (ValueError,OSError,TypeError,KeyError,PublicationError) as exc:
            payloads={};receipt.update(status='INVALID',errors=[error_text(exc)],accepted_inputs_changed=False)
        finally:
            if temp: temp.cleanup()
        payloads[marker]=dumps(receipt)
        payloads['reports/requests/'+rid+'.md']=('# Workspace request '+rid+'\n\nStatus: '+receipt['status']+'\n\n'+
            '\n'.join('- '+m+': '+s for m,s in receipt.get('modules',{}).items())+'\n\nRead the adjacent JSON receipt for missing inputs, evidence, transfers and output links.\n').encode()
        stage=root/'.runtime/staging'/('workspace-'+uuid4().hex)
        for name,blob in payloads.items(): atomic_write(stage/name,blob)
        commit=publish(root,stage,list(payloads),'workspace-'+rid,receipt['status'],commit_marker=marker)
        return {**receipt,'publication_commit':commit}


def pending(root,*,local_demo=False,push=False,s3=None):
    limits=gate(root,local_demo=local_demo)
    branch=git(root,'symbolic-ref','--short','HEAD').stdout.decode().strip()
    if push:
        if local_demo or not limits.get('auto_push'): raise ValueError('private publication authorization required')
        remote=git(root,'ls-remote','origin','refs/heads/'+branch,check=False)
        if remote.returncode or not remote.stdout or remote.stdout.decode().split()[0]!=head(root): raise PublicationError('remote HEAD differs; use a fresh checkout')
    paths=git(root,'ls-tree','-r','--name-only','HEAD','--','requests/wealth','requests/workspace').stdout.decode().splitlines()
    results=[]
    for name in sorted(p for p in paths if p.endswith('.json')):
        try:
            fn=legacy_execute if name.startswith('requests/wealth/') else execute
            results.append(fn(root,root/name,local_demo=local_demo,**({'s3':s3} if fn==execute else {})))
        except ValueError as exc: results.append({'request_id':Path(name).stem,'status':'REJECTED','errors':[str(exc)]})
    publication=pipeline.push(root,'origin',branch) if push else None
    return {'status':'PROCESSED' if all(r['status']=='COMPLETE' for r in results) else 'PARTIAL','requests':results,'publication':publication}
