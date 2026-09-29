"""Evidence-aware checks. Static lint is never described as DAX execution."""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from .core import BuildError, read_json
from .report import DECORATIVE, INTEGER_PROPERTIES, SLICERS, contrast, effective_style, z_order


def design_errors(visual, plan):
    """Catch designs that Power BI would silently render with its own defaults."""
    errors, kind, title = [], visual["type"], visual["title"]
    style = effective_style(visual, plan)
    objects = visual.get("objects", {})
    if kind in {"shape", "basicShape"}:
        for entry in objects.get("shape", []):
            for prop, value in entry.get("properties", {}).items():
                encoded = value.get("expr", {}).get("Literal", {}).get("Value", "") if isinstance(value, dict) else ""
                if prop in INTEGER_PROPERTIES["shape"] and not encoded.endswith("L"):
                    errors.append(f"{title}: shape.{prop} is an integer property; encode it as '12L' (or use style.corner)")
        if not style.get("fill") and "fill" not in objects:
            errors.append(f"{title}: shape has no authored fill; Power BI would draw its default theme-coloured block. Set style.fill (and style.outline)")
    if kind in SLICERS:
        if not visual.get("roles"):
            errors.append(f"{title}: slicer has no field binding")
        settings = visual.get("slicer", {})
        if kind == "slicer" and "mode" not in settings and "data" not in objects:
            errors.append(f"{title}: choose the slicer style deliberately (slicer.mode: Dropdown, Between, Relative...)")
        if kind == "slicer" and settings.get("mode") in {"VerticalList", "HorizontalList", "Basic"}:
            errors.append(f"{title}: legacy {settings['mode']} slicers look dated; use advancedSlicerVisual (buttons/tabs) or listSlicer with designed states")
        if kind == "slicer" and settings.get("mode") == "Dropdown" and not (style.get("background") or style.get("border")
                or visual.get("container_objects") or plan["theme"]["definition"].get("visualStyles")):
            errors.append(f"{title}: a bare legacy dropdown looks dated; give it a container (style.background/border/radius/padding) and header/item styling")
        if kind in {"advancedSlicerVisual", "listSlicer"}:
            if "mode" in settings:
                errors.append(f"{title}: slicer.mode applies only to the legacy slicer; design tiles with slicer tile/selected tokens")
            if not (settings.get("selected_fill") or settings.get("accent") or "fillCustom" in objects or "accentBar" in objects):
                errors.append(f"{title}: design the selected state (slicer.selected_fill or slicer.accent); the default is a heavy theme-coloured bar")
        # Mirrors Microsoft's PBIR_SLICER_HEIGHT_BELOW_FLOOR: header 28 + selector 32 + default padding 8/8.
        if visual.get("slicer", {}).get("mode") == "Dropdown":
            floor = (28 if visual["slicer"].get("show_header", True) else 0) + 32 + 16
            if visual["position"]["height"] < floor:
                errors.append(f"{title}: dropdown slicer needs at least {floor}px height or its header/selector is clipped")
    if kind == "textbox" and visual.get("text_style", {}).get("fontSize"):
        points = float(str(visual["text_style"]["fontSize"]).rstrip("pt"))
        floor = max(18, -(-points * 25 // 16)) + 16
        if visual["position"]["height"] < floor:
            errors.append(f"{title}: {points:g}pt text needs at least {floor:g}px height (with default padding) to avoid a scrollbar")
    if kind == "cardVisual" and "card_outline" not in style and "outline" not in objects:
        errors.append(f"{title}: decide the card's inner outline (style.card_outline: false removes Power BI's default grey box)")
    if kind == "pageNavigator" and not visual.get("navigator") and "fill" not in objects:
        errors.append(f"{title}: design the navigator buttons (navigator.tile_fill/selected_fill/tile_text...); the default navy buttons clash with most designs")
    themed = bool(plan["theme"]["definition"].get("visualStyles"))
    if kind not in DECORATIVE and not (themed or style or visual.get("container_objects")):
        errors.append(f"{title}: no authored container design (style, style_defaults, container_objects or theme visualStyles); Power BI defaults would become the design")
    return errors


def plan_schema(plan, name):
    from jsonschema import Draft202012Validator
    schema = read_json(Path(__file__).parent / "schemas" / (name + "-plan.json"))
    return [f"{list(e.path)}: {e.message}" for e in Draft202012Validator(schema).iter_errors(plan)]


def check_names(values, kind, errors):
    duplicates = [name for name, count in Counter(v.casefold() for v in values).items() if count > 1]
    errors.extend(f"Duplicate {kind}: {name}" for name in duplicates)


def validate_model(plan: dict) -> dict:
    errors, warnings = [], []
    schema_errors = plan_schema(plan, "model")
    if schema_errors:
        return {"check": "model_plan_schema", "status": "failed", "errors": schema_errors}
    tables = {t["name"]: t for t in plan.get("tables", [])}
    if not tables:
        errors.append("Model has no tables")
    check_names([t["name"] for t in plan.get("tables", [])] + [g["name"] for g in plan.get("calculation_groups", [])], "table", errors)
    measures = plan.get("measures", [])
    check_names([m["name"] for m in measures], "measure", errors)
    check_names([r["name"] for r in plan.get("relationships", [])], "relationship", errors)
    columns = {}
    for name, table in tables.items():
        check_names([c["name"] for c in table["columns"]], f"column in {name}", errors)
        columns[name] = {c["name"]: c for c in table["columns"]}
        if not table.get("m", "").strip():
            errors.append(f"Table {name} has no executable M partition")
        for col in table["columns"]:
            if col["data_type"] not in {"string", "dateTime", "int64", "double", "decimal", "boolean"}:
                errors.append(f"Unsupported data type: {name}[{col['name']}]")
            if col.get("sort_by") and col["sort_by"] not in columns[name]:
                errors.append(f"Missing sort column: {name}.{col['sort_by']}")
            if col.get("distinct", 0) > 10000 and col["data_type"] == "string":
                warnings.append(f"High-cardinality text: {name}[{col['name']}]; review import size.")
        for hierarchy in table.get("hierarchies", []):
            if any(level not in columns[name] for level in hierarchy["levels"]):
                errors.append(f"Hierarchy {name}.{hierarchy['name']} references a missing column")
    qualified = re.compile(r"(?:'((?:[^']|'')+)'|([A-Za-z_][\w]*))\[((?:[^\]]|\]\])+)\]")
    known_measures = {m["name"] for m in measures}
    for measure in measures:
        if measure["table"] not in tables:
            errors.append(f"Measure {measure['name']} has missing table")
        expr = measure["expression"]
        if not expr.strip() or "\n" in expr or "\r" in expr:
            errors.append(f"Measure {measure['name']} requires nonempty single-line DAX")
        if not measure.get("reason"):
            errors.append(f"Measure {measure['name']} has no business justification")
        # Exclude DAX double-quoted string literals from reference and bracket scanning.
        stripped = re.sub(r'"(?:[^"]|"")*"', '""', expr)
        for match in qualified.finditer(stripped):
            table = (match[1] or match[2]).replace("''", "'")
            col = match[3].replace("]]", "]")
            if table not in columns or (col not in columns.get(table, {}) and not any(m["table"] == table and m["name"] == col for m in measures)):
                errors.append(f"Missing DAX reference {table}[{col}] in {measure['name']}")
        remainder = qualified.sub("", stripped)
        for ref in re.findall(r"\[([^\]]+)\]", remainder):
            if ref not in known_measures and ref not in columns.get(measure["table"], {}):
                warnings.append(f"Unresolved unqualified DAX reference [{ref}] in {measure['name']}; engine validation required for virtual columns.")
        if stripped.count("(") != stripped.count(")"):
            errors.append(f"Unbalanced DAX parentheses: {measure['name']}")
        if "/" in stripped:
            warnings.append(f"Review division in {measure['name']}; DIVIDE is preferred.")
    graph = defaultdict(list)
    pairs = set()
    for rel in plan.get("relationships", []):
        ft, tt, fc, tc = (rel[k] for k in ["from_table", "to_table", "from_column", "to_column"])
        if fc not in columns.get(ft, {}) or tc not in columns.get(tt, {}):
            errors.append(f"Relationship {rel['name']} has missing endpoints")
            continue
        one, many = columns[tt][tc], columns[ft][fc]
        if one["data_type"] != many["data_type"]:
            errors.append(f"Relationship {rel['name']} has mismatched types")
        if not one.get("unique", one.get("is_key", False)) or one.get("nulls", 0):
            errors.append(f"Relationship {rel['name']} has unproven/nonunique/null one-side key")
        if rel.get("direction", "oneDirection") != "oneDirection":
            errors.append("Bidirectional/many-to-many needs a dedicated reviewed adapter; direct file default is oneDirection")
        if rel.get("active", True):
            pair = tuple(sorted([ft, tt]))
            if pair in pairs:
                errors.append(f"Multiple active relationships between {ft} and {tt}")
            pairs.add(pair)
            graph[tt].append(ft)
    for start in tables:
        visited_paths = Counter()

        def walk(node, path):
            if node in path:
                errors.append(f"Circular filter path involving {node}")
                return
            for child in graph[node]:
                visited_paths[child] += 1
                if visited_paths[child] > 1:
                    errors.append(f"Ambiguous filter paths from {start} to {child}")
                    continue
                walk(child, path | {node})
        walk(start, set())
    for role in plan.get("roles", []):
        for table in role["filters"]:
            if table not in tables:
                errors.append(f"RLS role references missing table {table}")
    for group in plan.get("calculation_groups", []):
        check_names([i["name"] for i in group["items"]], "calculation item", errors)
    return {"check": "model_static", "status": "failed" if errors else "passed", "errors": sorted(set(errors)), "warnings": sorted(set(warnings)),
            "limitation": "Reference and structural checks only; DAX/M parsing, refresh, semantics and performance require a runtime."}


def validate_report(plan, model):
    errors, warnings = [], []
    schema_errors = plan_schema(plan, "report")
    if schema_errors:
        return {"check": "report_plan_schema", "status": "failed", "errors": schema_errors}
    names = [p["name"] for p in plan.get("pages", [])]
    check_names(names, "page", errors)
    if not names or not any(not p.get("hidden") for p in plan.get("pages", [])):
        errors.append("Report requires a visible page")
    cols = {t["name"]: {c["name"] for c in t["columns"]} for t in model["tables"]}
    measures = {(m["table"], m["name"]) for m in model["measures"]}
    slicer_fields = {}
    for page in plan["pages"]:
        if not re.fullmatch(r"[a-f0-9]{20}|ReportSection[a-f0-9]{0,24}", page["name"]):
            errors.append("Page names must be stable PBIR identifiers")
        check_names([v["name"] for v in page["visuals"] if v.get("name")], "visual", errors)
        if sum(bool(v.get("roles")) for v in page["visuals"]) > 8:
            warnings.append(f"{page['title']}: more than eight data visuals may harm readability/performance")
        positions = []
        stack = [(z_order(v, i), v.get("layer") == "background", v["title"]) for i, v in enumerate(page["visuals"], 1)]
        for z, _, title in stack:
            if z < 0:
                errors.append(f"{title}: z_index {z} is negative; Power BI Desktop does not render visuals with negative z")
        content = [z for z, background, _ in stack if not background]
        for z, background, title in stack:
            if background and content and z >= min(content):
                errors.append(f"{title}: background element (z {z}) must stack below every content visual (lowest content z {min(content)})")
        for visual in page["visuals"]:
            background = visual.get("layer") == "background"
            if background and (visual["type"] not in {"shape", "textbox", "image"} or visual.get("roles")):
                errors.append("Only unbound decorative elements can use the background layer")
            if not visual.get("question"):
                errors.append(f"{visual['title']}: missing analytical question")
            p = visual["position"]
            if any(not isinstance(p.get(k), (int, float)) for k in ["x", "y", "width", "height"]):
                errors.append("Visual position must contain numeric x/y/width/height")
                continue
            if min(p["x"], p["y"]) < 0 or min(p["width"], p["height"]) <= 0 or p["x"] + p["width"] > page.get("width", plan["width"]) or p["y"] + p["height"] > page.get("height", plan["height"]):
                errors.append(f"Out-of-bounds visual: {visual['title']}")
            for other, op, other_background in positions:
                if background or other_background:
                    continue
                if p["x"] < op["x"] + op["width"] and p["x"] + p["width"] > op["x"] and p["y"] < op["y"] + op["height"] and p["y"] + p["height"] > op["y"]:
                    errors.append(f"Visual overlap: {visual['title']} / {other}")
            positions.append((visual["title"], p, background))
            if visual["type"] == "cardVisual" and (p["height"] < 80 or p["width"] < 120):
                warnings.append(f"Card may clip at this size; review chosen typography in Desktop: {visual['title']}")
            for bindings in visual.get("roles", {}).values():
                for b in bindings:
                    found = (b["table"], b["name"]) in measures if b.get("kind") == "Measure" else b["name"] in cols.get(b["table"], {})
                    if not found:
                        errors.append(f"Missing visual binding {b['table']}.{b['name']}")
            if visual.get("tooltip_page") and visual["tooltip_page"] not in names:
                errors.append("Missing tooltip page")
            errors.extend(design_errors(visual, plan))
        slicer_fields[page["name"]] = {json.dumps(b, sort_keys=True) for v in page["visuals"] if v["type"] in SLICERS
            for bs in v.get("roles", {}).values() for b in bs if not v.get("slicer", {}).get("sync_group")}
        if page.get("drillthrough"):
            b = page["drillthrough"]
            if b["name"] not in cols.get(b["table"], {}):
                errors.append("Missing drillthrough field")
    visible = [p for p in plan["pages"] if not p.get("hidden") and not p.get("tooltip")]
    navigators = {"pageNavigator", "actionButton", "bookmarkNavigator"}
    if len(visible) > 1 and not any(v["type"] in navigators for p in visible for v in p["visuals"]):
        warnings.append("Multi-page report has no on-canvas navigation (pageNavigator/actionButton); users rely on tabs only")
    repeated = Counter(f for fields in slicer_fields.values() for f in fields)
    for field_key, count in repeated.items():
        if count > 1:
            warnings.append(f"Slicer on {json.loads(field_key)['name']} appears on {count} pages without slicer.sync_group; selections will not carry across pages")
    palette = plan["theme"]["palette"]
    if contrast(palette["ink"], palette["surface"]) < 4.5 or contrast(palette["muted"], palette["canvas"]) < 4.5:
        errors.append("Theme text contrast is below 4.5:1")
    return {"check": "report_static", "status": "failed" if errors else "passed", "errors": errors, "warnings": warnings}


def enforce(result):
    if result["status"] == "failed":
        raise BuildError("Validation failed: " + "; ".join(result.get("errors", [str(result)]))[:4000])


def cli_result(result):
    if result["status"] == "unavailable":
        return result
    payload = result["result"]
    data = payload.get("data", payload)
    diagnostics = data.get("diagnostics", [])
    if isinstance(diagnostics, dict):
        diagnostics = [{"code": code, "severity": group.get("severity"), **item} for code, group in diagnostics.items() for item in group.get("items", [])]
    errors = [d for d in diagnostics if d.get("severity") == "error"]
    result["errors"] = [json.dumps(d) for d in errors]
    result["status"] = "failed" if errors or payload.get("error") or data.get("result") == "failed" or data.get("errorCount", 0) else "passed"
    # Schema-unreachable warnings mean remote schema validation was NOT completed.
    result["schema_complete"] = result["remote_schema"] and not any("UNREACHABLE" in d.get("code", "") for d in diagnostics)
    return result


class PowerBIValidator:
    def model(self, plan):
        return validate_model(plan)

    def report(self, plan, model):
        return validate_report(plan, model)

    def files(self, root: Path):
        errors = []
        files = list(root.rglob("*.json")) + list(root.rglob("*.pbip")) + list(root.rglob("*.pbir")) + list(root.rglob("*.pbism"))
        for path in files:
            try:
                read_json(path)
            except (ValueError, OSError) as exc:
                errors.append(f"{path}: {exc}")
        return {"check": "json_parse", "status": "failed" if errors else "passed", "errors": errors, "files": len(files)}
