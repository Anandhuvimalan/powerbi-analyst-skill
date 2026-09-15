import datetime
import json
import sqlite3

import pytest
from openpyxl import Workbook

from powerbi_agent.analysis import discover, profile
from powerbi_agent.core import BuildError


def test_identifiers_nulls_and_duplicates_are_preserved(sales):
    assert sales.rows[0]["OrderId"] == "001"
    assert sales.rows[-1]["Revenue"] is None
    revenue = next(c for c in sales.profile["columns"] if c["name"] == "Revenue")
    assert revenue["nulls"] == 1
    assert revenue["maximum"] == 200
    duplicate = profile("D", sales.source, [sales.rows[0], sales.rows[0]])
    assert duplicate.profile["duplicate_rows"] == 1
    assert len(duplicate.rows) == 2


def test_csv_quoted_headers_and_numeric_keys(tmp_path):
    (tmp_path / "test.csv").write_text('CustomerId,"Customer, Name",Revenue\n001,"Anand, A",12.5\n002, Bob ,\n', encoding="utf-8")
    data = discover(["test.csv"], tmp_path)[0]
    assert data.rows[0]["CustomerId"] == "001"
    assert data.rows[1]["Customer, Name"] == "Bob"
    assert data.rows[1]["Revenue"] is None


def test_duplicate_headers_and_extra_cells_fail(tmp_path):
    (tmp_path / "duplicate.csv").write_text("X,X\n1,2\n")
    with pytest.raises(BuildError, match="headers"):
        discover(["duplicate.csv"], tmp_path)
    (tmp_path / "extra.csv").write_text("X\n1,2\n")
    with pytest.raises(BuildError, match="more values"):
        discover(["extra.csv"], tmp_path)


def test_excel_all_sheets_and_real_dates(tmp_path):
    book = Workbook()
    book.active.title = "Orders"
    book.active.append(["OrderDate", "Revenue"])
    book.active.append([datetime.date(2025, 1, 1), 10.2])
    book.create_sheet("People").append(["EmployeeId", "Department"])
    book["People"].append(["01", "Finance"])
    book.save(tmp_path / "book.xlsx")
    data = discover(["book.xlsx"], tmp_path)
    assert [d.name for d in data] == ["Orders", "People"]
    assert data[0].rows[0]["OrderDate"] == "2025-01-01"


def test_ambiguous_dates_and_timestamps_are_not_truncated():
    data = profile("D", {}, [{"When": "01/02/2025", "Timestamp": datetime.datetime(2025, 1, 1, 12, 15)}])
    assert all(c["data_type"] == "string" for c in data.profile["columns"])
    assert "12:15" in data.rows[0]["Timestamp"]


def test_json_union_columns_and_nested_data(tmp_path):
    (tmp_path / "data.json").write_text(json.dumps([{"A": 1}, {"B": 2}]))
    data = discover(["data.json"], tmp_path)[0]
    assert data.rows == [{"A": 1, "B": None}, {"A": None, "B": 2}]
    with pytest.raises(BuildError, match="nested"):
        profile("D", {}, [{"Object": {"nested": True}}])


def test_row_budget_never_claims_sample_uniqueness(tmp_path):
    (tmp_path / "large.csv").write_text("Id\n1\n2\n3\n")
    with pytest.raises(BuildError, match="max_rows"):
        discover(["large.csv"], tmp_path, max_rows=2)


def test_sqlite_readonly_and_explicit_table(tmp_path):
    conn = sqlite3.connect(tmp_path / "data.db")
    conn.execute("CREATE TABLE Sales (Id TEXT, Revenue REAL)")
    conn.execute("INSERT INTO Sales VALUES ('01', 15)")
    conn.commit()
    conn.close()
    data = discover([{"kind": "sqlite", "path": "data.db", "table": "Sales"}], tmp_path)
    assert data[0].rows[0]["Revenue"] == 15
    with pytest.raises(BuildError, match="table"):
        discover([{"kind": "sqlite", "path": "data.db", "table": "Sales; DROP TABLE Sales"}], tmp_path)


def test_duplicate_table_names_and_empty_sources_fail(tmp_path):
    (tmp_path / "empty.csv").write_text("Id,Name\n")
    with pytest.raises(BuildError, match="no data"):
        discover(["empty.csv"], tmp_path)


def test_nonfinite_values_fail():
    with pytest.raises(BuildError, match="Non-finite"):
        profile("D", {}, [{"Value": float("inf")}])
