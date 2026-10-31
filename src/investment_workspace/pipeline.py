"""Offline run lifecycle, immutable inputs and checksummed, locally committed revisions."""

import json
import sys
import time
import uuid
from copy import deepcopy
from datetime import date, datetime, timezone
from importlib.resources import files
from importlib.metadata import version
from pathlib import Path

from . import __version__
from .contracts import normalize, payload as record_payload, active_sources
from .runtime import RunContext, context, current
from .record_history import accept_records
from .wealth import calculate_wealth
from .migration import verify_migrations, export_compatibility, active_legacy
from .readiness import report as readiness_report
from .excel import export_workbook, read_notes, validate_workbook
from .portfolio import calculate
from .schemas import Bundle, NoteOverride, Transaction
from .research import COLLECTIONS, calculate_research
from .workflows import calculate_workflows, records as integration_records, GROUPS as INTEGRATION_GROUPS, SINGLE as INTEGRATION_SINGLE
from pydantic import ValidationError
from .storage import (LockBusy, PublicationError, atomic_write, committed, digest, dumps,
                      git, head, prepare_repository, publish, read_json, require_clean,
                      rollback_pending, writer_lock)

WORKBOOK = "workbooks/Investment_Workspace.xlsx"
STATE = "data/canonical/portfolio.json"


def new_id():
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + "-" + uuid.uuid4().hex[:8]


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def code_hash():
    root = Path(__file__).parent
    return digest(b"".join(p.name.encode() + p.read_bytes() for p in sorted(root.glob("*.py"))))


def fixture_bytes(phase2=False, phase3=False, phase4=False):
    name = "phase4-demo.json" if phase4 else "phase3-demo.json" if phase3 else "phase2-demo.json" if phase2 else "demo.json"
    return files("investment_workspace").joinpath("fixtures/" + name).read_bytes()


def empty_state():
    return {"holdings": [], "transactions": [], "summary": {"mode": "UNKNOWN", "cash": None, "total_assets": None, "market_cutoff": None, "sizing_status": "BLOCKED"}, "reconciliation": [], "coverage": [], "data_gaps": [], "sources": [], "assumptions": [], "notes": [], "run_log": [], "changes": [], "usage": [], "analysis_run_id": None}


def record_failure(root, run_id, error, status="PUBLICATION_FAILED"):
    diagnostic = {"run_id": run_id, "status": status, "attempted_at": timestamp(), "error": str(error), "publication_status": "NOT_PUBLISHED"}
    atomic_write(root / ".runtime/failed" / f"{run_id}.json", dumps(diagnostic))
    return diagnostic


def queued_failures(root):
    return [json.loads(p.read_bytes()) for p in sorted((root / ".runtime/failed").glob("*.json"))]


def recover_abandoned_staging(root):
    for stage in sorted((root / ".runtime/staging").glob("*")):
        if not stage.is_dir() or not (stage / "attempt.json").exists():
            continue
        if committed(root, f"runs/{stage.name}/manifest.json") is not None:
            continue
        if not (root / ".runtime/failed" / f"{stage.name}.json").exists():
            record_failure(root, stage.name, "Abandoned staging detected; committed revision retained", "ABANDONED_STAGING")


def same_analytics(left, right):
    # Exclude lineage from change detection; original dates/IDs survive no-change runs.
    keys = ("holdings", "transactions", "summary", "reconciliation", "data_gaps", "coverage", "notes", "research", "integration", "wealth", "financials", "dataset", "evaluation_as_of", "evidence_fingerprint", "migration_records", "documents")
    def clean(value):
        if isinstance(value, dict):
            return {k: clean(v) for k, v in value.items() if not (k == "covered_event_ids" and v == []) and k not in {"run_id", "upstream_run_ids", "code_version", "input_hash", "confidence", "validation_status", "owner", "schema_version", "effective_date", "record_id", "market_cutoff_metadata", "import_source_id", "units", "assumption_ids", "source_ids"}}
        if isinstance(value, list):
            return [clean(v) for v in value]
        return value
    return {k: clean(normalize(left.get(k))) for k in keys} == {k: clean(normalize(right.get(k))) for k in keys}


def metadata(bundle, run_id, input_hash, owner, source_ids):
    policy_id = "policy." + digest(dumps(bundle.policy.model_dump(mode="json")))
    return {"schema_version": "1.0", "run_id": run_id, "owner": owner, "effective_date": bundle.closing.timestamp.date().isoformat(), "market_cutoff_metadata": bundle.market_cutoff.isoformat(), "units": "PKR / shares / fraction as named", "source_ids": sorted(set(source_ids)), "assumption_ids": [policy_id], "upstream_run_ids": [], "code_version": __version__, "input_hash": input_hash, "confidence": "SYNTHETIC" if bundle.mode == "DEMO" else "SOURCE_DECLARED", "validation_status": "VALIDATED"}


def merge_notes(previous, overrides, bundle, run_id, source_id):
    notes = deepcopy(previous)
    existing = {n["override_id"]: n for n in notes}
    for note in overrides:
        payload = note.model_dump(mode="json")
        if note.ticker not in {s.ticker for s in bundle.securities}:
            raise ValueError(f"unknown note ticker: {note.ticker}")
        if note.effective_date > bundle.market_cutoff:
            raise ValueError("note effective date is after cutoff")
        if note.override_id in existing:
            old = {k: existing[note.override_id].get(k) for k in payload}
            if old != payload:
                raise ValueError("override ID is immutable; use a new ID and supersedes")
            continue
        if note.supersedes and note.supersedes not in existing:
            raise ValueError("superseded override does not exist")
        if note.supersedes and existing[note.supersedes]["ticker"] != note.ticker:
            raise ValueError("override cannot supersede another ticker's note")
        accepted = {**metadata(bundle, run_id, source_id.removeprefix("manual."), "user_notes", [source_id]), **payload, "record_id": note.override_id, "import_source_id": source_id, "previous_value": existing[note.supersedes]["value"] if note.supersedes else None}
        notes.append(accepted)
        existing[note.override_id] = accepted
    return notes


