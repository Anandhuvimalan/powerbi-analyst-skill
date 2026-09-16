"""The compiler must preserve authored compositions without injecting a template."""
from copy import deepcopy
from pathlib import Path

from powerbi_agent.agent_workflow import validate_brief
from powerbi_agent.cli import main
from powerbi_agent.core import identity, read_json
from powerbi_agent.report import PbirWriter, color, literal
from powerbi_agent.validation import validate_report


def canvas(report, visuals):
    return {"composition": "authored", "width": 960, "height": 900,
            "theme": deepcopy(report["theme"]), "pages": [
                {"name": identity("authored"), "title": "Decision workspace", "visuals": visuals}]}


def element(kind, title, x, y, w, h, **extra):
    return {"type": kind, "title": title, "question": title,
            "position": {"x": x, "y": y, "width": w, "height": h}, **extra}


def test_full_canvas_and_styles_are_owned_by_author(tmp_path, report, model):
    metric = report["pages"][0]["visuals"][0]["roles"]["Data"][0]
    value_style = {"value": [{"selector": {"id": "default"}, "properties": {"fontSize": literal(18)}}]}
    plan = canvas(report, [
        element("textbox", "Editorial heading", 0, 0, 700, 75, text="A decision, not a generic overview",
                text_style={"fontFamily": "Georgia", "fontSize": "26pt", "color": "#182B3A"}),
        element("cardVisual", "Single compact metric", 730, 0, 230, 90,
                roles={"Data": [metric]}, objects=value_style, z_index=7, tab_order=2),
        element("tableEx", "Decision evidence", 0, 100, 960, 800, roles={"Values": [metric]})])
    plan["settings"] = {"useEnhancedTooltips": True}
    plan["pages"][0]["background"] = "#FFFDF7"
    assert validate_report(plan, model)["status"] == "passed"
    PbirWriter().apply(tmp_path, "Model.SemanticModel", plan)
    visuals = [read_json(p) for p in tmp_path.rglob("visual.json")]
    assert len(visuals) == 3  # no hidden title, subtitle or navigation
    assert not any(v["visual"]["visualType"] == "pageNavigator" for v in visuals)
    card = next(v for v in visuals if v["visual"]["visualType"] == "cardVisual")
    assert card["position"] == {"x": 730, "y": 0, "width": 230, "height": 90, "z": 7, "tabOrder": 2}
    assert card["visual"]["objects"] == value_style
    assert "visualContainerObjects" not in card["visual"]
    heading = next(v for v in visuals if v["visual"]["visualType"] == "textbox")
    assert "query" not in heading["visual"]
    assert heading["visual"]["objects"]["general"][0]["properties"]["paragraphs"][0]["textRuns"][0]["textStyle"]["fontFamily"] == "Georgia"
    page = read_json(next(tmp_path.rglob("page.json")))
    assert page["height"] == 900
    assert page["objects"]["background"][0]["properties"]["color"] == color("#FFFDF7")


def test_no_navigation_even_for_multiple_pages(tmp_path, report):
    plan = canvas(report, [element("textbox", "Page note", 10, 10, 400, 60, text="First")])
    second = deepcopy(plan["pages"][0])
    second["name"] = identity("second")
    plan["pages"].append(second)
    PbirWriter().apply(tmp_path, "Model.SemanticModel", plan)
    assert len(list(tmp_path.rglob("visual.json"))) == 2


def test_background_layers_allow_grouping_but_never_hide_data_overlap(report, model):
    plan = canvas(report, [
        element("shape", "Section background", 0, 0, 960, 900, layer="background"),
        element("textbox", "Title", 20, 20, 400, 60, text="Evidence")])
    assert validate_report(plan, model)["status"] == "passed"
    plan["pages"][0]["visuals"].append(element("textbox", "Overlapping text", 20, 20, 400, 60))
    assert any("overlap" in e for e in validate_report(plan, model)["errors"])
    plan["pages"][0]["visuals"][0]["type"] = "tableEx"
    assert any("decorative" in e for e in validate_report(plan, model)["errors"])


def test_plan_does_not_supply_or_overwrite_a_report_template(tmp_path):
    source = tmp_path / "sales.csv"
    source.write_text("Revenue,Region\n100,North\n200,South\n")
    args = ["plan", "--project", str(tmp_path / "Fresh.pbip"), "--data", str(source), "--goal", "Regional revenue", "--artifacts", str(tmp_path / "plans")]
    assert main(args) == 0
    directory = tmp_path / "plans"
    assert (directory / "design-context.json").exists()
    assert not (directory / "report-plan.json").exists()
    (directory / "report-plan.json").write_text('{"authored":true}')
    assert main(args + ["--bootstrap"]) == 0
    assert read_json(directory / "report-plan.json") == {"authored": True}
    assert read_json(directory / "bootstrap-report-plan.json")["composition"] == "bootstrap"


def test_reasoner_gets_evidence_and_brand_without_seed_design(tmp_path, model, report, sales, monkeypatch):
    from powerbi_agent.reasoning import CommandReasoningAdapter
    captured = {}

    def run(command, **kwargs):
        captured.update(read_json(Path(command[-1])))
        return {"model_plan": model, "report_plan": {}}

    monkeypatch.setattr("powerbi_agent.reasoning.run_json", run)
    CommandReasoningAdapter(["planner"]).plan([sales], "Investigate regional results", model, report, tmp_path, brand={"primary_color": "#384C44"})
    assert "baseline_report_plan" not in captured
    assert captured["brand"]["primary_color"] == "#384C44"
    assert captured["dataset_profiles"] == [sales.profile]


def test_bootstrap_is_rejected_by_agent_review(report, sales):
    result = validate_brief({}, [sales.profile], report)
    assert any("bootstrap" in e for e in result["errors"])
