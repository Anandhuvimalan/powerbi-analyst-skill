"""Traceable agent planning; the deterministic bootstrap is never an agent result."""
from collections import Counter
from pathlib import Path

from jsonschema import Draft202012Validator

from .core import BuildError, read_json


def require_agent_inputs(request):
    if request.get("agent_mode", True) and not request.get("reasoning"):
        if not all(request.get(key) for key in ("analysis_brief", "model_plan", "report_plan")):
            raise BuildError("Agent mode requires analysis_brief, model_plan and report_plan authored from this dataset, or reasoning.command. Run plan to inspect data, then have your host agent author the plans. For a preset technical demo only, explicitly use --bootstrap or agent_mode:false.")


def validate_brief(brief, profiles, report):
    schema = read_json(Path(__file__).parent / "schemas/analysis-brief.json")
    errors = [f"{list(e.path)}: {e.message}" for e in Draft202012Validator(schema).iter_errors(brief)]
    if report.get("composition") == "bootstrap":
        errors.append("Preset bootstrap reports cannot be submitted as agent-authored designs. Author the report from the analytical brief.")
    if errors:
        return {"check": "agent_analysis", "status": "failed", "errors": errors}
    columns = {p["name"]: {c["name"] for c in p["columns"]} for p in profiles}
    for grain in brief["grain"]:
        if grain["table"] not in columns:
            errors.append(f"Grain references unknown source table: {grain['table']}")
    if {g["table"] for g in brief["grain"]} != set(columns):
        errors.append("State the observed grain of every profiled source table.")
    for finding in brief["findings"]:
        for field in finding["evidence"]:
            if field["column"] not in columns.get(field["table"], set()):
                errors.append(f"Finding references missing source evidence: {field['table']}.{field['column']}")
    page_names = [p["page"] for p in brief["pages"]]
    if set(page_names) != {p["name"] for p in report["pages"]} or len(page_names) != len(set(page_names)):
        errors.append("Each report page needs exactly one analysis-brief decision and justification.")
    # Catch literal duplicate analytical visuals, not valid repeated slicers/navigation.
    for page in report["pages"]:
        signatures = []
        for visual in page["visuals"]:
            if visual["type"] in {"slicer", "pageNavigator", "textbox", "actionButton", "shape", "image"}:
                continue
            import json
            signatures.append(json.dumps({key: visual.get(key) for key in ("type", "roles", "filters")}, sort_keys=True))
        if any(count > 1 for count in Counter(signatures).values()):
            errors.append(f"Page {page['title']} contains duplicate analytical visuals with identical fields and filters.")
    return {"check": "agent_analysis", "status": "failed" if errors else "passed", "errors": errors,
            "detail": "Source evidence and page decisions are traceable. This check cannot prove originality or business correctness; the host agent must review both."}
