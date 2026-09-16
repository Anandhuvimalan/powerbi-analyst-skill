from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

from .adapters import DesktopBridgeAdapter, ModelingMCPAdapter, ReportAuthoringAdapter
from .core import BuildError, write_json
from .orchestrator import analyze_request, build, load_request, verify_runtime
from .planning import plan_model
from .bootstrap import plan_report
from .transaction import recover


def parser():
    root = argparse.ArgumentParser(prog="powerbi-agent", description="Build actual PBIP/TMDL/PBIR projects from the existing analyst skill.")
    sub = root.add_subparsers(dest="action", required=True)
    for action in ["build", "plan"]:
        p = sub.add_parser(action)
        p.add_argument("request", nargs="?", type=Path)
        p.add_argument("--project")
        p.add_argument("--output")
        p.add_argument("--data", action="append")
        p.add_argument("--goal")
        p.add_argument("--modeling", choices=["file", "mcp"])
        p.add_argument("--remote-schema", action="store_true")
        p.add_argument("--auto-open", action="store_true")
        p.add_argument("--bootstrap", action="store_true", help="Explicit preset technical demo; not an agent-designed dashboard")
        if action == "plan":
            p.add_argument("--artifacts", type=Path, default=Path("output/plan"))
    sub.add_parser("doctor")
    p = sub.add_parser("discover-tools")
    p.add_argument("--out", type=Path, default=Path("output/mcp-tools.json"))
    p = sub.add_parser("recover")
    p.add_argument("project", type=Path)
    p = sub.add_parser("verify-runtime")
    p.add_argument("project", type=Path)
    connection = p.add_mutually_exclusive_group(required=True)
    connection.add_argument("--connection-env")
    connection.add_argument("--desktop", action="store_true", help="Discover the AS child of the matching Desktop project")
    p.add_argument("--refresh", action="store_true", help="Refresh a verified non-Desktop XMLA model before DAX checks")
    p.add_argument("--native-refresh", action="store_true", help="Optional Windows/English native Refresh fallback with --desktop")
    return root


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if args.action in {"build", "plan"}:
            if args.request:
                request, base = load_request(args.request.resolve()), args.request.resolve().parent
            else:
                if not args.project or not args.data or not args.goal:
                    raise BuildError("Supply a request JSON or --project, --data, and --goal.")
                request, base = {"project": args.project, "sources": args.data, "business_goal": args.goal}, Path.cwd()
            if args.output:
                request["output"] = args.output
            if args.bootstrap:
                request["agent_mode"] = False
            if args.modeling:
                request["modeling"] = {"mode": args.modeling}
            if args.remote_schema:
                request["remote_schema"] = True
            if args.auto_open:
                request["auto_open_powerbi"] = True
            if args.action == "build":
                state = build(request, base)
                if request.get("runtime") and state.status != "built_runtime_verified":
                    return 2
                if request.get("visual_qa") and not any(r["check"] == "visual_qa" and r["status"] == "passed" for r in state.validation_results):
                    return 2
            else:
                data = analyze_request(request, base)
                if any(d.source["kind"] == "sqlite" for d in data):
                    raise BuildError("SQLite snapshot planning runs as part of build; use CSV for a separate plan.")
                model = plan_model(data, request["business_goal"])
                write_json(args.artifacts / "profile.json", [d.profile for d in data])
                write_json(args.artifacts / "model-plan.json", model)
                write_json(args.artifacts / "design-context.json", {
                    "business_objective": request["business_goal"], "brand": request.get("brand", {}),
                    "instruction": "Author analysis-brief.json and report-plan.json from these observations. Review the model scaffold. Every page element and style must be explicit; the renderer adds no header, navigation, KPI row or layout.",
                    "schemas": {name: json.loads((Path(__file__).parent / "schemas" / (name + ".json")).read_text())
                                for name in ("report-plan", "analysis-brief")}})
                if args.bootstrap:
                    write_json(args.artifacts / "bootstrap-report-plan.json", plan_report(model, request["business_goal"], request.get("brand")))
                print(f"[PLAN] Artifacts saved in {args.artifacts}; no Power BI project was changed.")
        elif args.action == "doctor":
            desktop = DesktopBridgeAdapter()
            report = ReportAuthoringAdapter()
            data = {"report_cli": report.command, "modeling_mcp": ModelingMCPAdapter().command, "desktop_cli": desktop.command}
            try:
                data["desktop_status"] = desktop.status()
            except BuildError as exc:
                data["desktop_status"] = str(exc)
            print(json.dumps(data, indent=2))
        elif args.action == "discover-tools":
            tools = asyncio.run(ModelingMCPAdapter().discover())
            write_json(args.out, tools)
            print(f"Discovered {len(tools)} tools; saved schemas to {args.out}")
        elif args.action == "recover":
            recover(args.project)
            print("Recovery complete")
        elif args.action == "verify-runtime":
            project = args.project.resolve()
            if args.native_refresh and (not args.desktop or args.refresh):
                raise BuildError("--native-refresh requires --desktop and cannot be combined with XMLA --refresh.")
            if args.desktop:
                desktop = DesktopBridgeAdapter()
                pid = desktop.select_pid(project)
                if args.native_refresh:
                    desktop.native_refresh(project, pid)
                connection = asyncio.run(ModelingMCPAdapter().desktop_connection(pid))
            else:
                value = os.environ.get(args.connection_env)
                if not value:
                    raise BuildError("Connection environment variable is missing.")
                connection = {"operation": "Connect", "connectionString": value}
            result = verify_runtime(project, connection, refresh=args.refresh)
            print(json.dumps(result, indent=2))
        return 0
    except (BuildError, OSError, ValueError, KeyError) as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
