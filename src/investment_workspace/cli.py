"""Offline portfolio and research CLI. Phase 3 commands fail explicitly."""

import argparse
import json
import sys
from pathlib import Path

from . import pipeline
from .storage import LockBusy, PublicationError


def main(argv=None):
    parser = argparse.ArgumentParser(description="Evidence-linked investment workspace — Phase 2 offline research")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="Git workspace root")
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init", help="Publish the clearly labelled synthetic offline demo")
    init.add_argument("--offline", action="store_true", required=True)
    init.add_argument("--phase2", action="store_true", help="Use the synthetic Phase 2 model/entitlement demo")
    imp = sub.add_parser("import-portfolio", help="Import a strict JSON bundle of snapshots, ledger, prices and sources")
    imp.add_argument("--file", type=Path, required=True)
    research = sub.add_parser("import-research", help="Import a sources/research JSON evidence packet")
    research.add_argument("--file", type=Path, required=True)
    sub.add_parser("update-dividends", help="Recompute accepted dividend evidence and entitlement")
    run_parser = sub.add_parser("run", help="Recalculate the last accepted portfolio import")
    run_parser.add_argument("workflow", choices=["daily", "portfolio", "valuation", "ic", "event"])
    run_parser.add_argument("--offline", action="store_true")
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
            result = pipeline.run(root, pipeline.fixture_bytes(args.phase2), workflow="init-demo")
        elif args.command == "import-portfolio":
            result = pipeline.run(root, args.file.read_bytes(), workflow="import-portfolio")
        elif args.command == "import-research":
            result = pipeline.import_research(root, args.file.read_bytes())
        elif args.command == "update-dividends":
            result = pipeline.run(root, pipeline.current_input(root), workflow="update-dividends")
        elif args.command == "run":
            if args.workflow not in {"daily", "portfolio", "valuation"}:
                raise ValueError("this workflow needs Phase 3 verified models/data")
            result = pipeline.run(root, pipeline.current_input(root), workflow=args.workflow)
        elif args.command == "validate":
            result = pipeline.validate(root, args.run)
        elif args.command == "export-excel":
            result = pipeline.run(root, pipeline.current_input(root), workflow="export-excel")
        elif args.command == "replay":
            result = pipeline.replay(root, args.run_id, args.output)
        elif args.command == "import-overrides":
            result = pipeline.import_overrides(root, args.workbook)
        elif args.command == "recover":
            result = pipeline.recover(root)
        else:
            result = pipeline.push(root, args.remote, args.branch)
        print(json.dumps(result, indent=2, sort_keys=True))
        if args.command == "run" and args.require_full_coverage:
            state = pipeline.read_json(root, pipeline.STATE)
            if result.get("status") == "FAILED" or state.get("research", {}).get("summary", {}).get("valuation_status") != "COMPLETE":
                return 1
        return 1 if result.get("status") == "FAILED" else 0
    except (ValueError, OSError, PublicationError, LockBusy) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
