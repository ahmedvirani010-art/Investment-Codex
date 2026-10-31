"""Bounded R2 transfers: staged inputs and verified immutable output archives."""
import hashlib
import io
import json
import math
import os
import time
from pathlib import PurePosixPath
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field
from .schemas import StrictModel,Identifier
from .storage import committed,read_json,digest,dumps,atomic_write,writer_lock,require_clean,publish,rollback_pending,head


class PullObject(StrictModel):
    key: str = Field(min_length=1)
    sha256: str | None = Field(default=None,pattern=r'^[a-f0-9]{64}$')


class StorageRequest(StrictModel):
    request_id: Identifier
    operation: Literal['pull','push']
    objects: list[PullObject] = Field(default_factory=list)
    run_id: Identifier | None = None
    paths: list[str] = Field(default_factory=list)


def safe_key(key,prefixes):
    p=PurePosixPath(key)
    if key.startswith('/') or '\\' in key or any(part in {'.','..',''} for part in key.split('/')) or not any(key.startswith(x) for x in prefixes):
        raise ValueError('object key outside allowed prefixes or unsafe path')
    return str(p)


def policy(root,*,dry_run=False):
    p=read_json(root,'config/storage.json',{})
    if read_json(root,'data/canonical/portfolio.json',{}).get('dataset',{}).get('mode')=='USER_IMPORT' and not p.get('private_repository_verified'):
        raise ValueError('private financial storage policy has not been verified')
    if not p.get('enabled') and not dry_run: raise ValueError('R2 storage processing is disabled')
    for k in ('max_objects','max_object_bytes','max_total_bytes','max_seconds','attempts'):
        if type(p.get(k)) is not int or p[k]<=0: raise ValueError('positive storage limits required: '+k)
    if not p.get('read_prefixes') or not p.get('archive_prefix') or any(not x.endswith('/') or x.startswith('/') or '..' in x.split('/') for x in p['read_prefixes']+[p['archive_prefix']]):
        raise ValueError('safe read/archive prefixes required')
    return p


def client():
    endpoint=os.environ.get('R2_ENDPOINT_URL','')
    url=urlsplit(endpoint)
    if (url.scheme!='https' or not url.hostname or not url.hostname.endswith('.r2.cloudflarestorage.com')
            or url.username or url.password or url.port not in (None,443) or url.path not in ('','/') or url.query or url.fragment):
        raise ValueError('R2_ENDPOINT_URL must be an HTTPS R2 account endpoint')
    if not all(os.environ.get(k) for k in ('R2_BUCKET','R2_ACCESS_KEY_ID','R2_SECRET_ACCESS_KEY')):
        raise ValueError('R2 runner configuration/credentials incomplete')
    import boto3
    from botocore.config import Config
    return boto3.client('s3',endpoint_url=endpoint,region_name='auto',
        aws_access_key_id=os.environ['R2_ACCESS_KEY_ID'],aws_secret_access_key=os.environ['R2_SECRET_ACCESS_KEY'],
        config=Config(signature_version='s3v4',connect_timeout=5,read_timeout=30,retries={'max_attempts':0}))


def _read(s3,bucket,key,limit,check_time):
    response=s3.get_object(Bucket=bucket,Key=key)
    body=response['Body']
    try:
        if response.get('ContentLength',0)>limit: raise ValueError('object exceeds configured size limit')
        out=bytearray()
        while True:
            check_time();chunk=body.read(min(65536,limit+1-len(out)))
            if not chunk: break
            out.extend(chunk)
            if len(out)>limit: raise ValueError('object exceeds configured size limit')
        return bytes(out)
    finally:
        body.close()


