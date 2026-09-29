from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from zipfile import ZipFile

import pytest

from powerbi_agent.agent_workflow import validate_brief
from powerbi_agent.core import BuildError, identity, read_json
from powerbi_agent.orchestrator import build, analyze_request
from powerbi_agent.planning import plan_model


class OfflineCLI:
    def validate(self, *args):
        return {"check": "microsoft_report_cli", "status": "unavailable"}


def brief(report, table="Sales"):
    return {"audience": "Regional decision makers", "decisions": ["Prioritize profitable regions"],
        "grain": [{"table": table, "meaning": "One observed order line"}],
        "findings": [{"observation": "Revenue and cost are available at the same grain", "evidence": [{"table": table, "column": "Revenue"}], "implication": "Compare margin as a ratio of totals"}],
        "pages": [{"page": p["name"], "decision": p["title"], "why_needed": "Support the requested regional decision"} for p in report["pages"]],
        "design_rationale": "Emphasize the requested analytical decision with legible comparisons."}


def as_authored(report):
    """Turn the bootstrap fixture into an author-owned plan with its own design system."""
    report["composition"] = "authored"
    report["theme"]["palette"].update(canvas="#F4F1EA", accent="#8A4B2A")
    report["design_system"] = {"concept": "Regional margin ledger for decision makers",
        "derived_from": ["Revenue and cost share one order-line grain", "Audience compares a handful of regions"],
        "tokens": {"canvas": "#F4F1EA", "panel": "#FFFFFF", "ink": "#182B3A", "muted": "#526572", "accent": "#8A4B2A"},
        "typography": {"heading": "Segoe UI Semibold", "body": "Segoe UI"}, "grid": {"margin": 24, "gutter": 16, "columns": 12},
        "filter_strategy": "One region dropdown in the header; the page answers one regional question."}
    return report


@pytest.mark.parametrize("flags", [{}, {"agent_mode": True}])
def test_agent_mode_does_not_fall_back_to_bootstrap(tmp_path, flags):
    with pytest.raises(BuildError, match="Agent mode requires"):
        build({**flags, "project": "No.pbip", "sources": ["missing.csv"], "business_goal": "Analyze sales"}, tmp_path)
    assert not (tmp_path / "No.pbip").exists()
    assert not (tmp_path / ".powerbi-agent").exists()


def test_brief_requires_real_evidence_and_every_page(model, report, sales):
    report = as_authored(deepcopy(report))
    good = brief(report)
    assert validate_brief(good, [sales.profile], report)["status"] == "passed"
    bad = deepcopy(good)
    bad["findings"][0]["evidence"][0]["column"] = "InventedTarget"
    assert validate_brief(bad, [sales.profile], report)["status"] == "failed"
    bad = deepcopy(good)
    bad["pages"] = []
    assert validate_brief(bad, [sales.profile], report)["status"] == "failed"


def test_agent_mode_preserves_distinct_authored_experiences(tmp_path, model, report):
    # Same source, two author-owned reading orders, densities, canvases and typography.
    (tmp_path / "Sales.csv").write_text("OrderId,Revenue,Cost,Region\n001,100,60,North\n002,200,90,South\n")
    model = plan_model(analyze_request({"sources": ["Sales.csv"]}, tmp_path), "Analyze revenue and profit by region")
    from powerbi_agent.report import literal
    region = {"table": "Sales", "name": "Region"}
    revenue = {"table": "Sales", "name": "Total Revenue", "kind": "Measure"}
    margin = {"table": "Sales", "name": "Margin %", "kind": "Measure"}

    def visual(kind, title, x, y, w, h, **extra):
        return {"type": kind, "title": title, "question": title,
                "position": {"x": x, "y": y, "width": w, "height": h}, **extra}

    designs = [
        ("Contribution", 1000, 900, [
            visual("textbox", "Where is revenue concentrated?", 0, 0, 1000, 64,
                   text="Where is revenue concentrated?", text_style={"fontFamily": "Georgia", "fontSize": "26pt", "color": "#182B3A"}),
            visual("clusteredBarChart", "Regional contribution", 0, 88, 716, 548,
                   roles={"Category": [region], "Y": [revenue]}, sort=revenue, descending=True),
            visual("cardVisual", "Revenue", 744, 88, 256, 180, roles={"Data": [revenue]}, style={"card_outline": False}),
            visual("cardVisual", "Margin", 744, 296, 256, 180, roles={"Data": [margin]}, style={"card_outline": False}),
            visual("tableEx", "Supporting regional economics", 0, 664, 1000, 236,
                   roles={"Values": [region, revenue, margin]})]),
        ("Investigation", 1440, 810, [
            visual("slicer", "Focus region", 0, 0, 240, 810, roles={"Values": [region]},
                   objects={"data": [{"properties": {"mode": literal("Basic")}}]}),
            visual("textbox", "Review regional margins", 272, 0, 1168, 72,
                   text="Review regional margins", text_style={"fontFamily": "Segoe UI", "fontSize": "22pt", "color": "#182B3A"}),
            visual("tableEx", "Lowest margins first", 272, 100, 1168, 710,
                   roles={"Values": [region, margin, revenue]}, sort=margin)])]
    authored = []
    for name, width, height, elements in designs:
        plan = as_authored(deepcopy(report))
        plan.update(width=width, height=height)
        plan["pages"] = [{"name": identity(name), "title": name, "visuals": elements}]
        spec = {"project": name + ".pbip", "sources": ["Sales.csv"], "business_goal": name,
            "agent_mode": True, "analysis_brief": brief(plan), "model_plan": model, "report_plan": plan}
        state = build(spec, tmp_path, report_cli=OfflineCLI())
        assert any(v["check"] == "agent_analysis" and v["status"] == "passed" for v in state.validation_results)
        visuals = [read_json(p) for p in (tmp_path / (name + ".Report")).rglob("visual.json")]
        assert len(visuals) == len(elements)
        assert not any(v["visual"]["visualType"] == "pageNavigator" for v in visuals)
        assert sorted((v["position"]["x"], v["position"]["y"], v["position"]["width"], v["position"]["height"]) for v in visuals) == sorted(
            (v["position"]["x"], v["position"]["y"], v["position"]["width"], v["position"]["height"]) for v in elements)
        authored.append([v["visual"]["visualType"] for v in visuals])
    assert authored[0] != authored[1]


