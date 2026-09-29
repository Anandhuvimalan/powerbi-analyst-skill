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
                roles={"Data": [metric]}, objects=value_style, style={"card_outline": False}, z_index=7, tab_order=2),
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
    assert card["visual"]["objects"] == {**value_style, "outline": [{"selector": {"id": "default"}, "properties": {"show": literal(False)}}]}
    assert card["visual"]["visualContainerObjects"] == {"title": [{"properties": {"show": literal(True), "text": literal("Single compact metric")}}]}
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
    assert any("no authored fill" in e for e in validate_report(plan, model)["errors"])
    plan["pages"][0]["visuals"][0]["style"] = {"fill": "#FFFFFF", "outline": False}
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


def test_authored_title_style_and_panel_compile_to_native_objects(tmp_path, report, model):
    metric = report["pages"][0]["visuals"][0]["roles"]["Data"][0]
    plan = canvas(report, [
        element("shape", "Revenue panel", 0, 0, 960, 900, layer="background",
                style={"fill": "#FFFFFF", "outline": "#E4E0D8", "outline_width": 1, "shape": "rectangleRounded", "corner": 14}),
        element("clusteredBarChart", "Revenue by region", 16, 16, 928, 868, roles={"Values": [metric]},
                subtitle="Sorted by revenue", style={"background": False, "title_color": "#2B2118", "title_size": 13})])
    plan["style_defaults"] = {"*": {"header_icons": False, "padding": 8}}
    assert validate_report(plan, model)["status"] == "passed"
    PbirWriter().apply(tmp_path, "Model.SemanticModel", plan)
    visuals = {v["visual"]["visualType"]: v["visual"] for v in (read_json(p) for p in tmp_path.rglob("visual.json"))}
    shape = visuals["shape"]["objects"]
    assert shape["shape"][0]["properties"]["roundEdge"] == {"expr": {"Literal": {"Value": "14L"}}}
    assert shape["fill"][0]["properties"]["fillColor"] == color("#FFFFFF")
    assert shape["outline"][0]["properties"]["lineColor"] == color("#E4E0D8")
    assert "title" not in visuals["shape"].get("visualContainerObjects", {})
    chart = visuals["clusteredBarChart"]["visualContainerObjects"]
    assert chart["title"][0]["properties"]["text"] == literal("Revenue by region")
    assert chart["title"][0]["properties"]["fontColor"] == color("#2B2118")
    assert chart["subTitle"][0]["properties"]["text"] == literal("Sorted by revenue")
    assert chart["background"] == [{"properties": {"show": literal(False)}}]
    assert chart["visualHeader"] == [{"properties": {"show": literal(False)}}]
    assert chart["padding"][0]["properties"]["left"] == literal(8)


def test_double_encoded_integer_shape_property_is_rejected(report, model):
    bad = {"shape": [{"selector": {"id": "default"}, "properties": {"roundEdge": literal(12)}}],
           "fill": [{"selector": {"id": "default"}, "properties": {"fillColor": color("#FFFFFF")}}]}
    plan = canvas(report, [element("shape", "Panel", 0, 0, 960, 900, layer="background", objects=bad)])
    assert any("integer property" in e for e in validate_report(plan, model)["errors"])


def test_slicers_need_a_chosen_style_and_can_sync(tmp_path, report, model):
    region = {"table": "Sales", "name": "Region"}
    slicer = element("slicer", "Region", 0, 0, 240, 76, roles={"Values": [region]})
    plan = canvas(report, [slicer])
    assert any("slicer style" in e for e in validate_report(plan, model)["errors"])
    slicer["slicer"] = {"mode": "Dropdown", "single_select": False, "select_all": True, "sync_group": "region"}
    slicer["style"] = {"title_color": "#2B2118"}
    assert validate_report(plan, model)["status"] == "passed"
    PbirWriter().apply(tmp_path, "Model.SemanticModel", plan)
    visual = read_json(next(tmp_path.rglob("visual.json")))["visual"]
    assert visual["objects"]["data"] == [{"properties": {"mode": literal("Dropdown")}}]
    assert visual["objects"]["header"][0]["properties"]["text"] == literal("Region")
    assert visual["objects"]["header"][0]["properties"]["fontColor"] == color("#2B2118")
    assert visual["objects"]["selection"][0]["properties"]["selectAllCheckboxEnabled"] == literal(True)
    assert visual["visualContainerObjects"]["title"] == [{"properties": {"show": literal(False)}}]
    assert visual["syncGroup"] == {"groupName": "region", "fieldChanges": True, "filterChanges": True}


