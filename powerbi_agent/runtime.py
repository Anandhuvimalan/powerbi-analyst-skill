"""Independent source totals, filtered-context checks, and runtime result assessment."""
from __future__ import annotations

import json
import math

from .model import dq, ref


def source_expectations(model, datasets):
    data = {d.name: d for d in datasets}
    measures = {m["name"]: m for m in model["measures"]}

    def expected(name, rows, seen=None):
        seen = set() if seen is None else seen
        if name in seen or name not in measures:
            return False, None
        measure = measures[name]
        spec = measure.get("check") or {}
        kind = spec.get("kind")
        if kind in {"difference", "ratio"}:
            left_ok, left = expected(spec["left"], rows, seen | {name})
            right_ok, right = expected(spec["right"], rows, seen | {name})
            if not left_ok or not right_ok:
                return False, None
            if kind == "difference":
                return True, (left or 0) - (right or 0)
            return True, None if not right else (left or 0) / right
        if kind == "count":
            return True, len(rows) or None
        if kind in {"sum", "distinct"}:
            if rows and spec["column"] not in rows[0]:
                return False, None
            values = [r[spec["column"]] for r in rows if r.get(spec["column"]) is not None]
            if not values:
                return True, None
            return True, math.fsum(values) if kind == "sum" else len(set(values))
        if kind == "expected":
            return True, spec["value"]
        return False, None

    checks = []
    for measure in model["measures"]:
        source = data.get(measure["table"])
        if not source:
            continue
        ok, total = expected(measure["name"], source.rows)
        dax_ref = "[" + measure["name"].replace("]", "]]") + "]"
        spec = measure.get("check") or {}
        if spec.get("kind") in {"previous_year", "yoy"}:
            relationship = next((r for r in model["relationships"] if r["from_table"] == source.name and r["to_table"] == "DimDate" and r.get("active", True)), None)
            if relationship and any(c["name"] == relationship["from_column"] and c.get("role") == "date" and c.get("minimum") for c in source.profile["columns"]):
                col = relationship["from_column"]
                years = sorted({int(r[col][:4]) for r in source.rows if r[col] is not None})
                for year in [years[0], years[-1]]:
                    _, current_value = expected(spec["base"], [r for r in source.rows if r[col] and int(r[col][:4]) == year])
                    _, previous_value = expected(spec["base"], [r for r in source.rows if r[col] and int(r[col][:4]) == year - 1])
                    value = previous_value if spec["kind"] == "previous_year" else None if not previous_value else ((current_value or 0) - previous_value) / previous_value
                    checks.append({"measure": measure["name"], "context": f"calendar_year_{year}", "has_expected": True, "expected": value,
                        "query": f'EVALUATE ROW("Value", CALCULATE({dax_ref}, \'DimDate\'[Year] = {year}))'})
                continue
        checks.append({"measure": measure["name"], "context": "grand_total", "has_expected": ok, "expected": total,
                       "query": f'EVALUATE ROW("Value", {dax_ref})'})
        if not ok or (measure.get("check") or {}).get("kind") == "expected":
            continue
        for relationship in model["relationships"]:
            if relationship["from_table"] != source.name or not relationship.get("active", True) or relationship["to_table"] == "DimDate":
                continue
            key = relationship["from_column"]
            value = next((r[key] for r in source.rows if r.get(key) is not None), None)
            if value is None:
                continue
            selected = [r for r in source.rows if r.get(key) == value]
            _, result = expected(measure["name"], selected)
            encoded = str(value).upper() if isinstance(value, bool) else str(value) if isinstance(value, (int, float)) else dq(str(value))
            checks.append({"measure": measure["name"], "context": "relationship_filter_" + relationship["to_table"],
                "has_expected": True, "expected": result,
                "query": f'EVALUATE ROW("Value", CALCULATE({dax_ref}, {ref(relationship["to_table"], relationship["to_column"])} = {encoded}))'})
        category = next((c for c in source.profile["columns"] if c["role"] == "category" and 1 < c["distinct"] <= 20), None)
        if category:
            value = next(r[category["name"]] for r in source.rows if r[category["name"]] is not None)
            selected = [r for r in source.rows if r[category["name"]] == value]
            _, result = expected(measure["name"], selected)
            checks.append({"measure": measure["name"], "context": "category_filter", "has_expected": True, "expected": result,
                "query": f'EVALUATE ROW("Value", CALCULATE({dax_ref}, {ref(source.name, category["name"])} = {dq(str(value))}))'})
    return checks


def result_scalar(result):
    """Read common inline/resource MCP result envelopes without guessing an unknown shape."""
    values = []

    def walk(node, in_rows=False):
        if isinstance(node, dict):
            for key, value in node.items():
                if key in {"[Value]", "Value"} and not isinstance(value, (dict, list)):
                    values.append(value)
                elif key in {"text"} and isinstance(value, str):
                    try:
                        walk(json.loads(value))
                    except json.JSONDecodeError:
                        pass
                else:
                    walk(value, key.lower() in {"rows", "rowdata"})
        elif isinstance(node, list):
            for item in node:
                if in_rows and isinstance(item, list) and len(item) == 1:
                    values.append(item[0])
                else:
                    walk(item, in_rows)
    walk(result)
    if len(values) == 1:
        return True, values[0]
    return False, None


def assess_results(checks, results):
    if not checks:
        return {"check": "dax_runtime", "status": "needs_review", "assessments": [], "detail": "No executable checks were defined; empty validation is not a pass."}
    assessments = []
    for check, result in zip(checks, results, strict=True):
        parsed, value = result_scalar(result)
        status = "needs_review"
        detail = "Unknown MCP result shape or no independent expected value."
        if parsed and check["has_expected"]:
            expected = check["expected"]
            equal = value is None and expected is None
            if isinstance(value, (int, float)) and isinstance(expected, (int, float)) and not isinstance(value, bool):
                equal = math.isclose(value, expected, rel_tol=1e-8, abs_tol=1e-6)
            status = "passed" if equal else "failed"
            detail = "Compared with independent source aggregation in the same filter context."
        elif parsed and value is None:
            detail = "DAX returned blank. Inspect missing periods, empty context and measure semantics."
        assessments.append({**check, "actual": value, "status": status, "detail": detail})
    overall = "failed" if any(a["status"] == "failed" for a in assessments) else "needs_review" if any(a["status"] != "passed" for a in assessments) else "passed"
    return {"check": "dax_runtime", "status": overall, "assessments": assessments,
            "detail": "Source totals and selected category contexts checked; further time/RLS/performance scenarios may still be needed."}