def transfer(root,request,*,dry_run=False,s3=None):
    request=StorageRequest.model_validate(request)
    p=policy(root,dry_run=dry_run)
    if request.request_id in {'.','..'}: raise ValueError('invalid request ID')
    if len(request.objects)>p['max_objects'] or len(request.paths)>p['max_objects']: raise ValueError('transfer object count exceeds limit')
    start=time.monotonic();total=0
    def deadline():
        if time.monotonic()-start>p['max_seconds']: raise ValueError('transfer deadline exhausted')
    def call(fn):
        for attempt in range(p['attempts']):
            deadline()
            try: return fn()
            except ValueError: raise
            except Exception:
                if attempt+1==p['attempts']: raise ValueError('R2 operation failed after bounded retries; verify runner access') from None
                time.sleep(min(2**attempt,4))
    planned=[];payloads={}
    if request.operation=='pull':
        if not request.objects or request.paths or request.run_id: raise ValueError('pull requires exact object keys only')
        for obj in request.objects: planned.append({'key':safe_key(obj.key,p['read_prefixes']),'expected_sha256':obj.sha256})
    else:
        if not request.run_id or not request.paths or request.objects: raise ValueError('push requires a committed run and exact artifact paths')
        manifest=read_json(root,'runs/'+request.run_id+'/manifest.json')
        if not manifest or 'output_hashes' not in manifest: raise ValueError('unknown committed analytical run')
        revision=__import__('subprocess').check_output(['git','-C',str(root),'log','-1','--format=%H','--','runs/'+request.run_id+'/manifest.json']).decode().strip()
        for path in request.paths:
            if path not in manifest['output_hashes']: raise ValueError('archive path must belong to the committed run manifest')
            from .storage import git
            data=git(root,'show',revision+':'+path).stdout
            if digest(data)!=manifest['output_hashes'][path]: raise ValueError('committed archive artifact hash mismatch')
            sha=digest(data);key=p['archive_prefix']+request.run_id+'/'+sha+'/'+PurePosixPath(path).name
            planned.append({'key':key,'sha256':sha,'size':len(data),'path':path,'source_revision':revision})
            payloads[key]=data
    if len({o['key'] for o in planned})!=len(planned): raise ValueError('duplicate transfer key')
    if dry_run: return {'status':'DRY_RUN','operation':request.operation,'objects':planned,'mutated':False}
    s3=s3 or client();bucket=os.environ.get('R2_BUCKET')
    if not bucket: raise ValueError('R2_BUCKET missing')
    outputs=[]
    for item in planned:
        deadline();key=item['key']
        if request.operation=='pull':
            data=call(lambda:_read(s3,bucket,key,min(p['max_object_bytes'],p['max_total_bytes']-total),deadline))
            sha=digest(data)
            if item['expected_sha256'] and sha!=item['expected_sha256']: raise ValueError('download SHA-256 mismatch')
            total+=len(data)
            artifact_id=sha
            atomic_write(root/'.runtime/r2/artifacts'/artifact_id,data)
            outputs.append({**item,'artifact_id':artifact_id,'sha256':sha,'size':len(data),'pinned':bool(item['expected_sha256'])})
        else:
            data=payloads[key];total+=len(data)
            if len(data)>p['max_object_bytes'] or total>p['max_total_bytes']: raise ValueError('upload exceeds configured transfer limits')
            # Content-addressed keys prevent naming collisions. Existing differing bytes are never overwritten.
            try:
                s3.head_object(Bucket=bucket,Key=key)
                exists=True
            except Exception as exc:
                code=getattr(exc,'response',{}).get('Error',{}).get('Code')
                if code not in {'404','NoSuchKey','NotFound'}: raise ValueError('cannot establish archive object existence') from None
                exists=False
            if not exists: call(lambda:s3.put_object(Bucket=bucket,Key=key,Body=data))
            check=call(lambda:_read(s3,bucket,key,p['max_object_bytes'],deadline))
            if digest(check)!=item['sha256']: raise ValueError('archive read-back SHA-256 mismatch')
            outputs.append(item)
    result={'status':'COMPLETE','operation':request.operation,'request_id':request.request_id,'objects':outputs,'bytes':total,
            'run_id':request.run_id,'financial_acceptance':False,'publication_authority':'GIT_RECEIPT'}
    if request.operation=='push':
        content=dumps({'status':'ARTIFACTS_VERIFIED','run_id':request.run_id,'objects':outputs})
        key=p['archive_prefix']+request.run_id+'/'+digest(content)+'/manifest.json'
        call(lambda:s3.put_object(Bucket=bucket,Key=key,Body=content))
        if digest(call(lambda:_read(s3,bucket,key,p['max_object_bytes'],deadline)))!=digest(content): raise ValueError('archive manifest verification failed')
        result['archive_manifest']={'key':key,'sha256':digest(content)}
    return result


def execute(root,request,*,dry_run=False,s3=None):
    request=StorageRequest.model_validate(request)
    if dry_run: return transfer(root,request,dry_run=True)
    relative='reports/storage/'+request.request_id+'.json'
    with writer_lock(root):
        rollback_pending(root);require_clean(root)
        fingerprint=digest(dumps(request.model_dump(mode='json')))
        old=read_json(root,relative)
        if old:
            if old['request_hash']!=fingerprint: raise ValueError('storage request ID is immutable')
            return {**old,'idempotent':True}
        try: result=transfer(root,request,s3=s3)
        except (ValueError,OSError) as exc: result={'status':'FAILED','errors':[str(exc)],'financial_acceptance':False}
        result.update(request_hash=fingerprint,request_id=request.request_id,source_head=head(root))
        stage=root/'.runtime/storage-staging'/request.request_id
        atomic_write(stage/relative,dumps(result))
        sha=publish(root,stage,[relative],'storage-'+request.request_id,result['status'],commit_marker=relative)
        return {**result,'publication_commit':sha}


def artifact(root,receipt_id,artifact_id):
    if receipt_id in {'.','..'} or not __import__('re').fullmatch(r'[A-Za-z0-9_.-]+',receipt_id) or not __import__('re').fullmatch(r'[a-f0-9]{64}',artifact_id):
        raise ValueError('unsafe transfer reference')
    receipt=read_json(root,'reports/storage/'+receipt_id+'.json',{})
    match=next((o for o in receipt.get('objects',[]) if o.get('artifact_id')==artifact_id and o.get('pinned')),None)
    if receipt.get('status')!='COMPLETE' or receipt.get('operation')!='pull' or not match: raise ValueError('only pinned successful pull artifacts may be imported')
    path=root/'.runtime/r2/artifacts'/artifact_id
    if not path.exists():
        transfer(root,StorageRequest(request_id='rehydrate-'+artifact_id[:20],operation='pull',objects=[PullObject(key=match['key'],sha256=artifact_id)]))
    data=path.read_bytes()
    if digest(data)!=artifact_id: raise ValueError('staged artifact hash mismatch; pull it again')
    return data
