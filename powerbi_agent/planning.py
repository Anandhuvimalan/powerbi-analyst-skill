"""Conservative bootstrap planner. Full AI-authored plans use the same executor."""
from __future__ import annotations

from copy import deepcopy

from .analysis import Dataset, words
from .core import identity
from .model import date_m, dimension_m, ref, source_m, tq


def domain_for(datasets: list[Dataset], goal: str) -> str:
    text = " ".join([goal] + [c["name"] for d in datasets for c in d.profile["columns"]]).lower()
    scores = {"sales": ["revenue", "order", "product", "sales"], "hr": ["employee", "attrition", "workforce", "salary"],
              "finance": ["expense", "budget", "cash flow", "ledger"], "marketing": ["campaign", "conversion", "lead", "click"]}
    ranked = [(sum(token in text for token in tokens), name) for name, tokens in scores.items()]
    score, name = max(ranked)
    return name if score else "general"


def plan_model(datasets: list[Dataset], goal: str) -> dict:
    plan = {"tables": [], "measures": [], "relationships": [], "expressions": [], "calculation_groups": [], "roles": [],
            "assumptions": ["Column meaning is inferred conservatively; use an agent-authored model_plan for domain rules.",
              "Nulls and duplicate fact rows are preserved. No imputation or outlier removal is justified automatically.",
              "Calculated columns, RLS and calculation groups are created only through an explicit justified plan."],
            "domain": domain_for(datasets, goal)}
    for data in datasets:
        cols = deepcopy(data.profile["columns"])
        numeric = [c for c in cols if c["role"] == "numeric"]
        event_key = any(words(c["name"]) in {"orderid", "transactionid", "eventid"} for c in cols)
        additive_names = {"revenue", "salesamount", "cost", "profit", "quantity", "units", "expense", "spend", "clicks", "impressions", "leads", "conversions"}
        entity_key = any(c["role"] == "key" and c["unique"] for c in cols)
        fact = event_key or any(words(c["name"]) in additive_names for c in numeric) or (bool(numeric) and not entity_key)
        for col in cols:
            col["hidden"] = col["role"] == "key"
            if words(col["name"]) in {"country", "city", "state", "postalcode"}:
                col["category"] = {"country": "Country", "city": "City", "state": "StateOrProvince", "postalcode": "PostalCode"}[words(col["name"])]
        plan["tables"].append({"name": data.name, "kind": "fact" if fact else "dimension", "columns": cols,
                               "m": source_m(data.source, cols), "source": data.source})
    # Relationships require same-name keys, exact type match, full-set membership and a unique non-null one side.
    by_name = {d.name: d for d in datasets}
    used_pairs = set()
    for fact in list(plan["tables"]):
        if fact["kind"] != "fact":
            continue
        data = by_name[fact["name"]]
        for key in [c for c in fact["columns"] if c["role"] == "key"]:
            values = {r[key["name"]] for r in data.rows if r[key["name"]] is not None}
            candidates = []
            for dim in plan["tables"]:
                if dim["name"] == fact["name"] or dim["kind"] != "dimension" or dim["name"] not in by_name:
                    continue
                col = next((c for c in dim["columns"] if c["name"] == key["name"] and c.get("unique") and c["data_type"] == key["data_type"]), None)
                if col and values <= {r[col["name"]] for r in by_name[dim["name"]].rows}:
                    candidates.append(dim)
            if len(candidates) == 1:
                dim = candidates[0]
                pair = (fact["name"], dim["name"])
                add_relationship(plan, fact["name"], key["name"], dim["name"], key["name"], pair not in used_pairs)
                used_pairs.add(pair)
    # Extract real entities only when attributes functionally depend on an observed natural key.
    for fact in list(plan["tables"]):
        if fact["kind"] != "fact":
            continue
        data = by_name[fact["name"]]
        for entity in ("Product", "Customer", "Employee", "Campaign", "Region", "Department"):
            key = next((c for c in fact["columns"] if words(c["name"]) in {words(entity) + "id", words(entity) + "key"}), None)
            if not key or key["nulls"] or any(r["from_table"] == fact["name"] and r["from_column"] == key["name"] for r in plan["relationships"]):
                continue
            attrs = [c for c in fact["columns"] if c["role"] == "category" and words(c["name"]).startswith(words(entity))]
            if not attrs:
                continue
            selected = [key] + attrs
            mapping = {}
            conflict = False
            for row in data.rows:
                value = tuple(row[c["name"]] for c in selected)
                if row[key["name"]] in mapping and mapping[row[key["name"]]] != value:
                    conflict = True
                    break
                mapping[row[key["name"]]] = value
            if conflict:
                plan["assumptions"].append(f"{entity} dimension skipped: attributes conflict for a key; history/grain needs an explicit rule.")
                continue
            name = "Dim" + entity
            if any(t["name"].casefold() == name.casefold() for t in plan["tables"]):
                name = fact["name"] + "_" + name
            dimcols = deepcopy(selected)
            for col in dimcols:
                col["hidden"] = col["name"] == key["name"]
                col["nulls"] = 0
                col["unique"] = col["name"] == key["name"]
                # Functional dependency was proven above. Equal observed cardinality
                # then proves these attributes partition the entity rows identically.
                if col["role"] == "category" and col["distinct"] == len(mapping):
                    col["grouping_equivalence"] = name + ":entity"
            plan["tables"].append({"name": name, "kind": "dimension", "columns": dimcols,
                "m": dimension_m(fact["name"], [c["name"] for c in selected], key["name"]),
                "derived_from": fact["name"], "key": key["name"]})
            for col in attrs:
                col["hidden"] = True
            add_relationship(plan, fact["name"], key["name"], name, key["name"])
    dates = [(t["name"], c["name"]) for t in plan["tables"] if t["kind"] == "fact" for c in t["columns"] if c["role"] == "date" and c["minimum"]]
    if dates and not any(t["name"].casefold() == "dimdate" for t in plan["tables"]):
        datecols = [{"name": n, "data_type": typ, "role": role, "hidden": n == "MonthNumber"} for n, typ, role in [
            ("Date", "dateTime", "date"), ("Year", "int64", "category"), ("Quarter", "string", "category"),
            ("MonthNumber", "int64", "category"), ("Month", "string", "category"), ("YearMonth", "string", "category")]]
        datecols[0].update(is_key=True, unique=True, nulls=0)
        datecols[4]["sort_by"] = "MonthNumber"
        plan["tables"].append({"name": "DimDate", "kind": "dimension", "is_date": True, "columns": datecols, "m": date_m(dates),
            "hierarchies": [{"name": "Calendar", "levels": ["Year", "Quarter", "Month", "Date"]}]})
        seen = set()
        for table, col in dates:
            add_relationship(plan, table, col, "DimDate", "Date", table not in seen)
            seen.add(table)
    create_measures(plan, goal)
    return plan


