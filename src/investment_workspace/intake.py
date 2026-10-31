"""Controlled evidence packages and spreadsheet migration; never network ingestion."""

import json
from pathlib import Path

from pydantic import Field

from .schemas import (StrictModel, Source, Bundle, Research, Integration, Wealth, FinancialFact,
                      WorkbookMigration, EvidenceDocument, ScenarioProfile, ICDecision)
from .storage import dumps, digest, read_json
from .migration import compare_workbook


class EvidenceFile(StrictModel):
    path: str = Field(min_length=1)
    document: EvidenceDocument


class EvidencePackage(StrictModel):
    schema_version: str = '4.0'
    bundle: Bundle | None = None
    sources: list[Source] = Field(default_factory=list)
    market_cutoff: str | None = None
    research: Research | None = None
    integration: Integration | None = None
    wealth: Wealth | None = None
    financials: list[FinancialFact] | None = None
    scenario_profiles: list[ScenarioProfile] | None = None
    decisions: list[ICDecision] | None = None
    files: list[EvidenceFile] = Field(default_factory=list)


def merge_sources(bundle, sources):
    old={s['source_id']:Source.model_validate(s).model_dump(mode='json',exclude_none=True) for s in bundle['sources']}
    for source in sources:
        payload=source.model_dump(mode='json',exclude_none=True) if hasattr(source,'model_dump') else source
        if payload['source_id'] in old and old[payload['source_id']]!=payload:
            raise ValueError('source ID immutable')
        old[payload['source_id']]=payload
    bundle['sources']=list(old.values())


def import_package(root, path, *, as_of=None):
    from . import pipeline
    raw=path.read_bytes()
    try:
        package=EvidencePackage.model_validate_json(raw)
        if package.schema_version!='4.0':
            raise ValueError('unsupported evidence package version')
        data=package.bundle.model_dump(mode='json',exclude_none=True) if package.bundle else json.loads(pipeline.current_input(root))
        merge_sources(data,package.sources)
        if package.market_cutoff:
            data['market_cutoff']=package.market_cutoff
        for key in ('research','integration','wealth','financials','scenario_profiles','decisions'):
            supplied=getattr(package,key)
            if supplied is not None:
                data[key]=[v.model_dump(mode='json') for v in supplied] if isinstance(supplied,list) else supplied.model_dump(mode='json')
        documents=list(data.get('documents',[]))
        artifacts={}
        for file in package.files:
            file_path=Path(file.path)
            if not file_path.is_absolute():
                file_path=path.parent/file_path
            content=file_path.read_bytes()
            doc=file.document
            if digest(content)!=doc.sha256:
                raise ValueError('evidence file hash mismatch')
            source=next((s for s in data['sources'] if s['source_id']==doc.source_id),None)
            if not source or source.get('document_sha256',doc.sha256)!=doc.sha256:
                raise ValueError('document/source hash mismatch or missing source')
            payload=doc.model_dump(mode='json')
            if payload not in documents:
                documents.append(payload)
            artifacts['data/evidence/blobs/'+doc.sha256+doc.suffix]=content
        if documents:
            data['documents']=documents
    except (ValueError,KeyError,TypeError,OSError) as exc:
        return pipeline.run(root,raw,workflow='import-evidence',validation_error=str(exc),as_of=as_of)
    return pipeline.run(root,dumps(data),workflow='import-evidence',artifacts=artifacts,as_of=as_of)


def migrate_workbook(root, workbook, mapping_file, *, accept=False):
    from . import pipeline
    packet=json.loads(mapping_file.read_bytes())
    if set(packet)!={'migration','sources'}:
        raise ValueError('mapping file requires migration and sources')
    migration=WorkbookMigration.model_validate(packet['migration'])
    raw=workbook.read_bytes()
    state=read_json(root,pipeline.STATE)
    if not state:
        raise ValueError('import canonical research/history before reconciling a legacy workbook')
    result=compare_workbook(raw,migration,state)
    result['accepted']=False
    result['reference_run_id']=state['published_run_id']
    if not accept:
        return result
    bundle=json.loads(pipeline.current_input(root))
    merge_sources(bundle,[Source.model_validate(s) for s in packet['sources']])
    migrations=list(bundle.get('migrations',[]))
    payload=migration.model_dump(mode='json')
    if not any(m['record_id']==migration.record_id for m in migrations):
        migrations.append(payload)
    elif next(m for m in migrations if m['record_id']==migration.record_id)!=payload:
        raise ValueError('migration record ID immutable')
    bundle['migrations']=migrations
    return pipeline.run(root,dumps(bundle),workflow='migrate-workbook',
                        artifacts={'data/evidence/blobs/'+migration.workbook_sha256+'.xlsx':raw})
