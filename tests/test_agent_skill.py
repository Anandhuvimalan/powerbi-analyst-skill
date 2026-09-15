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


def test_agent_mode_does_not_fall_back_to_bootstrap(tmp_path):
    with pytest.raises(BuildError, match="Agent mode requires"):
        build({"agent_mode": True, "project": "No.pbip", "sources": ["missing.csv"], "business_goal": "Analyze sales"}, tmp_path)
    assert not (tmp_path / "No.pbip").exists()
    assert not (tmp_path / ".powerbi-agent").exists()


def test_brief_requires_real_evidence_and_every_page(model, report, sales):
    good = brief(report)
    assert validate_brief(good, [sales.profile], report)["status"] == "passed"
    bad = deepcopy(good)
    bad["findings"][0]["evidence"][0]["column"] = "InventedTarget"
    assert validate_brief(bad, [sales.profile], report)["status"] == "failed"
    bad = deepcopy(good)
    bad["pages"] = []
    assert validate_brief(bad, [sales.profile], report)["status"] == "failed"


def test_agent_mode_preserves_distinct_authored_experiences(tmp_path, model, report):
    # Same source: two explicitly authored analytical purposes, not two recolored seeds.
    (tmp_path / "Sales.csv").write_text("OrderId,Revenue,Cost,Region\n001,100,60,North\n002,200,90,South\n")
    model = plan_model(analyze_request({"sources": ["Sales.csv"]}, tmp_path), "Analyze revenue and profit by region")
    authored = []
    for name, kind, roles in [
        ("Exceptions", "tableEx", {"Values": [{"table": "Sales", "name": "Region"}, {"table": "Sales", "name": "Margin %", "kind": "Measure"}]}),
        ("Contribution", "clusteredBarChart", {"Category": [{"table": "Sales", "name": "Region"}], "Y": [{"table": "Sales", "name": "Total Revenue", "kind": "Measure"}]})]:
        plan = deepcopy(report)
        plan["pages"] = [{"name": identity(name), "title": name, "visuals": [{"type": kind, "title": name,
            "question": "Which region should receive attention?", "roles": roles, "position": {"x": 32, "y": 160, "width": 1216, "height": 528}}]}]
        spec = {"project": name + ".pbip", "sources": ["Sales.csv"], "business_goal": name,
            "agent_mode": True, "analysis_brief": brief(plan), "model_plan": model, "report_plan": plan}
        state = build(spec, tmp_path, report_cli=OfflineCLI())
        assert any(v["check"] == "agent_analysis" and v["status"] == "passed" for v in state.validation_results)
        visuals = [read_json(p)["visual"]["visualType"] for p in (tmp_path / (name + ".Report")).rglob("visual.json")]
        assert kind in visuals
        authored.append(visuals)
    assert authored[0] != authored[1]


def test_duplicate_analytical_visuals_fail_agent_review(report, sales):
    report = deepcopy(report)
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
        assert "powerbi-analyst/runtime/package-lock.json" in names
        assert not any(part in namestring.split('/') for namestring in names for part in ("output", ".git", "node_modules", ".venv", ".env"))
        archive.extractall(tmp_path / "unpacked")
    helper = tmp_path / "unpacked/powerbi-analyst/scripts/agent.py"
    result = subprocess.run([sys.executable, str(helper), "schemas"], capture_output=True, text=True, check=True, cwd=tmp_path)
    assert "analysis-brief" in json.loads(result.stdout)
    result = subprocess.run([sys.executable, str(helper), "where"], capture_output=True, text=True, check=True, cwd=tmp_path)
    assert Path(json.loads(result.stdout)["runtime"]).parent == helper.parents[1]