def add_relationship(plan, ft, fc, tt, tc, active=True):
    plan["relationships"].append({"name": identity(ft, fc, tt, tc), "from_table": ft, "from_column": fc,
                                  "to_table": tt, "to_column": tc, "active": active, "direction": "oneDirection"})


def create_measures(plan: dict, goal: str) -> None:
    goal = goal.lower()
    facts = [t for t in plan["tables"] if t["kind"] == "fact"]
    for table in facts or plan["tables"][:1]:
        name = table["name"]
        prefix = name + " " if len(facts) > 1 else ""
        created = {}

        def add(label, expr, reason, fmt="#,##0", check=None):
            final = prefix + label
            plan["measures"].append({"table": name, "name": final, "expression": expr, "format": fmt,
                "reason": reason, "folder": "Time intelligence" if any(x in label for x in ["YoY", "MoM", "YTD", "Previous", "Running"]) else "KPIs",
                "check": check})
            return "[" + final.replace("]", "]]") + "]"

        additive = {"revenue": "Revenue", "salesamount": "Revenue", "totalrevenue": "Revenue", "cost": "Cost", "totalcost": "Cost",
                    "profit": "Profit", "quantity": "Quantity", "units": "Quantity", "expense": "Expenses", "spend": "Spend",
                    "clicks": "Clicks", "impressions": "Impressions", "leads": "Leads", "conversions": "Conversions"}
        for col in table["columns"]:
            token = words(col["name"])
            if col["role"] != "numeric" or token not in additive:
                continue
            label = additive[token]
            if label in created:
                continue
            created[label] = add("Total " + label, f'SUM({ref(name, col["name"])})', f"Aggregate observed additive {col['name']} at source grain.",
                "#,##0.00" if label in {"Revenue", "Cost", "Profit", "Expenses", "Spend"} else "#,##0",
                {"kind": "sum", "column": col["name"]})
        for token, label in [("orderid", "Orders"), ("customerid", "Customers"), ("employeeid", "Employees")]:
            col = next((c for c in table["columns"] if words(c["name"]) == token), None)
            if col:
                created[label] = add(label, f'DISTINCTCOUNTNOBLANK({ref(name, col["name"])})', "Count observed business entities; exclude null identifiers.", check={"kind": "distinct", "column": col["name"]})
        if not created:
            created["Records"] = add("Records", f"COUNTROWS({tq(name)})", "Count records; numeric aggregation requires domain meaning.", check={"kind": "count"})
        if "Revenue" in created and "Cost" in created and "Profit" not in created and any(w in goal for w in ["profit", "margin"]):
            created["Profit"] = add("Total Profit", created["Revenue"] + " - " + created["Cost"], "Requested profitability; observed revenue and cost.", "#,##0.00", {"kind": "difference", "left": created["Revenue"][1:-1], "right": created["Cost"][1:-1]})
        if "Profit" in created and "Revenue" in created and any(w in goal for w in ["profit", "margin"]):
            add("Margin %", f'DIVIDE({created["Profit"]}, {created["Revenue"]})', "Ratio of totals; avoid averaging row margins.", "0.0%", {"kind": "ratio", "left": created["Profit"][1:-1], "right": created["Revenue"][1:-1]})
        if "Revenue" in created and "Orders" in created and any(w in goal for w in ["order", "sales", "customer"]):
            add("Average Order Value", f'DIVIDE({created["Revenue"]}, {created["Orders"]})', "Revenue per distinct order in current context.", "#,##0.00", {"kind": "ratio", "left": created["Revenue"][1:-1], "right": created["Orders"][1:-1]})
        if "Conversions" in created and "Leads" in created and "conversion" in goal:
            add("Conversion %", f'DIVIDE({created["Conversions"]}, {created["Leads"]})', "Observed conversions per observed lead; same source grain.", "0.0%")
        has_date = any(r["from_table"] == name and r["to_table"] == "DimDate" and r["active"] for r in plan["relationships"])
        primary = created.get("Revenue") or next(iter(created.values()))
        if has_date and any(w in goal for w in ["growth", "yoy", "year over year"]):
            prev = add("Previous Year", f"CALCULATE({primary}, DATEADD('DimDate'[Date], -1, YEAR))", "Requested annual comparison.", "#,##0.00", {"kind": "previous_year", "base": primary[1:-1]})
            add("YoY %", f"DIVIDE({primary} - {prev}, {prev})", "Growth compared with previous year; blank when baseline is missing.", "0.0%", {"kind": "yoy", "base": primary[1:-1]})
        if has_date and any(w in goal for w in ["mom", "month over month"]):
            prev = add("Previous Month", f"CALCULATE({primary}, DATEADD('DimDate'[Date], -1, MONTH))", "Requested monthly comparison.", "#,##0.00")
            add("MoM %", f"DIVIDE({primary} - {prev}, {prev})", "Monthly growth with safe denominator.", "0.0%")
        if has_date and any(w in goal for w in ["running", "cumulative", "ytd"]):
            add("Running Total", f"CALCULATE({primary}, FILTER(ALLSELECTED('DimDate'), 'DimDate'[Date] <= MAX('DimDate'[Date])))", "Cumulative total within selected calendar range.", "#,##0.00")