def run(root: Path, input_bytes: bytes, *, overrides=(), override_bytes=None, workflow="portfolio", validation_error=None,
        as_of=None, max_units=None, max_seconds=None, artifacts=None, activate_dataset=False, recalculate=False) -> dict:
    root = root.resolve()
    run_id = new_id()
    began = time.monotonic()
    try:
        with writer_lock(root):
            prepare_repository(root)
            recovered = rollback_pending(root)
            if recovered and not recovered["committed"]:
                record_failure(root, recovered["run_id"], "Interrupted publication recovered; previous committed revision retained")
            recover_abandoned_staging(root)
            require_clean(root)
            evaluated = date.fromisoformat(as_of) if isinstance(as_of,str) else as_of
            runtime = RunContext(root,code_hash(),read_json(root,STATE,{}),as_of=evaluated,max_units=max_units,
                                 max_seconds=max_seconds,artifacts=artifacts,verify=recalculate or workflow=='valuation')
            with context(runtime):
                return _run_locked(root, run_id, input_bytes, overrides, override_bytes, workflow, began, validation_error, activate_dataset)
    except Exception as exc:
        record_failure(root, run_id, exc, "LOCK_BUSY" if isinstance(exc, LockBusy) else "PUBLICATION_FAILED")
        if isinstance(exc, (PublicationError, LockBusy)):
            raise
        raise PublicationError(f"output generation failed; previous committed revision retained: {exc}") from exc


