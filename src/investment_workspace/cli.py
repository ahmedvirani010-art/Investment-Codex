"""Controlled offline research, portfolio and deterministic wealth-planning CLI."""

import argparse
import json
import sys
from pathlib import Path

from . import pipeline
from .storage import LockBusy, PublicationError


def main(argv=None):
    parser = argparse.ArgumentParser(description="Evidence-linked investment workspace — Controlled research and wealth planning")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="Git workspace root")
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init", help="Publish the clearly labelled synthetic offline demo")
    init.add_argument("--offline", action="store_true", required=True)
    init.add_argument("--completion-demo",action="store_true",help="Use the versioned numerical/scenario completion fixture")
    init.add_argument("--phase4", action="store_true", help="Use the synthetic wealth-planning demo")
    init.add_argument("--phase3", action="store_true", help="Use the synthetic integrated workflows demo")
    init.add_argument("--phase2", action="store_true", help="Use the synthetic Phase 2 model/entitlement demo")
    common=sub.add_parser('request',help='Process typed workspace requests')
    selected=common.add_mutually_exclusive_group(required=True)
    selected.add_argument('--file',type=Path)
    selected.add_argument('--pending',action='store_true')
    common.add_argument('--local-demo',action='store_true')
    common.add_argument('--publish',action='store_true')
    storage=sub.add_parser('storage',help='Bounded R2 transfers; no financial acceptance')
    storage.add_argument('operation',choices=['pull','push','status'])
    storage.add_argument('--file',type=Path)
    storage.add_argument('--request-id')
    storage.add_argument('--dry-run',action='store_true')
    sub.add_parser('decision-basis',help='Show reviewed-basis hashes for current proposals')
    request=sub.add_parser('wealth-request',help='Process committed chat requests through the wealth policy')
    choice=request.add_mutually_exclusive_group(required=True)
    choice.add_argument('--file',type=Path)
    choice.add_argument('--pending',action='store_true')
    request.add_argument('--local-demo',action='store_true')
    request.add_argument('--publish',action='store_true',help='Authorized private Actions normal push only')
    preflight=sub.add_parser('wealth-preflight',help='Check a wealth packet without changing accepted records')
    preflight.add_argument('--file',type=Path,required=True)
    preflight.add_argument('--as-of')
    benchmark=sub.add_parser('benchmark-wealth',help='Isolated equivalent-scope synthetic benchmark')
    benchmark.add_argument('--samples',type=int,default=3)
    benchmark.add_argument('--months',type=int,default=360)
    sub.add_parser('readiness', help='Read committed coverage, migration and deployment dependencies')
    delta=sub.add_parser('changes',help='Compare committed revisions')
    delta.add_argument('--since-run',required=True)
    for command in ('import-evidence','import-wealth'):
        intake=sub.add_parser(command,help='Import a controlled evidence/wealth JSON package')
        intake.add_argument('--file',type=Path,required=True)
        intake.add_argument('--as-of')
    migrate=sub.add_parser('migrate-workbook',help='Reconcile an explicitly mapped workbook before acceptance')
    migrate.add_argument('--file',type=Path,required=True)
    migrate.add_argument('--mapping',type=Path,required=True)
    operation=migrate.add_mutually_exclusive_group()
    operation.add_argument('--dry-run',action='store_true')
    operation.add_argument('--accept',action='store_true')
    activate=sub.add_parser('activate-dataset',help='Archive a DEMO and explicitly initialize a real dataset')
    activate.add_argument('--file',type=Path,required=True)
    activate.add_argument('--author',required=True)
    activate.add_argument('--reason',required=True)
    activate.add_argument('--confirm-real-data',action='store_true',required=True)
    automate=sub.add_parser('automation',help='Run only an explicitly activated production policy')
    automate.add_argument('--workflow',choices=['daily','valuation','ic','macro'],required=True)
    automate.add_argument('--as-of',required=True)
    automate.add_argument('--dry-run',action='store_true')
    automate.add_argument('--scheduled',action='store_true')
    imp = sub.add_parser("import-portfolio", help="Import a strict JSON bundle of snapshots, ledger, prices and sources")
    imp.add_argument("--file", type=Path, required=True)
    research = sub.add_parser("import-research", help="Import a sources/research JSON evidence packet")
    research.add_argument("--file", type=Path, required=True)
    integration = sub.add_parser("import-integration", help="Import strict sources/integration JSON packet")
    integration.add_argument("--file", type=Path, required=True)
    history = sub.add_parser("import-history", help="Fill one history in a JSON integration packet from a raw OHLCV CSV")
    history.add_argument("--file", type=Path, required=True)
    history.add_argument("--packet", type=Path, required=True)
    history.add_argument("--history-id", required=True)
    inspect = sub.add_parser("inspect-datastore", help="Read-only legacy workbook sheet/formula inventory")
    inspect.add_argument("--workbook", type=Path, required=True)
    analyze = sub.add_parser("analyze", help="Recalculate and report one security from owned shared state")
    analyze.add_argument("ticker")
    analyze.add_argument("--offline", action="store_true")
    sub.add_parser("update-dividends", help="Recompute accepted dividend evidence and entitlement")
    run_parser = sub.add_parser("run", help="Recalculate the last accepted portfolio import")
    run_parser.add_argument("workflow", choices=["daily", "portfolio", "valuation", "ic", "event", "timing", "macro", "watchlist", "retirement", "cross-asset"])
    run_parser.add_argument("--source-file", type=Path, help="Event JSON sources/integration packet; never guesses PDF contents")
    run_parser.add_argument("--ticker")
    run_parser.add_argument("--offline", action="store_true")
    run_parser.add_argument("--as-of")
    run_parser.add_argument("--max-work-units",type=int)
    run_parser.add_argument("--max-seconds",type=float)
    run_parser.add_argument("--scope", choices=["required"], default="required")
    run_parser.add_argument("--require-full-coverage", action="store_true")
    validate = sub.add_parser("validate", help="Check committed hashes and workbook parity")
    validate.add_argument("--run", default="latest")
    export = sub.add_parser("export-excel", help="Publish a fresh diagnostic/workbook revision from accepted input")
    export.add_argument("--offline", action="store_true")
    replay = sub.add_parser("replay", help="Rebuild a chosen committed dataset without network or state mutation")
    replay.add_argument("--run-id", required=True)
    replay.add_argument("--output", type=Path, required=True)
    replay.add_argument("--offline", action="store_true", required=True)
    notes = sub.add_parser("import-overrides", help="Explicitly import confirmed notes from Manual_Inputs only")
    notes.add_argument("--workbook", type=Path, required=True)
    sub.add_parser("schedule-status", help="Show disabled schedule plan and activation dependencies")
    sub.add_parser("recover", help="Recover interrupted publication and retry its input")
    push = sub.add_parser("push", help="Explicitly authorize a non-forced push; verify remote SHA")
    push.add_argument("--remote", default="origin")
    push.add_argument("--branch", default="main")
    args = parser.parse_args(argv)
    root = args.root.resolve()
    try:
        if args.command == "init":
            from .storage import read_json
            if read_json(root, pipeline.STATE):
                raise ValueError("workspace already has accepted data; init will not replace it with a demo")
            result = pipeline.run(root, pipeline.fixture_bytes(args.phase2, args.phase3, args.phase4,completion=args.completion_demo), workflow="init-demo")
        elif args.command=='request':
            from .workspace_requests import execute,pending
            if args.publish and not args.pending: raise ValueError('--publish requires --pending')
            result=pending(root,local_demo=args.local_demo,push=args.publish) if args.pending else execute(root,args.file,local_demo=args.local_demo)
        elif args.command=='storage':
            from .object_storage import execute,StorageRequest
            if args.operation=='status':
                from .schemas import Identifier
                from pydantic import TypeAdapter
                TypeAdapter(Identifier).validate_python(args.request_id)
                if args.request_id in {'.','..'}: raise ValueError('invalid storage request ID')
                result=pipeline.read_json(root,'reports/storage/'+args.request_id+'.json')
                if not result: raise ValueError('transfer receipt not found')
            else:
                if args.file is None: raise ValueError('--file is required')
                spec=StorageRequest.model_validate_json(args.file.read_bytes())
                if spec.operation!=args.operation: raise ValueError('storage operation mismatch')
                result=execute(root,spec,dry_run=args.dry_run)
        elif args.command=='decision-basis':
            from .decisions import basis
            state=pipeline.read_json(root,pipeline.STATE,{})
            proposals=state.get('integration',{}).get('input',{}).get('proposals',[])
            result={'proposals':[{'proposal_id':p['record_id'],'ticker':p['ticker'],'reviewed_basis_hash':basis(state,p['ticker'])} for p in proposals]}
        elif args.command=='wealth-request':
            from .wealth_requests import execute,pending
            if args.publish and not args.pending:
                raise ValueError('--publish requires --pending')
            result=pending(root,local_demo=args.local_demo,push=args.publish) if args.pending else execute(root,args.file,local_demo=args.local_demo)
        elif args.command=='wealth-preflight':
            from .wealth_requests import preflight
            result=preflight(root,json.loads(args.file.read_bytes()),as_of=args.as_of)
        elif args.command=='benchmark-wealth':
            from .wealth_benchmark import benchmark
            result=benchmark(samples=args.samples,months=args.months)
        elif args.command=='readiness':
            from .readiness import committed_report
            result=committed_report(root)
        elif args.command=='changes':
            result=pipeline.changes_since(root,args.since_run)
        elif args.command=='import-evidence':
            from .intake import import_package
            result=import_package(root,args.file,as_of=args.as_of)
        elif args.command=='import-wealth':
            result=pipeline.import_wealth(root,args.file.read_bytes(),as_of=args.as_of)
        elif args.command=='migrate-workbook':
            from .intake import migrate_workbook
            result=migrate_workbook(root,args.file,args.mapping,accept=args.accept)
        elif args.command=='activate-dataset':
            result=pipeline.run(root,args.file.read_bytes(),workflow='activate-dataset',activate_dataset={
                'author':args.author,'reason':args.reason,'confirmed_real_data':args.confirm_real_data})
        elif args.command=='automation':
            from .automation import execute
            result=execute(root,args.workflow,args.as_of,dry_run=args.dry_run,scheduled=args.scheduled)
        elif args.command == "import-portfolio":
            result = pipeline.run(root, args.file.read_bytes(), workflow="import-portfolio")
        elif args.command == "import-research":
            result = pipeline.import_research(root, args.file.read_bytes())
        elif args.command == "import-integration":
            result = pipeline.import_integration(root, args.file.read_bytes())
        elif args.command == "import-history":
            from .adapters import read_history_csv
            from .storage import dumps
            try:
                packet = json.loads(args.packet.read_bytes())
                histories = packet["integration"]["histories"]
                matches = [h for h in histories if h["record_id"] == args.history_id]
                if len(matches) != 1:
                    raise ValueError("history ID must resolve to exactly one packet history")
                matches[0]["bars"] = read_history_csv(args.file)
            except (ValueError, KeyError, TypeError) as exc:
                result = pipeline.run(root, args.file.read_bytes(), workflow="import-history", validation_error=str(exc))
            else:
                result = pipeline.import_integration(root, dumps(packet), workflow="import-history")
        elif args.command == "inspect-datastore":
            from .adapters import inspect_datastore
            result = inspect_datastore(args.workbook)
        elif args.command == "analyze":
            raw = pipeline.current_input(root)
            if args.ticker not in {s["ticker"] for s in json.loads(raw)["securities"]}:
                raise ValueError("ticker must be declared in the accepted securities")
            result = pipeline.run(root, raw, workflow="analyze")
            state = pipeline.read_json(root, pipeline.STATE)
            result["security"] = {key: [r for r in state.get("integration", {}).get(key, []) if r.get("ticker") == args.ticker or args.ticker in r.get("affected_tickers", [])]
                                  for key in ("timing", "events", "watchlist", "ic_actions")}
            result["security"].update({key: [r for r in state.get("research", {}).get(key, []) if r.get("ticker") == args.ticker]
                                       for key in ("earnings", "valuations", "entries")})
        elif args.command == "update-dividends":
            result = pipeline.run(root, pipeline.current_input(root), workflow="update-dividends")
        elif args.command == "run":
            if args.source_file:
                if args.workflow != "event":
                    raise ValueError("--source-file is only supported for run event")
                result = pipeline.import_integration(root, args.source_file.read_bytes(), workflow="event",as_of=args.as_of,max_units=args.max_work_units,max_seconds=args.max_seconds)
            else:
                result = pipeline.run(root, pipeline.current_input(root), workflow=args.workflow,as_of=args.as_of,max_units=args.max_work_units,max_seconds=args.max_seconds)
            if args.ticker:
                result["requested_ticker"] = args.ticker
                result["scope_note"] = "Shared dependents and full required coverage checked"
        elif args.command == "validate":
            result = pipeline.validate(root, args.run)
        elif args.command == "export-excel":
            result = pipeline.run(root, pipeline.current_input(root), workflow="export-excel")
        elif args.command == "replay":
            result = pipeline.replay(root, args.run_id, args.output)
        elif args.command == "import-overrides":
            result = pipeline.import_overrides(root, args.workbook)
        elif args.command == "schedule-status":
            result = pipeline.read_json(root, "config/schedules.json", {"enabled": False, "status": "UNCONFIGURED", "timezone": "Asia/Karachi"})
        elif args.command == "recover":
            result = pipeline.recover(root)
        else:
            result = pipeline.push(root, args.remote, args.branch)
        print(json.dumps(result, indent=2, sort_keys=True))
        if args.command == "run" and args.require_full_coverage:
            state = pipeline.read_json(root, pipeline.STATE)
            from .readiness import workflow_status
            if workflow_status(state,args.workflow)!='COMPLETE':
                return 1
        return 1 if result.get('status') in {'FAILED','BLOCKED','PUSH_FAILED','INVALID'} or args.command in {'automation','wealth-request','request'} and result.get('status')=='PARTIAL' else 0
    except (ValueError, OSError, KeyError, TypeError, PublicationError, LockBusy) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
