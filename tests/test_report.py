from copy import deepcopy

import pytest

from powerbi_agent.analysis import profile
from powerbi_agent.core import BuildError, read_json
from powerbi_agent.planning import plan_model
from powerbi_agent.report import PbirWriter, contrast, grid, plan_report, theme_for
from powerbi_agent.validation import cli_result, validate_report


def test_report_primary_metric_and_bindings(report, model):
    assert validate_report(report, model)["status"] == "passed"
    first = report["pages"][0]["visuals"][0]
    assert first["roles"]["Data"][0]["name"] == "Total Revenue"
    assert any(v["type"] == "lineChart" for p in report["pages"] for v in p["visuals"])


def test_domain_and_pages_change_for_hr():
    data = profile("Employees", {"kind": "csv", "path": "C:/hr.csv"}, [
        {"EmployeeId": "1", "Department": "IT", "Status": "Active"},
        {"EmployeeId": "2", "Department": "HR", "Status": "Left"}])
    model = plan_model([data], "Workforce headcount by department")
    report = plan_report(model, "Workforce headcount by department")
    assert model["domain"] == "hr"
    assert len(report["pages"]) <= 2
    assert not any(v["type"] == "lineChart" for p in report["pages"] for v in p["visuals"])
    assert "revenue" not in str(report).lower()


@pytest.mark.parametrize("categories,equivalent", [(["A", "B", "C"], True), (["A", "A", "B"], False)])
def test_duplicate_entity_groupings_require_proven_equivalence(categories, equivalent):
    data = profile("Sales", {"kind": "csv", "path": "C:/sales.csv"}, [
        {"OrderId": str(i), "ProductId": f"P{i}", "ProductName": f"Product {i}", "ProductCategory": category, "Revenue": "100"}
        for i, category in enumerate(categories)])
    model = plan_model([data], "Revenue by product and category")
    report = plan_report(model, "Revenue by product and category detailed analysis")
    bindings = [b["name"] for p in report["pages"] for v in p["visuals"] for fields in v["roles"].values() for b in fields]
    assert "ProductName" in bindings
    assert ("ProductCategory" not in bindings) == equivalent


@pytest.mark.parametrize("count", [1, 2, 3, 4, 6])
def test_grid_stays_inside_canvas(count):
    cells = grid(count)
    assert len(cells) == count
    assert all(c["x"] >= 32 and c["x"] + c["width"] <= 1248 and c["y"] + c["height"] <= 688 for c in cells)


def test_brand_palette_contrast_and_errors():
    palette = theme_for("sales", {"primary_color": "#AB1267"})
    assert palette["definition"]["dataColors"][0] == "#AB1267"
    assert contrast(palette["palette"]["ink"], palette["palette"]["surface"]) >= 4.5
    with pytest.raises(BuildError, match="hex"):
        theme_for("sales", {"primary_color": "red"})


def test_overlap_missing_binding_and_clipped_card_fail(report, model):
    bad = deepcopy(report)
    bad["pages"][0]["visuals"][1]["position"] = bad["pages"][0]["visuals"][0]["position"]
    assert any("overlap" in e for e in validate_report(bad, model)["errors"])
    bad = deepcopy(report)
    bad["pages"][0]["visuals"][0]["roles"]["Data"][0]["name"] = "Missing"
    assert any("binding" in e for e in validate_report(bad, model)["errors"])
    bad["pages"][0]["visuals"][0]["position"]["height"] = 45
    assert any("Card" in e for e in validate_report(bad, model)["warnings"])


def test_pbir_resources_roles_navigation_and_drillthrough(tmp_path, model):
    plan = plan_report(model, "products regional detailed analysis with drill through")
    PbirWriter().apply(tmp_path, "Demo.SemanticModel", plan)
    report = read_json(tmp_path / "definition/report.json")
    resource = report["resourcePackages"][0]["items"][0]
    theme = read_json(tmp_path / "StaticResources/RegisteredResources" / resource["path"])
    assert theme["name"] == resource["name"] == report["themeCollection"]["customTheme"]["name"]
    visuals = [read_json(p) for p in tmp_path.rglob("visual.json")]
    assert any(v["visual"]["visualType"] == "pageNavigator" for v in visuals)
    card = next(v for v in visuals if v["visual"]["visualType"] == "cardVisual")
    assert "Data" in card["visual"]["query"]["queryState"]
    drill = next(read_json(p) for p in tmp_path.rglob("page.json") if read_json(p).get("pageBinding"))
    assert drill["pageBinding"]["parameters"][0]["boundFilter"] == drill["filterConfig"]["filters"][0]["name"]


def test_cli_grouped_diagnostics_and_missing_schema_are_not_false_passes():
    failed = cli_result({"status": "pending", "remote_schema": True, "result": {"data": {"result": "failed", "errorCount": 1,
        "diagnostics": {"BAD": {"severity": "error", "items": [{"message": "Invalid binding"}]}}}}})
    assert failed["status"] == "failed"
    warning = cli_result({"status": "pending", "remote_schema": True, "result": {"data": {"diagnostics": {
        "PBIR_SCHEMA_UNREACHABLE": {"severity": "warning", "items": [{"message": "Offline"}]}}}}})
    assert warning["schema_complete"] is False