def _run_locked(root, run_id, input_bytes, overrides, override_bytes, workflow, began, validation_error, activate_dataset=False):
    previous = read_json(root, STATE, empty_state())
    archived_previous = None
    runtime = current()
    state = deepcopy(previous)
    input_hash = digest(input_bytes)
    source_id = "input." + input_hash
    source_path = f"data/evidence/blobs/{input_hash}.json"
    stage = root / ".runtime/staging" / run_id
    stage.mkdir(parents=True)
    atomic_write(stage / "request.json", input_bytes)
    atomic_write(stage / "attempt.json", dumps({"run_id": run_id, "attempted_at": timestamp(), "workflow": workflow}))
    atomic_write(stage / "request_notes.json", dumps([note.model_dump(mode="json") for note in overrides]))
    if override_bytes is not None:
        atomic_write(stage / "request_workbook.xlsx", override_bytes)
    if validation_error:
        atomic_write(stage / "request_error.json", dumps(validation_error))
    request_context = {'as_of':runtime.as_of.isoformat() if runtime.as_of else None,
                       'max_units':runtime.max_units,'max_seconds':runtime.max_seconds,'activate_dataset':activate_dataset,
                       'artifacts':list(runtime.artifacts), 'recalculate':runtime.verify}
    atomic_write(stage / 'request_context.json', dumps(request_context))
    for path, raw in runtime.artifacts.items():
        name = Path(path).name
        if path != 'data/evidence/blobs/'+name or '.' not in name or name.split('.')[0] != digest(raw) or Path(name).suffix not in {'.xlsx','.json','.csv','.pdf','.txt','.md'}:
            raise ValueError('artifact path must be its content-addressed permitted evidence path')
        atomic_write(stage / '_request_artifacts' / path, raw)
    error = None
    status = "FAILED"
    bundle = None
    try:
        if validation_error:
            raise ValueError(validation_error)
        bundle = Bundle.model_validate_json(input_bytes)
        dataset_id = bundle.dataset_id or ('legacy.demo' if bundle.mode=='DEMO' else 'legacy.user')
        prior_dataset = previous.get('dataset',{'dataset_id':'legacy.demo' if previous['summary'].get('mode')=='DEMO' else 'legacy.user',
                                                'mode':previous['summary'].get('mode')})
        switched = bool(previous.get('analysis_run_id') and (prior_dataset['dataset_id']!=dataset_id or prior_dataset['mode']!=bundle.mode))
        if switched:
            if not isinstance(activate_dataset,dict) or activate_dataset.get('confirmed_real_data') is not True or not activate_dataset.get('author') or not activate_dataset.get('reason') or prior_dataset['mode']!='DEMO' or bundle.mode!='USER_IMPORT' or not bundle.dataset_id:
                raise ValueError('dataset/mode immutable; explicit DEMO-to-production activation or a fresh workspace required')
            if any(sec.ticker.startswith('DEMO') for sec in bundle.securities) or any(src.source_id.startswith(('demo.','synthetic.')) or 'SYNTHETIC' in src.title.upper() for src in bundle.sources):
                raise ValueError('synthetic fixtures cannot be activated as production data')
            archived_previous = deepcopy(previous)
            previous = empty_state()
            previous['run_log'] = archived_previous['run_log']
            previous['changes'] = archived_previous['changes']
            runtime.cache = {}
        elif activate_dataset:
            raise ValueError('dataset activation requires an existing DEMO and a distinct real dataset ID')
        if runtime.as_of and runtime.as_of < bundle.market_cutoff:
            raise ValueError('evaluation date cannot precede the supplied observation cutoff')
        with runtime.phase('portfolio'):
            state = calculate(bundle)
        state['dataset'] = {'dataset_id':dataset_id,'mode':bundle.mode}
        state['active_source_ids']=active_sources(bundle)
        if archived_previous:
            state['dataset']['activation']=activate_dataset
        if runtime.as_of:
            state['evaluation_as_of'] = runtime.as_of.isoformat()
            state['summary']['evaluation_as_of'] = runtime.as_of.isoformat()
        # An immutable transaction ID cannot silently be reassigned on later imports.
        old_transactions = {t["transaction_id"]: t for t in previous["transactions"]}
        for t in state["transactions"]:
            if t["transaction_id"] in old_transactions:
                old = old_transactions[t["transaction_id"]]
                if any(t[k] != old.get(k) for k in Transaction.model_fields):
                    raise ValueError(f"previously accepted transaction changed: {t['transaction_id']}")
        current_ids = {t["transaction_id"] for t in state["transactions"]}
        for old in previous["transactions"]:
            if bundle.opening.timestamp < datetime.fromisoformat(old["timestamp"]) <= bundle.closing.timestamp and old["transaction_id"] not in current_ids:
                raise ValueError("previously accepted transaction omitted from overlapping ledger window")
        state["transactions"] = sorted([t for t in previous["transactions"] if t["transaction_id"] not in current_ids] + state["transactions"], key=lambda t: (t["timestamp"], t["transaction_id"]))
        all_sources = {s["source_id"]: s for s in previous["sources"]}
        for source in bundle.sources:
            payload = record_payload(source)
            # Bind source IDs to the actual referenced facts, not merely their title.
            facts = {"source": payload, "snapshots": [s.model_dump(mode="json") for s in (bundle.opening, bundle.closing) if s.source_id == source.source_id], "prices": sorted([p.model_dump(mode="json") for p in bundle.prices if p.source_id == source.source_id], key=lambda p: p["ticker"]), "transactions": sorted({t.transaction_id: t.model_dump(mode="json") for t in bundle.transactions if t.source_id == source.source_id}.values(), key=lambda t: t["transaction_id"])}
            research_facts = [record_payload(r) for group in COLLECTIONS
                              for r in getattr(bundle.research, group) if source.source_id in r.source_ids
                              or any(a.source_id == source.source_id for a in getattr(r, "adjustments", []))] if bundle.research else []
            for record in research_facts:
                if not record.get("covered_event_ids"):
                    record.pop("covered_event_ids", None)
            prior_research = [r["payload"] for r in previous.get("research", {}).get("history", [])
                              if source.source_id in r["payload"]["source_ids"] or
                              any(a["source_id"] == source.source_id for a in r["payload"].get("adjustments", []))]
            if research_facts or prior_research:
                retained = {r["record_id"]: r for r in prior_research}
                for record in research_facts:
                    if record["record_id"] in retained and retained[record["record_id"]] != record:
                        raise ValueError("research record ID is immutable")
                    retained[record["record_id"]] = record
                facts["research"] = sorted(retained.values(), key=lambda r: r["record_id"])
            if bundle.research and source.source_id in bundle.research.universe_source_ids:
                facts["universe"] = {k: v for k, v in bundle.research.model_dump(mode="json").items() if k not in COLLECTIONS}
            elif source.source_id in all_sources and all_sources[source.source_id].get("bound_universe"):
                facts["universe"] = all_sources[source.source_id]["bound_universe"]
            integrated = {r["record_id"]: r["payload"] for r in previous.get("integration", {}).get("history", [])
                          if source.source_id in r["payload"]["source_ids"] or any(a["source_id"] == source.source_id for a in r["payload"].get("actions", []))}
            for group, record in integration_records(bundle.integration):
                if source.source_id in record.source_ids or any(a.source_id == source.source_id for a in getattr(record, "actions", [])):
                    payload_record = record_payload(record)
                    if record.record_id in integrated and integrated[record.record_id] != payload_record:
                        raise ValueError("integration record ID is immutable")
                    integrated[record.record_id] = payload_record
            if integrated:
                facts["integration"] = sorted(integrated.values(), key=lambda r: r["record_id"])
            for module, incoming in (('financials',bundle.financials),('wealth',[r for g in ('assets','flows','scenarios','plans','histories') for r in getattr(bundle.wealth,g)] if bundle.wealth else [])):
                prior_owned = {r['record_id']:r['payload'] for r in previous.get(module,{}).get('history',[])
                               if source.source_id in r['payload']['source_ids'] or r['payload'].get('fx_source_id')==source.source_id}
                for record in incoming:
                    if source.source_id in record.source_ids or getattr(record,'fx_source_id',None)==source.source_id:
                        incoming_payload = record_payload(record)
                        if record.record_id in prior_owned and normalize(prior_owned[record.record_id])!=incoming_payload:
                            raise ValueError('owned record ID is immutable')
                        prior_owned[record.record_id]=incoming_payload
                if prior_owned:
                    facts[module]=sorted(prior_owned.values(),key=lambda r:r['record_id'])
            linked_documents=[d.model_dump(mode='json') for d in bundle.documents if d.source_id==source.source_id]
            if linked_documents:
                facts['documents']=sorted(linked_documents,key=lambda d:(d['sha256'],d['role']))
            linked_migrations = [record_payload(m) for m in bundle.migrations if source.source_id in m.source_ids]
            if linked_migrations:
                facts['migrations']=sorted(linked_migrations,key=lambda m:m['record_id'])
            fact_hash = digest(dumps(facts))
            if source.source_id in all_sources:
                old = {k: all_sources[source.source_id].get(k) for k in payload}
                has_facts = any(facts.get(k) for k in ("snapshots", "prices", "transactions", "research", "universe", "integration", "financials", "wealth", "migrations", "documents"))
                if old != payload or (has_facts and all_sources[source.source_id].get('facts_bound',True) and all_sources[source.source_id].get("fact_hash") != fact_hash):
                    raise ValueError("source ID is immutable; revised evidence needs a new ID")
            if source.source_id not in all_sources or not all_sources[source.source_id].get('facts_bound',True):
                all_sources[source.source_id] = {**payload, "fact_hash": fact_hash, "content_hash": input_hash, "content_path": source_path, "bound_universe": facts.get("universe"), "facts_bound": any(facts.get(k) for k in facts if k != "source")}
        all_sources[source_id] = {"source_id": source_id, "title": "Immutable imported bundle", "publisher": "user" if bundle.mode == "USER_IMPORT" else "offline fixture", "effective_date": bundle.market_cutoff.isoformat(), "locator": source_path, "evidence_label": "UNVERIFIED" if bundle.mode == "USER_IMPORT" else "ASSUMPTION", "content_hash": input_hash, "content_path": source_path}
        override_id = "manual." + digest(override_bytes) if override_bytes is not None else source_id
        if override_bytes is not None:
            all_sources[override_id] = {"source_id": override_id, "title": "Explicit Manual_Inputs import", "publisher": "user", "effective_date": bundle.market_cutoff.isoformat(), "locator": f"data/evidence/blobs/{digest(override_bytes)}.xlsx", "evidence_label": "CONFIRMED", "content_hash": digest(override_bytes), "content_path": f"data/evidence/blobs/{digest(override_bytes)}.xlsx"}
        state["sources"] = list(all_sources.values())
        state["notes"] = merge_notes(previous["notes"], overrides, bundle, run_id, override_id)
        state["assumptions"] = deepcopy(previous.get("assumptions", []))
        policy_id = "policy." + digest(dumps(bundle.policy.model_dump(mode="json")))
        if not any(a["assumption_id"] == policy_id for a in state["assumptions"]):
            state["assumptions"].append({"assumption_id": policy_id, "owner": "validation", "scope": "input freshness and reconciliation tolerances; no investment recommendation", "effective_date": bundle.market_cutoff.isoformat(), "value": bundle.policy.model_dump(mode="json"), "source_ids": [source_id], "run_id": run_id, "evidence_label": "ASSUMPTION"})
        for document in bundle.documents:
            if document.source_id not in {s.source_id for s in bundle.sources}:
                raise ValueError('unregistered document source')
            raw_document=runtime.blob(document.sha256,document.suffix)
            if raw_document is None or digest(raw_document)!=document.sha256:
                raise ValueError('evidence document missing or corrupt')
        old_documents=previous.get('documents',[])
        documents=[d.model_dump(mode='json') for d in bundle.documents]
        if any(d not in documents for d in old_documents):
            raise ValueError('accepted original documents cannot be omitted')
        if documents:
            state['documents']=documents
        financial_history = accept_records({'facts':bundle.financials},previous.get('financials',{}),bundle,run_id,input_hash)
        if bundle.financials or financial_history:
            state['financials']={'input':{'facts':[{**record_payload(f), 'owner':'financials','run_id':next(r['run_id'] for r in financial_history if r['record_id']==f.record_id),'schema_version':'4.0','units':f.units,'input_hash':next(r['input_hash'] for r in financial_history if r['record_id']==f.record_id)} for f in bundle.financials]},'history':financial_history,
                                'facts':[{**record_payload(f), 'owner':'financials','run_id':next(r['run_id'] for r in financial_history if r['record_id']==f.record_id),'schema_version':'4.0','units':f.units,'input_hash':next(r['input_hash'] for r in financial_history if r['record_id']==f.record_id)} for f in bundle.financials]}
        with runtime.phase('valuation'):
            calculate_research(bundle, state, previous, run_id, input_hash)
        if bundle.research:
            for model in bundle.research.models:
                if not any(a["assumption_id"] == model.record_id for a in state["assumptions"]):
                    state["assumptions"].append({"assumption_id": model.record_id, "owner": "valuation",
                        "scope": model.ticker + " explicit scenario/model assumptions", "effective_date": model.effective_date.isoformat(),
                        "value": model.model_dump(mode="json"), "source_ids": model.source_ids,
                        "run_id": run_id, "evidence_label": "ASSUMPTION"})
        with runtime.phase('integration'):
            calculate_workflows(bundle, state, previous, run_id, input_hash)
        if not bundle.integration:
            verify_migrations(bundle,state,previous)
        with runtime.phase('wealth'):
            calculate_wealth(bundle,state,previous,run_id,input_hash)
        if not bundle.wealth and workflow in {'retirement','cross-asset'}:
            state['data_gaps'].append({'ticker':None,'field':'wealth','reason':'MISSING_WEALTH_INPUT','owner':'wealth','next_action':'Import dated wealth inputs'})
        if not bundle.integration and workflow in {"ic", "event", "timing", "macro", "watchlist", "analyze"}:
            state["data_gaps"].append({"ticker": None, "field": "integration", "reason": "MISSING_INTEGRATION_INPUT",
                "owner": "integration", "next_action": "Import the dated Phase 3 sources/integration evidence packet"})
        if bundle.integration:
            for field in ("timing_policy", "risk_limits", "alert_methodology"):
                assumption = getattr(bundle.integration, field)
                if assumption and not any(a["assumption_id"] == assumption.record_id for a in state["assumptions"]):
                    state["assumptions"].append({"assumption_id": assumption.record_id, "owner": field,
                        "scope": "Explicit Phase 3 methodology/limits; not inherited defaults",
                        "effective_date": assumption.effective_date.isoformat(), "value": assumption.model_dump(mode="json"),
                        "source_ids": assumption.source_ids, "run_id": run_id, "evidence_label": "ASSUMPTION"})
        state['evidence_fingerprint']=digest(dumps([{k:v for k,v in source.items() if k not in {'content_hash','content_path'}}
                            for source in state['sources'] if not source['source_id'].startswith(('input.','manual.'))]))
        unchanged = same_analytics(previous, state)
        if unchanged:
            registry = state["sources"]
            assumptions = state["assumptions"]
            state = deepcopy(previous)
            state["sources"] = registry
            state["assumptions"] = assumptions
            status = "NO_MATERIAL_CHANGE"
        else:
            owners = {"holdings": "portfolio", "transactions": "portfolio", "reconciliation": "portfolio", "coverage": "valuation", "data_gaps": "validation"}
            for collection, owner in owners.items():
                for index, row in enumerate(state[collection]):
                    key = "transaction_id" if collection == "transactions" else "ticker" if collection in {"holdings", "coverage"} else None
                    old = next((r for r in previous[collection] if key and r.get(key) == row.get(key)), None)
                    if old and same_analytics({"holdings": [row]}, {"holdings": [old]}):
                        state[collection][index] = deepcopy(old)
                        continue
                    sources = row.get("source_ids", [s.source_id for s in bundle.sources])
                    row.update(metadata(bundle, run_id, input_hash, owner, sources + [source_id]))
                    if collection == "transactions":
                        row["effective_date"] = datetime.fromisoformat(row["timestamp"]).date().isoformat()
                    row.setdefault("record_id", f"{collection}.{index}")
            if same_analytics({"summary": state["summary"]}, {"summary": previous["summary"]}):
                state["summary"] = deepcopy(previous["summary"])
            else:
                state["summary"].update(metadata(bundle, run_id, input_hash, "portfolio", [s.source_id for s in bundle.sources] + [source_id]))
            state["analysis_run_id"] = run_id
            status = "PARTIAL" if state["reconciliation"] or any(g["reason"] in {"STALE_HOLDINGS", "MISSING_PRICE", "STALE_PRICE", "UNVERIFIED_INPUT"} for g in state["data_gaps"]) else "SUCCESS"
    except Exception as exc:
        error = json.dumps(exc.errors(include_input=False, include_url=False), default=str) if isinstance(exc, ValidationError) else str(exc)
        state = deepcopy(previous)
        state["data_gaps"] = [g for g in state["data_gaps"] if g.get("field") != "run_attempt"]
        state["data_gaps"].append({"ticker": None, "field": "run_attempt", "reason": "FAILED_INPUT_VALIDATION", "detail": error, "owner": "validation", "next_action": "Correct the import; last-good analytical values retained"})
        state["summary"]["sizing_status"] = "BLOCKED"
    if not error and state.get("research") and status != "NO_MATERIAL_CHANGE":
        status = "COMPLETE" if state["research"]["summary"]["valuation_status"] == "COMPLETE" and status != "PARTIAL" else "PARTIAL"
    if not error and not state.get("research") and workflow in {"valuation", "update-dividends"}:
        status = "PARTIAL"
    if not error and state.get("integration") and status != "NO_MATERIAL_CHANGE":
        status = "PARTIAL" if state["integration"]["summary"]["integration_status"] == "PARTIAL" or status == "PARTIAL" else "COMPLETE"
    if not error and not state.get("integration") and workflow in {"ic", "event", "timing", "macro", "watchlist", "analyze"}:
        status = "PARTIAL"
    if not error and workflow in {'retirement','cross-asset'} and status!='NO_MATERIAL_CHANGE':
        key='retirement_status' if workflow=='retirement' else 'cross_asset_status'
        status='COMPLETE' if state.get('wealth',{}).get('summary',{}).get(key)=='COMPLETE' else 'PARTIAL'
    if runtime.deferred and not error:
        status='PARTIAL'
    status = "FAILED" if error else status
    pending = queued_failures(root)
    logs = deepcopy(previous["run_log"])
    known = {entry["run_id"] for entry in logs}
    logs.extend(entry for entry in pending if entry["run_id"] not in known)
    entry = {"run_id": run_id, "workflow": workflow, "status": status, "attempted_at": timestamp(), "market_cutoff": bundle.market_cutoff.isoformat() if bundle else None, "analysis_run_id": state.get("analysis_run_id"), "input_hash": input_hash, "error": error, "publication_status": "LOCAL_ONLY"}
    if runtime.as_of:
        entry['evaluation_as_of']=runtime.as_of.isoformat()
    entry['dataset_id']=state.get('dataset',{}).get('dataset_id')
    logs.append(entry)
    state["run_log"] = logs
    state["attempt_status"] = status
    state["published_run_id"] = run_id
    state["schema_version"] = "1.0"
    state["changes"] = deepcopy(previous["changes"])
    if status not in {"FAILED", "NO_MATERIAL_CHANGE"}:
        if previous.get('evidence_fingerprint')!=state.get('evidence_fingerprint'):
            state['changes'].append({'run_id':run_id,'ticker':None,'field':'evidence_registry','change_type':'EVIDENCE',
                'previous':previous.get('evidence_fingerprint'),'new':state.get('evidence_fingerprint')})
        if previous.get('evaluation_as_of')!=state.get('evaluation_as_of'):
            state['changes'].append({'run_id':run_id,'ticker':None,'field':'evaluation_as_of','change_type':'ASSESSMENT',
                'previous':previous.get('evaluation_as_of'),'new':state.get('evaluation_as_of')})
        before = {h["ticker"]: h for h in previous["holdings"]}
        for h in state["holdings"]:
            for field in ("quantity", "cost", "price", "market_value"):
                old = before.get(h["ticker"], {}).get(field)
                if old != h[field]:
                    state["changes"].append({"run_id": run_id, "ticker": h["ticker"], "field": field, "previous": old, "new": h[field], "source_ids": h["source_ids"]})
        for ticker in sorted(set(before) - {h["ticker"] for h in state["holdings"]}):
            state["changes"].append({"run_id": run_id, "ticker": ticker, "field": "position", "previous": before[ticker], "new": None})
        for collection in ("earnings", "valuations", "entries", "dividends"):
            old_rows = previous.get("research", {}).get(collection, [])
            new_rows = state.get("research", {}).get(collection, [])
            if old_rows != new_rows:
                state["changes"].append({"run_id": run_id, "ticker": None, "field": collection,
                                          "previous": {'records':len(old_rows),'sha256':digest(dumps(old_rows))},
                                          "new": {'records':len(new_rows),'sha256':digest(dumps(new_rows))},
                                          "detail_path":f'runs/{run_id}/snapshot.json', "collection":collection})
        for collection in ("timing", "events", "risk", "watchlist", "ic_actions"):
            old_rows = previous.get("integration", {}).get(collection, [])
            new_rows = state.get("integration", {}).get(collection, [])
            if old_rows != new_rows:
                state["changes"].append({"run_id": run_id, "ticker": None, "field": collection,
                                          "previous": {'records':len(old_rows),'sha256':digest(dumps(old_rows))},
                                          "new": {'records':len(new_rows),'sha256':digest(dumps(new_rows))},
                                          "detail_path":f'runs/{run_id}/snapshot.json', "collection":collection})
        for collection in ('assets','flows','projections','cross_asset'):
            old_rows=previous.get('wealth',{}).get(collection,[])
            new_rows=state.get('wealth',{}).get(collection,[])
            if old_rows!=new_rows:
                state['changes'].append({'run_id':run_id,'ticker':None,'field':'wealth.'+collection,
                    'previous':{'records':len(old_rows),'sha256':digest(dumps(old_rows))},
                    'new':{'records':len(new_rows),'sha256':digest(dumps(new_rows))},'detail_path':f'runs/{run_id}/snapshot.json'})
        old_notes = {n["override_id"] for n in previous["notes"]}
        for note in state["notes"]:
            if note["override_id"] not in old_notes:
                state["changes"].append({"run_id": run_id, "ticker": note["ticker"], "field": "note", "previous": note["previous_value"], "new": note["value"], "source_ids": [note["import_source_id"]]})
    if not error:
        state['calculations']=runtime.cache
    state['deferred_work']=runtime.deferred
    state['dependencies']=runtime.dependencies
    state['readiness']=readiness_report(state)
    state["usage"] = deepcopy(previous["usage"]) + [{"run_id": run_id, "runtime_seconds": None, "calculation_runtime_seconds": round(time.monotonic() - began, 6), "input_tokens": None, "cached_input_tokens": None, "output_tokens": None, "reasoning_tokens": None, "cost": None, "phase_runtime_seconds":runtime.timings,"calculation_units":runtime.units,"cache_hits":runtime.hits,"cache_arithmetic_verified":runtime.verified,"deferred_units":len(runtime.deferred),"telemetry": "AI telemetry unknown; total wall time recorded externally after commit"}]
    prefix = f"runs/{run_id}"
    payloads = {STATE: dumps(state), f"{prefix}/snapshot.json": dumps(state), f"{prefix}/input.json": input_bytes, f"{prefix}/coverage.json": dumps(state["coverage"]), f"{prefix}/validation.json": dumps({"status": status, "error": error, "sizing_status": state["summary"]["sizing_status"], "workbook_parity": "PASS"}), f"{prefix}/changes.json": dumps([c for c in state["changes"] if c["run_id"] == run_id]), f"{prefix}/usage.json": dumps(state["usage"][-1]), "data/evidence/sources.json": dumps(state["sources"]), "reports/latest/summary.json": dumps({"run_id": run_id, "status": status, "summary": state["summary"], "gaps": state["data_gaps"]})}
    if state.get("research"):
        payloads["data/canonical/research.json"] = dumps(state["research"])
        payloads["reports/latest/valuation.json"] = dumps(state["research"]["summary"])
    if state.get("integration"):
        payloads["data/canonical/integration.json"] = dumps(state["integration"])
        payloads["reports/latest/integration.json"] = dumps(state["integration"]["summary"])
        payloads["feeds/latest/timing.json"] = dumps(state["integration"]["timing"])
        payloads["feeds/latest/ic.json"] = dumps(state["integration"]["ic_actions"])
    if state.get('wealth'):
        payloads['data/canonical/wealth.json']=dumps(state['wealth'])
    if state.get('financials'):
        payloads['data/canonical/financials.json']=dumps(state['financials'])
    payloads['reports/latest/readiness.json']=dumps(state['readiness'])
    delta=[change for change in state['changes'] if change['run_id']==run_id]
    payloads['reports/latest/changes.md']=(f"# Changes — {run_id}\n\nStatus: {status}\n\n"+
        '\n'.join('- '+str(c.get('ticker') or 'workspace')+': '+c['field'] for c in delta)+
        ('\n\nNo financial or evidence changes.\n' if not delta else '\n')+
        '\nReadiness: '+state['readiness']['deployment']+'\n').encode()
    payloads[f'{prefix}/dependencies.json']=dumps(runtime.dependencies)
    payloads[f'{prefix}/deferred.json']=dumps(runtime.deferred)
    if archived_previous:
        archive_id=archived_previous.get('dataset',{}).get('dataset_id','legacy.demo')
        payloads[f'data/history/datasets/{archive_id}/{archived_previous["published_run_id"]}.json']=dumps(archived_previous)
    for path,raw in runtime.artifacts.items():
        old_blob=committed(root,path)
        if old_blob is not None and old_blob!=raw:
            raise PublicationError('immutable evidence artifact hash mismatch')
        if old_blob is None:
            payloads[path]=raw
    # Once content-addressed evidence exists, never rewrite it.
    if committed(root, source_path) is None:
        payloads[source_path] = input_bytes
    elif committed(root, source_path) != input_bytes:
        raise PublicationError("immutable evidence hash mismatch")
    if override_bytes is not None:
        note_path = f"data/evidence/blobs/{digest(override_bytes)}.xlsx"
        if committed(root, note_path) is None:
            payloads[note_path] = override_bytes
    # Retain diagnostics for attempts whose workbook publication previously failed.
    for failure in pending:
        failure_path = f"runs/{failure['run_id']}/manifest.json"
        if committed(root, failure_path) is None:
            payloads[failure_path] = dumps(failure)
    for path, raw in payloads.items():
        atomic_write(stage / path, raw)
    export_workbook(stage / WORKBOOK, state)
    paths = sorted([*payloads, WORKBOOK])
    compatible='workbooks/PSX_Mean_Reversion_DataStore.xlsx'
    verified_legacy=bool(active_legacy(state.get('migration_records',[])))
    if verified_legacy or committed(root,compatible) is not None:
        export_compatibility(stage/compatible,state,blocked=not verified_legacy)
        paths.append(compatible)
    hashes = {path: digest((stage / path).read_bytes()) for path in paths}
    lockfile = committed(root, "uv.lock")
    manifest = {**entry, "schema_version": "1.0", "base_commit": head(root), "code_version": __version__, "code_hash": code_hash(), "dependency_lock_hash": digest(lockfile) if lockfile else None, "python_version": sys.version.split()[0], "dependencies": {name: version(name) for name in ("pydantic", "openpyxl")}, "policy_hash": digest(dumps(bundle.policy.model_dump(mode="json"))) if bundle else None, "offline": True, "scope": "Phase 4 wealth and investment workflows" if state.get("wealth") else "Phase 3 integrated investment workflows" if state.get("integration") else "Phase 2 research and portfolio" if state.get("research") else "Phase 1 portfolio; valuation blocked", "output_hashes": hashes}
    manifest_path = f"{prefix}/manifest.json"
    atomic_write(stage / manifest_path, dumps(manifest))
    paths.append(manifest_path)
    sha = publish(root, stage, paths, run_id, status)
    elapsed = round(time.monotonic() - began, 6)
    atomic_write(root / ".runtime/publications" / f"{run_id}.json", dumps({"run_id": run_id, "commit": sha, "publication_status": "LOCAL_ONLY", "runtime_seconds": elapsed}))
    for failure in pending:
        (root / ".runtime/failed" / f"{failure['run_id']}.json").unlink(missing_ok=True)
    return {**manifest, "commit": sha, "runtime_seconds": elapsed}