def test_duplicate_analytical_visuals_fail_agent_review(report, sales):
    report = as_authored(deepcopy(report))
    report["pages"][0]["visuals"].append(deepcopy(report["pages"][0]["visuals"][0]))
    assert validate_brief(brief(report), [sales.profile], report)["status"] == "failed"


def test_portable_skill_bundle_is_self_contained_and_excludes_local_artifacts(tmp_path):
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("pack_skill", root / "scripts/package_skill.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    target = tmp_path / "skill.zip"
    first = module.package(target)
    assert module.package(target) == first
    with ZipFile(target) as archive:
        names = archive.namelist()
        assert "powerbi-analyst/scripts/agent.py" in names
        assert "powerbi-analyst/runtime/powerbi_agent/schemas/analysis-brief.json" in names
        assert "powerbi-analyst/runtime/powerbi_agent/bootstrap.py" in names
        assert "powerbi-analyst/runtime/package-lock.json" in names
        assert not any(part in namestring.split('/') for namestring in names for part in ("output", ".git", "node_modules", ".venv", ".env"))
        archive.extractall(tmp_path / "unpacked")
    helper = tmp_path / "unpacked/powerbi-analyst/scripts/agent.py"
    result = subprocess.run([sys.executable, str(helper), "schemas"], capture_output=True, text=True, check=True, cwd=tmp_path)
    assert "analysis-brief" in json.loads(result.stdout)
    result = subprocess.run([sys.executable, str(helper), "where"], capture_output=True, text=True, check=True, cwd=tmp_path)
    assert Path(json.loads(result.stdout)["runtime"]).parent == helper.parents[1]


def test_design_system_is_required_and_must_not_be_the_preset(report, sales):
    plan = as_authored(deepcopy(report))
    assert validate_brief(brief(plan), [sales.profile], plan)["status"] == "passed"
    missing = deepcopy(plan)
    missing.pop("design_system")
    assert any("design_system" in e for e in validate_brief(brief(missing), [sales.profile], missing)["errors"])
    preset = deepcopy(plan)
    preset["theme"]["palette"].update(canvas="#F2F5F7", accent="#196A83")
    assert any("preset demo palette" in e for e in validate_brief(brief(preset), [sales.profile], preset)["errors"])


def test_multi_visual_page_without_panels_or_cards_fails(report, sales):
    plan = as_authored(deepcopy(report))
    plan["theme"]["definition"].pop("visualStyles")
    plan["pages"] = plan["pages"][:1]
    page = plan["pages"][0]
    for visual in page["visuals"]:
        visual.pop("container_objects", None)
        visual["style"] = {"background": False, "title_color": "#182B3A"}
    assert any("bare canvas" in e for e in validate_brief(brief(plan), [sales.profile], plan)["errors"])
    page["visuals"].insert(0, {"type": "shape", "title": "Content panel", "question": "Group the analysis", "layer": "background",
        "style": {"fill": "#FFFFFF", "outline": False}, "position": {"x": 16, "y": 150, "width": 1248, "height": 550}})
    assert validate_brief(brief(plan), [sales.profile], plan)["status"] == "passed"
