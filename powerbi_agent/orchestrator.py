from __future__ import annotations

import asyncio
import copy
import csv
import os
import shutil
import uuid
from pathlib import Path

from .adapters import DesktopBridgeAdapter, ModelingMCPAdapter, ReportAuthoringAdapter
from .analysis import discover
from .agent_workflow import require_agent_inputs, validate_brief
from .core import BuildError, ProjectState, read_json, within, write_json
from .model import TmdlWriter, dq
from .planning import plan_model
from .qa import CommandVisionReviewer, visual_qa
from .report import PbirWriter, plan_report
from .reasoning import CommandReasoningAdapter
from .runtime import assess_results, source_expectations
from .transaction import ProjectTransaction
from .validation import PowerBIValidator, cli_result, enforce


def load_request(path: Path):
    from jsonschema import Draft202012Validator
    request = read_json(path)
    schema = read_json(Path(__file__).parent / "schemas" / "request.json")
    errors = sorted(Draft202012Validator(schema).iter_errors(request), key=lambda e: str(e.path))
    if errors:
        raise BuildError("Invalid request: " + "; ".join(f"{list(e.path)}: {e.message}" for e in errors))
    return request


def project_layout(project: Path, managed=False):
    report = project.stem + ".Report"
    model = project.stem + ".SemanticModel"
    if project.exists():
        existing = read_json(project)
        reports = [a["report"]["path"] for a in existing.get("artifacts", []) if "report" in a]
        if len(reports) > 1:
            raise BuildError("A build target must reference exactly one report.")
        if reports:
            report_path = within(project.parent, reports[0])
            if report_path.parent != project.parent:
                raise BuildError("This executor requires report/model artifact folders directly beside the PBIP.")
            report = report_path.name
            pbir = report_path / "definition.pbir"
            if pbir.exists():
                reference = read_json(pbir).get("datasetReference", {})
                if "byConnection" in reference:
                    raise BuildError("Remote semantic-model references require an explicit model adapter; use a local byPath starter.")
                if "byPath" in reference:
                    model_path = (report_path / reference["byPath"]["path"]).resolve()
                    if model_path.parent != project.parent:
                        raise BuildError("Starter model must resolve beside the PBIP.")
                    model = model_path.name
    if not managed:
        model_dir, report_dir = project.parent / model, project.parent / report
        if any((model_dir / "definition" / "tables").glob("*.tmdl")) or (model_dir / "model.bim").exists():
            raise BuildError("Target contains an existing unmanaged analytical model. Choose --output for a new project; importing existing model edits requires a reviewed migration, not an automatic overwrite.")
        if any((report_dir / "definition" / "pages").glob("*/visuals/*/visual.json")) or (report_dir / "report.json").exists():
            raise BuildError("Target contains an unmanaged report. Choose --output to preserve it.")
    return report, model


def analyze_request(request, base):
    datasets = discover(request["sources"], base, request.get("max_rows", 100000))
    return datasets