def current_input(root):
    state = read_json(root, STATE)
    if not state or not state.get("analysis_run_id"):
        raise ValueError("no accepted portfolio yet; run init --offline or import-portfolio first")
    raw = committed(root, f"runs/{state['analysis_run_id']}/input.json")
    if raw is None:
        raise ValueError("accepted input missing from committed history")
    return raw


def import_overrides(root: Path, workbook: Path):
    raw = workbook.read_bytes()
    try:
        notes = read_notes(workbook)
        if not notes:
            raise ValueError("Manual_Inputs contains no notes to import")
    except (ValueError, ValidationError) as exc:
        error = json.dumps(exc.errors(include_input=False, include_url=False), default=str) if isinstance(exc, ValidationError) else str(exc)
        return run(root, current_input(root), override_bytes=raw, workflow="import-overrides", validation_error=error)
    return run(root, current_input(root), overrides=notes, override_bytes=raw, workflow="import-overrides")


def validate(root: Path, run_id="latest"):
    state = read_json(root, STATE)
    if run_id == "latest":
        if not state:
            raise ValueError("no published run")
        run_id = state["published_run_id"]
    if "/" in run_id or ".." in run_id:
        raise ValueError("invalid run ID")
    manifest = read_json(root, f"runs/{run_id}/manifest.json")
    if not manifest or "output_hashes" not in manifest:
        raise ValueError("run has no successfully published output set")
    # Mutable latest paths are verified in the chosen run's commit, not current HEAD.
    commit = git(root, "log", "-1", "--format=%H", "--", f"runs/{run_id}/manifest.json").stdout.decode().strip()
    for path, expected in manifest["output_hashes"].items():
        data = git(root, "show", f"{commit}:{path}", check=False)
        if data.returncode or digest(data.stdout) != expected:
            raise ValueError(f"committed output integrity failed: {path}")
    snapshot = read_json(root, f"runs/{run_id}/snapshot.json")
    tmp = root / ".runtime/validation" / f"{run_id}.xlsx"
    atomic_write(tmp, git(root, "show", f"{commit}:{WORKBOOK}").stdout)
    validate_workbook(tmp, snapshot)
    return {"run_id": run_id, "commit": commit, "integrity": "PASS", "workbook_parity": "PASS", "analytical_status": manifest["status"]}