def test_unsynced_repeated_slicers_and_missing_navigation_are_flagged(report, model):
    region = {"table": "Sales", "name": "Region"}
    plan = canvas(report, [element("slicer", "Region", 0, 0, 240, 60, roles={"Values": [region]}, slicer={"mode": "Dropdown"})])
    second = deepcopy(plan["pages"][0])
    second["name"] = identity("second")
    plan["pages"].append(second)
    warnings = validate_report(plan, model)["warnings"]
    assert any("sync_group" in w for w in warnings)
    assert any("navigation" in w for w in warnings)


def test_undesigned_data_visual_is_rejected(report, model):
    metric = report["pages"][0]["visuals"][0]["roles"]["Data"][0]
    plan = canvas(report, [element("tableEx", "Evidence", 0, 0, 960, 900, roles={"Values": [metric]})])
    plan["theme"]["definition"].pop("visualStyles")
    assert any("no authored container design" in e for e in validate_report(plan, model)["errors"])
    plan["style_defaults"] = {"*": {"background": "#FFFFFF", "radius": 10}}
    assert validate_report(plan, model)["status"] == "passed"


def test_background_layers_render_at_nonnegative_z_below_content(tmp_path, report, model):
    plan = canvas(report, [
        element("textbox", "Title", 20, 20, 400, 60, text="Evidence"),
        element("shape", "Band", 0, 0, 960, 120, layer="background", style={"fill": "#2B2118", "outline": False})])
    assert validate_report(plan, model)["status"] == "passed"
    PbirWriter().apply(tmp_path, "Model.SemanticModel", plan)
    z = {v["visual"]["visualType"]: v["position"]["z"] for v in (read_json(p) for p in tmp_path.rglob("visual.json"))}
    assert 0 <= z["shape"] < z["textbox"]
    plan["pages"][0]["visuals"][1]["z_index"] = -1000
    assert any("negative" in e for e in validate_report(plan, model)["errors"])
    plan["pages"][0]["visuals"][1]["z_index"] = 5000
    assert any("stack below" in e for e in validate_report(plan, model)["errors"])


def test_cards_must_decide_their_inner_outline(report, model):
    metric = report["pages"][0]["visuals"][0]["roles"]["Data"][0]
    plan = canvas(report, [element("cardVisual", "Revenue", 0, 0, 300, 120, roles={"Data": [metric]})])
    assert any("inner outline" in e for e in validate_report(plan, model)["errors"])
    plan["style_defaults"] = {"cardVisual": {"card_outline": False}}
    assert validate_report(plan, model)["status"] == "passed"


def test_field_label_becomes_display_name(tmp_path, report, model):
    plan = canvas(report, [element("tableEx", "Products", 0, 0, 960, 900,
        roles={"Values": [{"table": "Sales", "name": "ProductName", "label": "Product"}]})])
    PbirWriter().apply(tmp_path, "Model.SemanticModel", plan)
    projection = read_json(next(tmp_path.rglob("visual.json")))["visual"]["query"]["queryState"]["Values"]["projections"][0]
    assert projection["displayName"] == "Product"


