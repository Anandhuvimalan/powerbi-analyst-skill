"""Traceable agent planning; the deterministic bootstrap is never an agent result."""
from collections import Counter
from pathlib import Path

from jsonschema import Draft202012Validator

from .core import BuildError, read_json
from .report import DECORATIVE, SLICERS, effective_style

# The bootstrap demo's palette; an authored project must derive its own.
PRESET_CANVAS = "#F2F5F7"
PRESET_ACCENTS = {"#196A83", "#6550A3", "#215A63", "#4457A8", "#285D85"}


def design_system_errors(report):
    """The report must carry a project-derived design system and visibly group its content."""
    errors = []
    system = report.get("design_system")
    if not system:
        return ["Author report_plan.design_system (concept, derived_from, tokens, typography, grid, filter_strategy) from this project before laying out pages. See references/visual-design-system.md."]
    palette = {k: str(v).upper() for k, v in report["theme"]["palette"].items()}
    tokens = {k: str(v).upper() for k, v in system["tokens"].items()}
    if palette.get("canvas") == PRESET_CANVAS and palette.get("accent") in PRESET_ACCENTS or tokens.get("accent") in PRESET_ACCENTS and tokens.get("canvas") == PRESET_CANVAS:
        errors.append("The palette is the preset demo palette. Derive tokens from the project's brand, domain and audience.")
    themed_cards = any(entry.get("background", [{}])[0].get("show") for entry in report["theme"]["definition"].get("visualStyles", {}).get("*", {}).values())
    for page in report["pages"]:
        if page.get("hidden") or page.get("tooltip") or system.get("flat_layout_reason"):
            continue
        data = [v for v in page["visuals"] if v["type"] not in DECORATIVE and v["type"] not in SLICERS]
        if len(data) < 2:
            continue
        panels = [v for v in page["visuals"] if v.get("layer") == "background" and v["type"] in {"shape", "basicShape"}]
        def card(visual):
            authored = visual.get("container_objects", {}).get("background")
            if authored:
                return authored[0].get("properties", {}).get("show") != {"expr": {"Literal": {"Value": "false"}}}
            background = effective_style(visual, report).get("background")
            return bool(background) or background is None and themed_cards
        cards = all(card(v) for v in data)
        if not panels and not cards:
            errors.append(f"Page {page['title']}: content floats on the bare canvas. Group it with background-layer panel shapes or a card treatment (style.background), or state design_system.flat_layout_reason.")
    return errors


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
    errors.extend(design_system_errors(report))
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