def replay(root: Path, run_id: str, output: Path):
    result = validate(root, run_id)
    state = read_json(root, f"runs/{result['run_id']}/snapshot.json")
    if output.resolve().is_relative_to(root.resolve()):
        raise ValueError("replay output must be outside the checkout to preserve published files")
    if output.exists():
        raise ValueError("replay will not overwrite an existing file")
    export_workbook(output, state)
    return {**result, "output": str(output), "offline": True}


def recover(root: Path):
    overrides = []
    override_bytes = None
    validation_error = None
    options = {}
    with writer_lock(root):
        journal = rollback_pending(root)
        if journal and not journal["committed"]:
            record_failure(root, journal["run_id"], "Interrupted publication rolled back before retry")
            stage = root / journal["stage"]
            if journal.get("commit_marker"):
                return {"status":"REQUEST_ROLLED_BACK", "retry":"wealth-request --pending", "run_id":journal["run_id"]}
            raw = (stage / "request.json").read_bytes()
            if (stage/'request_context.json').exists():
                options=json.loads((stage/'request_context.json').read_bytes())
                options['artifacts']={path:(stage/'_request_artifacts'/path).read_bytes() for path in options['artifacts']}
            overrides = [NoteOverride.model_validate(n) for n in json.loads((stage / "request_notes.json").read_bytes())]
            if (stage / "request_workbook.xlsx").exists():
                override_bytes = (stage / "request_workbook.xlsx").read_bytes()
            if (stage / "request_error.json").exists():
                validation_error = json.loads((stage / "request_error.json").read_bytes())
        elif journal:
            return {"status": "RECOVERED_COMMITTED", "run_id": journal["run_id"], "commit": head(root)}
        else:
            raw = current_input(root)
    return run(root, raw, overrides=overrides, override_bytes=override_bytes, workflow="recovery", validation_error=validation_error, **options)


