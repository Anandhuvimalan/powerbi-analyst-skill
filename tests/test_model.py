from copy import deepcopy

from powerbi_agent.analysis import profile
from powerbi_agent.model import TmdlWriter, mq, source_m
from powerbi_agent.planning import plan_model
from powerbi_agent.validation import validate_model


def test_entity_and_date_relationships(model):
    assert {t["name"] for t in model["tables"]} == {"Sales", "DimProduct", "DimDate"}
    assert all(r["direction"] == "oneDirection" for r in model["relationships"])
    assert validate_model(model)["status"] == "passed"
    date = next(t for t in model["tables"] if t.get("is_date"))
    assert date["columns"][0]["is_key"]
    assert "Date.StartOfYear" in date["m"]


def test_conflicting_dimension_attributes_not_arbitrarily_deduplicated(sales):
    sales.rows[2]["ProductName"] = "Changed name"
    model = plan_model([sales], "sales")
    assert "DimProduct" not in {t["name"] for t in model["tables"]}
    assert any("conflict" in reason for reason in model["assumptions"])


def test_existing_dimension_with_numeric_attributes(sales):
    dim = profile("Product", {"kind": "csv", "path": "C:/product.csv"}, [{"ProductId": "P1", "Name": "Lamp", "Weight": 5}, {"ProductId": "P2", "Name": "Book", "Weight": 2}])
    model = plan_model([sales, dim], "sales")
    assert any(r["to_table"] == "Product" for r in model["relationships"])
    assert not any(m["name"] == "Total Weight" for m in model["measures"])


def test_unmatched_keys_do_not_create_relationship(sales):
    dim = profile("Product", {"kind": "csv", "path": "C:/product.csv"}, [{"ProductId": "P9", "Name": "Unknown"}])
    model = plan_model([sales, dim], "sales")
    assert not any(r["to_table"] == "Product" for r in model["relationships"])


def test_advanced_dax_is_contextual(model, sales):
    measures = {m["name"]: m["expression"] for m in model["measures"]}
    assert measures["Margin %"] == "DIVIDE([Total Profit], [Total Revenue])"
    assert "DATEADD('DimDate'[Date], -1, YEAR)" in measures["Previous Year"]
    assert "ALLSELECTED" in measures["Running Total"]
    minimal = plan_model([sales], "Revenue summary")
    assert "YoY %" not in {m["name"] for m in minimal["measures"]}
    assert not any("Retention" in m["name"] for m in minimal["measures"])


def test_extra_date_roles_are_inactive(sales):
    raw = [{**r, "ShipDate": r["OrderDate"]} for r in sales.rows]
    data = profile(sales.name, sales.source, raw)
    plan = plan_model([data], "monthly revenue")
    relations = [r for r in plan["relationships"] if r["to_table"] == "DimDate"]
    assert sum(r["active"] for r in relations) == 1


def test_m_preserves_nulls_and_quotes_source(sales):
    data = source_m({**sales.source, "path": 'C:/a "quoted" #(folder)/sales.csv'}, sales.profile["columns"])
    assert '""quoted""' in data
    assert "#(#)(folder)" in data
    assert '"OrderId", type text' in data
    assert "Table.ReplaceValue" in data
    assert "otherwise 0" not in data
    assert "Text.Trim" not in data


def test_tmdl_real_model_files_and_advanced_plan(tmp_path, model):
    model["expressions"] = [{"name": "SourceYear", "expression": "2025 meta [IsParameterQuery=true, Type=\"Number\", IsParameterQueryRequired=true]"}]
    model["roles"] = [{"name": "North", "filters": {"Sales": "[Region] = \"North\""}}]
    model["calculation_groups"] = [{"name": "Time Calculation", "precedence": 20, "items": [{"name": "Current", "expression": "SELECTEDMEASURE()"}]}]
    TmdlWriter().apply(tmp_path, model)
    text = "\n".join(p.read_text() for p in tmp_path.rglob("*.tmdl"))
    assert "createOrReplace" not in text
    assert "\tpartition 'Sales' = m" in text
    assert "calculationItem 'Current' = SELECTEDMEASURE()" in text
    assert "role 'North'" in text


def test_invalid_relationships_missing_refs_and_ambiguity(model):
    changed = deepcopy(model)
    changed["relationships"][0]["to_column"] = "Missing"
    assert validate_model(changed)["status"] == "failed"
    changed = deepcopy(model)
    changed["measures"][0]["expression"] = "SUM('Ghost'[Money])"
    assert any("Missing DAX" in e for e in validate_model(changed)["errors"])
    changed = deepcopy(model)
    changed["relationships"].append({**changed["relationships"][0], "name": "duplicate_pair"})
    assert any("Multiple active" in e for e in validate_model(changed)["errors"])