def test_button_slicer_compiles_designed_states_in_desktop_encoding(tmp_path, report, model):
    region = {"table": "Sales", "name": "Region"}
    buttons = element("advancedSlicerVisual", "Region", 0, 0, 520, 60, roles={"Values": [region]}, show_title=False,
        slicer={"columns": 4, "rows": 1, "corner": 8, "tile_fill": "#FFFFFF", "hover_fill": "#EFE7DC", "selected_fill": "#8A4B2A",
                "tile_outline": "#D9D0C1", "selected_outline": False, "tile_text": "#2B2118", "selected_text": "#FFFFFF",
                "text_align": "center", "sync_group": "region"})
    plan = canvas(report, [buttons])
    assert validate_report(plan, model)["status"] == "passed"
    PbirWriter().apply(tmp_path, "Model.SemanticModel", plan)
    visual = read_json(next(tmp_path.rglob("visual.json")))["visual"]
    fills = {(e["selector"]["id"], "data" in e["selector"]): e["properties"] for e in visual["objects"]["fillCustom"]}
    assert fills[("selection:selected", True)] == {"fillColor": color("#8A4B2A")}
    assert fills[("interaction:hover", True)] == {"fillColor": color("#EFE7DC")}
    assert fills[("default", False)]["show"] == literal(True)
    assert visual["objects"]["layout"][0]["properties"]["columnCount"] == literal(4, integer=True)
    assert visual["objects"]["shapeCustomRectangle"][0]["properties"]["rectangleRoundedCurve"] == literal(8, integer=True)
    values = {(e["selector"]["id"], "data" in e["selector"]): e["properties"] for e in visual["objects"]["value"]}
    assert values[("selection:selected", True)] == {"fontColor": color("#FFFFFF")}
    assert values[("selection:selected", False)] == {"bold": literal(True)}
    assert "header" not in visual["objects"] and "data" not in visual["objects"]
    assert visual["visualContainerObjects"]["title"] == [{"properties": {"show": literal(False)}}]
    assert visual["syncGroup"]["groupName"] == "region"


def test_tab_slicer_uses_accent_bar_states(tmp_path, report, model):
    region = {"table": "Sales", "name": "Region"}
    plan = canvas(report, [element("advancedSlicerVisual", "Region", 0, 0, 520, 60, roles={"Values": [region]},
        slicer={"columns": 4, "tile_fill": False, "tile_outline": False, "accent": "#8A4B2A"})])
    assert validate_report(plan, model)["status"] == "passed"
    PbirWriter().apply(tmp_path, "Model.SemanticModel", plan)
    bars = {(e["selector"]["id"], "data" in e["selector"]): e["properties"] for e in read_json(next(tmp_path.rglob("visual.json")))["visual"]["objects"]["accentBar"]}
    assert bars[("default", False)] == {"show": literal(False)}
    assert bars[("selection:selected", False)]["position"] == literal("Bottom")
    assert bars[("selection:selected", True)] == {"color": color("#8A4B2A")}


def test_dated_slicer_designs_are_rejected(report, model):
    region = {"table": "Sales", "name": "Region"}
    plan = canvas(report, [element("advancedSlicerVisual", "Region", 0, 0, 520, 60, roles={"Values": [region]}, slicer={"columns": 4})])
    assert any("selected state" in e for e in validate_report(plan, model)["errors"])
    plan = canvas(report, [element("slicer", "Region", 0, 0, 240, 200, roles={"Values": [region]}, slicer={"mode": "VerticalList"})])
    assert any("look dated" in e for e in validate_report(plan, model)["errors"])
    plan["theme"]["definition"].pop("visualStyles")
    plan["pages"][0]["visuals"][0]["slicer"] = {"mode": "Dropdown"}
    plan["pages"][0]["visuals"][0]["position"]["height"] = 84
    assert any("bare legacy dropdown" in e for e in validate_report(plan, model)["errors"])
    plan["pages"][0]["visuals"][0]["style"] = {"background": "#FFFFFF", "border": "#D9D0C1", "radius": 8}
    assert validate_report(plan, model)["status"] == "passed"


def test_page_navigator_must_be_designed_and_uses_plain_state_ids(tmp_path, report, model):
    nav = element("pageNavigator", "Pages", 0, 0, 240, 40)
    plan = canvas(report, [nav])
    assert any("navigator buttons" in e for e in validate_report(plan, model)["errors"])
    nav["navigator"] = {"tile_fill": "#2B2118", "selected_fill": "#3A2E25", "tile_text": "#B8AC9C", "selected_text": "#FFFFFF", "corner": 6}
    assert validate_report(plan, model)["status"] == "passed"
    PbirWriter().apply(tmp_path, "Model.SemanticModel", plan)
    objects = read_json(next(tmp_path.rglob("visual.json")))["visual"]["objects"]
    fills = {e["selector"]["id"]: e["properties"] for e in objects["fill"]}
    assert fills["selected"]["fillColor"] == color("#3A2E25") and "data" not in objects["fill"][0]["selector"]
    assert {e["selector"]["id"]: e["properties"] for e in objects["text"]}["selected"]["bold"] == literal(True)