def push(root: Path, remote="origin", branch="main"):
    if branch.startswith("-") or remote.startswith("-"):
        raise ValueError("invalid remote or branch")
    with writer_lock(root):
        require_clean(root)
        state = read_json(root, STATE)
        if not state:
            raise ValueError("no committed workspace to push")
        # An explicit push command is authorization for this action only. Never automatic.
        result = git(root, "push", remote, f"HEAD:refs/heads/{branch}", check=False)
        status = "PUSH_FAILED"
        if result.returncode == 0:
            remote_head = git(root, "ls-remote", remote, f"refs/heads/{branch}", check=False)
            if remote_head.returncode == 0 and remote_head.stdout.decode().split()[0] == head(root):
                status = "PUSHED"
        log = {"run_id": state["published_run_id"], "commit": head(root), "status": status, "timestamp": timestamp()}
        atomic_write(root / ".runtime/push-log" / f"{new_id()}.json", dumps(log))
        if status != "PUSHED":
            raise PublicationError("push failed or remote verification failed; local commit retained. Fetch and inspect current canonical data before rerunning; never force-push or merge XLSX")
        return log


def import_research(root: Path, raw: bytes, **options):
    """Import sources and research into the accepted portfolio; publish failures normally."""
    try:
        packet = json.loads(raw)
        if set(packet) != {"sources", "research"}:
            raise ValueError("research packet requires exactly sources and research")
        bundle = json.loads(current_input(root))
        sources = {s["source_id"]: s for s in bundle["sources"]}
        for source in packet["sources"]:
            if source["source_id"] in sources and sources[source["source_id"]] != source:
                raise ValueError("source ID is immutable")
            sources[source["source_id"]] = source
        bundle["sources"] = list(sources.values())
        bundle["research"] = packet["research"]
        return run(root, dumps(bundle), workflow="import-research", **options)
    except (ValueError, KeyError, TypeError) as exc:
        return run(root, raw, workflow="import-research", validation_error=str(exc), **options)