def build(request: dict, base=Path.cwd(), *, model_adapter=None, report_adapter=None, report_cli=None, desktop=None, reviewer=None):
    require_agent_inputs(request)
    base = base.resolve()
    starter = (base / request["project"]).resolve()
    project = (base / request.get("output", request["project"])).resolve()
    if project.suffix.lower() != ".pbip" or starter.suffix.lower() != ".pbip":
        raise BuildError("Project and output must use .pbip; binary PBIX editing is unsupported.")
    state = ProjectState(str(project), request["business_goal"])
    validator = PowerBIValidator()
    report_cli = report_cli or ReportAuthoringAdapter()
    model_adapter = model_adapter or TmdlWriter()
    report_adapter = report_adapter or PbirWriter()
    with ProjectTransaction(project) as tx:
        try:
            report_name, model_name = project_layout(project, bool(tx.old))
            state.log("DATA", "Discovering and profiling sources")
            datasets = analyze_request(request, base)
            state.dataset_profile = [d.profile for d in datasets]
            # SQLite's native connector varies by machine. A deterministic CSV snapshot is explicit.
            for dataset in datasets:
                if dataset.source["kind"] == "sqlite":
                    relative = model_name + "/sources/" + dataset.name + ".csv"
                    target = within(tx.stage, relative)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with target.open("w", encoding="utf-8", newline="") as stream:
                        writer = csv.DictWriter(stream, fieldnames=[c["name"] for c in dataset.profile["columns"]])
                        writer.writeheader()
                        writer.writerows(dataset.rows)
                    dataset.source = {"kind": "csv", "path": str(within(project.parent, relative)), "delimiter": ",", "snapshot": True}
            state.source_files = [d.source for d in datasets]
            plan_input = request.get("model_plan")
            state.model_plan = read_json((base / plan_input).resolve()) if isinstance(plan_input, str) else copy.deepcopy(plan_input) if plan_input else plan_model(datasets, request["business_goal"])
            generated_report = None
            brief_input = request.get("analysis_brief")
            state.analysis_brief = read_json((base / brief_input).resolve()) if isinstance(brief_input, str) else copy.deepcopy(brief_input) if brief_input else {}
            if request.get("reasoning"):
                if plan_input or request.get("report_plan"):
                    raise BuildError("Choose reasoning.command or explicit plans; do not supply both.")
                config = request["reasoning"]
                state.log("PLAN", "Applying the original knowledge skill through the configured AI planner")
                ai = CommandReasoningAdapter(config["command"], config.get("knowledge_root"))
                result = ai.plan(datasets, request["business_goal"], state.model_plan,
                    plan_report(state.model_plan, request["business_goal"], request.get("brand")), tx.run)
                state.model_plan, generated_report = result["model_plan"], result["report_plan"]
                state.analysis_brief = result.get("analysis_brief", {})
            state.domain = state.model_plan.get("domain", "general")
            state.model_plan.setdefault("domain", state.domain)
            result = validator.model(state.model_plan)
            state.validation_results.append(result)
            enforce(result)
            report_input = request.get("report_plan")
            state.report_plan = read_json((base / report_input).resolve()) if isinstance(report_input, str) else copy.deepcopy(report_input) if report_input else generated_report or plan_report(state.model_plan, request["business_goal"], request.get("brand"))
            result = validator.report(state.report_plan, state.model_plan)
            state.validation_results.append(result)
            enforce(result)
            if request.get("agent_mode") or state.analysis_brief:
                result = validate_brief(state.analysis_brief, state.dataset_profile, state.report_plan)
                state.validation_results.append(result)
                enforce(result)
                write_json(tx.run / "analysis-brief.json", state.analysis_brief)
            state.save(tx.run / "state.json")
            write_json(tx.run / "model-plan.json", state.model_plan)
            write_json(tx.run / "report-plan.json", state.report_plan)
            write_json(tx.run / "runtime-checks.json", source_expectations(state.model_plan, datasets))
            state.status = "executing"
            mode = request.get("modeling", {}).get("mode", "file")
            seed = copy.deepcopy(state.model_plan)
            if mode == "mcp":
                seed["measures"] = []
            state.log("MODEL", f"Writing {len(seed['tables'])} tables and {len(seed['relationships'])} relationships")
            model_adapter.apply(tx.stage / model_name, seed)
            if mode == "mcp":
                config = request.get("modeling", {})
                mcp = ModelingMCPAdapter(config.get("command"), allow_write=True)
                state.log("DAX", f"Creating {len(state.model_plan['measures'])} measures through Microsoft Modeling MCP")
                state.validation_results.append(asyncio.run(mcp.execute_folder(tx.stage / model_name / "definition", state.model_plan["measures"])))
            else:
                state.log("DAX", f"Applied {len(seed['measures'])} measure definitions to TMDL")
            state.log("REPORT", f"Creating {len(state.report_plan['pages'])} pages with bound visuals and theme")
            report_adapter.apply(tx.stage / report_name, model_name, state.report_plan)
            for name, kind in [(report_name, "Report"), (model_name, "SemanticModel")]:
                existing_platform = project.parent / name / ".platform"
                if existing_platform.is_file():
                    shutil.copy2(existing_platform, tx.stage / name / ".platform")
                else:
                    write_json(tx.stage / name / ".platform", {
                        "$schema": "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json",
                        "metadata": {"type": kind, "displayName": project.stem},
                        "config": {"version": "2.0", "logicalId": str(uuid.uuid5(uuid.NAMESPACE_URL, str(project) + kind))}})
            write_json(tx.stage / project.name, {"$schema": "https://developer.microsoft.com/json-schemas/fabric/pbip/pbipProperties/1.0.0/schema.json",
                "version": "1.0", "artifacts": [{"report": {"path": report_name}}], "settings": {"enableAutoRecovery": True}})
            result = validator.files(tx.stage)
            state.validation_results.append(result)
            enforce(result)
            result = cli_result(report_cli.validate(tx.stage / report_name, request.get("remote_schema", False)))
            state.validation_results.append(result)
            enforce(result)
            state.log("VALIDATE", "Model references, report bindings, layout and generated files checked")
            state.validation_results.extend([
                {"check": "dax_runtime", "status": "not_run", "detail": "Open and refresh the generated PBIP, then run verify-runtime against that model."},
                {"check": "m_refresh", "status": "not_run", "detail": "Power BI runtime and source credentials required."}])
            publication = tx.publish()
            state.log("SAVE", f"Published {publication['files_written']} project files; checkpoint saved")
            state.status = "built_pending_runtime"
            state.save(tx.run / "state.json")
        except BaseException as exc:
            state.status = "failed"
            state.errors.append(str(exc))
            state.save(tx.run / "state.json")
            raise
    # Live optional checks occur only after publishing a complete validated project.
    # Report refinements are independently checkpointed; Desktop failure leaves valid files available.
    desktop = desktop or DesktopBridgeAdapter()
    if request.get("auto_open_powerbi") or request.get("visual_qa") or request.get("runtime"):
        try:
            if request.get("auto_open_powerbi"):
                desktop.open(project)
                state.log("DESKTOP", "Opened project; model refresh requires Desktop runtime")
            runtime = request.get("runtime")
            if runtime:
                command = request.get("modeling", {}).get("command")
                if runtime.get("desktop"):
                    pid = desktop.select_pid(project, request.get("desktop", {}).get("pid"))
                    if runtime.get("native_refresh"):
                        state.log("DESKTOP", "Invoking the optional native Refresh command on the matching project")
                        state.validation_results.append({"check": "native_refresh_request", "status": "invoked", "result": desktop.native_refresh(project, pid)})
                    connection = asyncio.run(ModelingMCPAdapter(command).desktop_connection(pid))
                else:
                    if runtime.get("native_refresh"):
                        raise BuildError("native_refresh requires runtime.desktop:true.")
                    value = os.environ.get(runtime.get("connection_env", ""))
                    if not value:
                        raise BuildError("runtime needs desktop:true or a configured connection_env.")
                    connection = {"operation": "Connect", "connectionString": value}
                state.log("DAX", "Executing source, filter and time-context checks against the connected model")
                result = execute_runtime(state.model_plan, tx.run, connection, command, runtime.get("refresh", False))
                for prior in state.validation_results:
                    if prior["check"] == "dax_runtime":
                        prior["superseded"] = True
                state.validation_results.append(result)
                state.status = "built_runtime_verified" if result["status"] == "passed" else "built_runtime_" + result["status"]
                enforce(result)
            if request.get("visual_qa"):
                qa = request.get("qa", {})
                if reviewer is None and qa.get("reviewer_command"):
                    reviewer = CommandVisionReviewer(qa["reviewer_command"])
                if reviewer is None:
                    state.validation_results.append({"check": "visual_qa", "status": "unavailable", "detail": "Configure qa.reviewer_command for a vision model. Layout lint is not a screenshot review."})
                else:
                    def rerender(candidate):
                        with ProjectTransaction(project) as refinement:
                            for relative in refinement.old:
                                path = within(refinement.stage, relative)
                                path.parent.mkdir(parents=True, exist_ok=True)
                                shutil.copy2(within(project.parent, relative), path)
                            report_adapter.apply(refinement.stage / report_name, model_name, candidate)
                            enforce(cli_result(report_cli.validate(refinement.stage / report_name, request.get("remote_schema", False))))
                            refinement.publish()
                    result, state.report_plan = visual_qa(state, project, state.report_plan, state.model_plan, desktop, reviewer, rerender,
                        tx.run / "screenshots", qa.get("max_iterations", 3), qa.get("threshold", 90), request.get("desktop", {}).get("pid"))
                    state.validation_results.append(result)
        except BuildError as exc:
            if request.get("runtime") and state.status == "built_pending_runtime":
                state.status = "built_runtime_unavailable"
            state.validation_results.append({"check": "desktop_visual_qa", "status": "unavailable", "detail": str(exc)})
            state.log("DESKTOP", str(exc))
    else:
        state.validation_results.append({"check": "visual_qa", "status": "not_run", "detail": "No Desktop screenshots were reviewed."})
    state.log("DONE", f"PBIP saved: {project}. Status: {state.status}. See state.json for separate runtime and visual evidence.")
    state.save(tx.run / "state.json")
    write_json(tx.home / "latest.json", {"state": str(tx.run / "state.json"), "project": str(project)})
    return state


def verify_runtime(project: Path, connection: dict, command=None, refresh=False):
    tx = ProjectTransaction(project)
    state_path = Path(read_json(tx.home / "latest.json")["state"])
    state = read_json(state_path)
    record = execute_runtime(state["model_plan"], state_path.parent, connection, command, refresh)
    for prior in state["validation_results"]:
        if prior["check"] == "dax_runtime":
            prior["superseded"] = True
    state["validation_results"].append(record)
    state["status"] = "built_runtime_verified" if record["status"] == "passed" else "built_runtime_" + record["status"]
    if refresh:
        state["validation_results"].append({"check": "m_refresh", "status": "passed", "detail": "RefreshWithXMLA completed on the verified connected model."})
    write_json(state_path, state)
    enforce(record)
    return record


def execute_runtime(model, run, connection, command=None, refresh=False):
    checks = read_json(run / "runtime-checks.json")
    adapter = ModelingMCPAdapter(command, allow_write=refresh)
    results = asyncio.run(adapter.execute_dax(connection, [c["query"] for c in checks], model["measures"], refresh=refresh))
    record = assess_results(checks, results)
    write_json(run / "runtime-results.json", results)
    write_json(run / "runtime-assessment.json", record)
    return record