def import_integration(root: Path, raw: bytes, *, workflow="import-integration", **options):
    """Merge a complete active integration packet into the committed portfolio."""
    try:
        packet = json.loads(raw)
        if set(packet) != {"sources", "integration"}:
            raise ValueError("integration packet requires exactly sources and integration")
        bundle = json.loads(current_input(root))
        sources = {s["source_id"]: s for s in bundle["sources"]}
        for source in packet["sources"]:
            if source["source_id"] in sources and sources[source["source_id"]] != source:
                raise ValueError("source ID is immutable")
            sources[source["source_id"]] = source
        bundle["sources"] = list(sources.values())
        bundle["integration"] = packet["integration"]
        return run(root, dumps(bundle), workflow=workflow, **options)
    except (ValueError, KeyError, TypeError) as exc:
        return run(root, raw, workflow=workflow, validation_error=str(exc), **options)


def import_wealth(root: Path, raw: bytes, **options):
    from .intake import merge_sources
    try:
        packet=json.loads(raw)
        if set(packet)!={'sources','wealth'}:
            raise ValueError('wealth packet requires exactly sources and wealth')
        bundle=json.loads(current_input(root))
        merge_sources(bundle,packet['sources'])
        bundle['wealth']=packet['wealth']
    except (ValueError,KeyError,TypeError) as exc:
        return run(root,raw,workflow='import-wealth',validation_error=str(exc),**options)
    return run(root,dumps(bundle),workflow='import-wealth',**options)


def changes_since(root: Path, run_id):
    if '/' in run_id or '..' in run_id:
        raise ValueError('invalid reference run ID')
    before=read_json(root,f'runs/{run_id}/snapshot.json')
    after=read_json(root,STATE)
    if not before or not after:
        raise ValueError('reference and current committed snapshots required')
    original={entry['run_id'] for entry in before['run_log']}
    rows=[c for c in after['changes'] if c['run_id'] not in original]
    return {'from_run':run_id,'to_run':after['published_run_id'],'changes':rows,
            'readiness_before':before.get('readiness'),'readiness_after':after.get('readiness')}
