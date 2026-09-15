"""Question-driven PBIR pages and reusable layout/formatting primitives."""
from __future__ import annotations

import math
import re
import datetime
from pathlib import Path

from .analysis import words
from .core import BuildError, identity, write_json

SCHEMA_ROOT = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition"
SCHEMAS = {"report": "3.1.0", "page": "2.1.0", "pagesMetadata": "1.0.0", "visualContainer": "2.9.0", "versionMetadata": "1.0.0"}


def schema(kind: str) -> str:
    return f"{SCHEMA_ROOT}/{kind}/{SCHEMAS[kind]}/schema.json"


def literal(value):
    if isinstance(value, bool):
        encoded = str(value).lower()
    elif isinstance(value, (int, float)):
        encoded = str(value) + "D"
    else:
        encoded = "'" + str(value).replace("'", "''") + "'"
    return {"expr": {"Literal": {"Value": encoded}}}


def color(value):
    return {"solid": {"color": literal(value)}}


def field(table, name, kind="Column"):
    return {"table": table, "name": name, "kind": kind}


def expression(binding):
    return {binding.get("kind", "Column"): {"Expression": {"SourceRef": {"Entity": binding["table"]}}, "Property": binding["name"]}}


def contrast(a, b):
    def luminance(hexcolor):
        rgb = [int(hexcolor[i:i+2], 16) / 255 for i in (1, 3, 5)]
        linear = [c / 12.92 if c <= .04045 else ((c + .055) / 1.055) ** 2.4 for c in rgb]
        return sum(c * w for c, w in zip(linear, [.2126, .7152, .0722]))
    x, y = sorted([luminance(a), luminance(b)])
    return (y + .05) / (x + .05)


def theme_for(domain, brand=None):
    brand = brand or {}
    accent = brand.get("primary_color") or {"sales": "#196A83", "hr": "#6550A3", "finance": "#215A63", "marketing": "#4457A8"}.get(domain, "#285D85")
    if not re.fullmatch(r"#[0-9A-Fa-f]{6}", accent):
        raise BuildError("brand.primary_color must be a six-digit hex color such as #196A83.")
    palette = {"accent": accent, "ink": "#182B3A", "muted": "#526572", "canvas": "#F2F5F7", "surface": "#FFFFFF",
               "positive": "#237A57", "negative": "#B4474D", "neutral": "#7B8794"}
    theme = {"name": brand.get("company") or domain.title() + " Analytics", "dataColors": [accent, "#7B8794", "#61A6AC", "#A294BE", "#C49B56"],
        "background": palette["surface"], "foreground": palette["ink"], "tableAccent": accent,
        "good": palette["positive"], "bad": palette["negative"], "neutral": palette["neutral"],
        "textClasses": {key: {"fontFace": "Segoe UI", "fontSize": size, "color": palette["ink"]} for key, size in [("callout", 28), ("title", 14), ("header", 12), ("label", 11)]},
        "visualStyles": {"*": {"*": {"border": [{"show": False}], "background": [{"show": True, "color": {"solid": {"color": "#FFFFFF"}}, "transparency": 0}],
            "title": [{"fontFamily": "Segoe UI", "fontSize": 13, "fontColor": {"solid": {"color": palette["ink"]}}}]}}}}
    return {"palette": palette, "definition": theme}


def grid(count: int, x=32, y=290, width=1216, height=398, gap=20, columns=2):
    if count < 1:
        return []
    columns = min(count, columns)
    rows = math.ceil(count / columns)
    w, h = (width - gap * (columns - 1)) / columns, (height - gap * (rows - 1)) / rows
    return [{"x": x + (i % columns) * (w + gap), "y": y + (i // columns) * (h + gap), "width": w, "height": h} for i in range(count)]


def humanize(value):
    return re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", value).replace("_", " ")


def plan_report(model, goal, brand=None):
    theme = theme_for(model["domain"], brand)
    pages = []
    measures = model["measures"]
    facts = [t for t in model["tables"] if t["kind"] == "fact"] or model["tables"][:1]
    for fact in facts:
        metrics = [m for m in measures if m["table"] == fact["name"]]
        priorities = ["revenue", "profit", "margin", "orders", "employees", "conversions", "spend", "quantity"]
        metrics.sort(key=lambda m: next((i for i, token in enumerate(priorities) if token in m["name"].lower()), len(priorities)))
        if not metrics:
            continue
        active_dims = {r["to_table"] for r in model["relationships"] if r["from_table"] == fact["name"] and r.get("active", True)}
        relevant = [t for t in model["tables"] if t["name"] == fact["name"] or t["name"] in active_dims]
        groups = [field(t["name"], c["name"]) for t in relevant if not t.get("is_date") for c in t["columns"]
                  if c.get("role") == "category" and not c.get("hidden") and 1 < c.get("distinct", 2) <= 60]
        equivalences = {(t["name"], c["name"]): c.get("grouping_equivalence") for t in relevant for c in t["columns"]}
        selected = {}
        for group in groups:
            key = equivalences[(group["table"], group["name"])] or (group["table"], group["name"])
            if key not in selected or group["name"].lower().endswith("name"):
                selected[key] = group
        groups = list(selected.values())
        # Put business-requested dimensions first, retaining deterministic order.
        groups.sort(key=lambda f: (not any(word.lower() in goal.lower() for word in re.findall(r"[A-Z][a-z]+|[a-z]+", f["name"])), f["name"]))
        primary = field(metrics[0]["table"], metrics[0]["name"], "Measure")
        headline = [field(m["table"], m["name"], "Measure") for m in metrics if m.get("folder") != "Time intelligence"][:4]
        title = model["domain"].title() + " Overview" if len(facts) == 1 else fact["name"] + " Overview"
        visuals = [{"type": "cardVisual", "title": "Performance at a glance", "question": "What are the headline results in the selected context?", "roles": {"Data": headline},
                    "position": {"x": 32, "y": 160, "width": 1216, "height": 130}}]
        charts = []
        if "DimDate" in active_dims:
            dates = [c for c in fact["columns"] if c.get("role") == "date" and c.get("minimum")]
            monthly = dates and (datetime.date.fromisoformat(dates[0]["maximum"]) - datetime.date.fromisoformat(dates[0]["minimum"])).days > 120
            axis = field("DimDate", "YearMonth" if monthly else "Date")
            charts.append({"type": "lineChart", "title": primary["name"] + (" by month" if monthly else " over time"), "question": "How is performance changing over time?",
                           "roles": {"Category": [axis], "Y": [primary]}, "sort": axis})
        if groups:
            charts.append({"type": "clusteredBarChart", "title": primary["name"] + " by " + humanize(groups[0]["name"]),
                           "question": "Which segments contribute most?", "roles": {"Category": [groups[0]], "Y": [primary]}, "sort": primary, "descending": True})
        if not charts:
            charts.append({"type": "tableEx", "title": "Key results", "question": "What are the observed totals?", "roles": {"Values": headline}})
        for chart, position in zip(charts, grid(len(charts), y=312, height=376)):
            visuals.append({**chart, "position": position})
        slicer = groups[0] if groups else field("DimDate", "Year") if "DimDate" in active_dims else None
        if slicer:
            visuals.append({"type": "slicer", "title": humanize(slicer["name"]), "question": "Which segment should this page focus on?",
                "roles": {"Values": [slicer]}, "position": {"x": 940, "y": 24, "width": 308, "height": 80}})
        if "DimDate" in active_dims and slicer != field("DimDate", "Year"):
            visuals.append({"type": "slicer", "title": "Year", "question": "Which calendar year should the report compare?",
                "roles": {"Values": [field("DimDate", "Year")]}, "position": {"x": 720, "y": 24, "width": 200, "height": 80}})
        pages.append({"name": identity(fact["name"], "overview"), "title": title, "subtitle": "Selected context · " + fact["name"], "visuals": visuals})
        # Add only requested/deep analytical cuts with available fields. Each page changes with the data.
        detail_groups = groups[1:4]
        if any(w in goal.lower() for w in ["detail", "product", "customer", "region", "department", "channel", "analysis"]):
            for group in detail_groups:
                group_title = humanize(group["name"]) + " Analysis"
                roles = {"Category": [group], "Y": [primary]}
                second = {"Values": [group] + headline}
                pv = [{"type": "clusteredBarChart", "title": primary["name"] + " by " + humanize(group["name"]), "question": "Which entities drive results?", "roles": roles, "sort": primary, "descending": True},
                      {"type": "tableEx", "title": "Performance details", "question": "What explains differences between entities?", "roles": second}]
                for visual, position in zip(pv, grid(2, y=160, height=528)):
                    visual["position"] = position
                pages.append({"name": identity(fact["name"], group["table"], group["name"]), "title": group_title,
                              "subtitle": "Compare contribution and supporting metrics", "visuals": pv})
        if groups and "drill" in goal.lower():
            pages.append({"name": identity(fact["name"], "drillthrough"), "title": "Entity Details", "subtitle": "Filtered from the selected entity",
                "drillthrough": groups[0], "hidden": True,
                "visuals": [{"type": "tableEx", "title": "Detailed results", "question": "What are this entity's results?",
                    "roles": {"Values": [groups[0]] + headline}, "position": {"x": 32, "y": 160, "width": 1216, "height": 528}}]})
    return {"width": 1280, "height": 720, "theme": theme, "pages": pages,
            "design_rationale": "Pages follow available related dimensions and requested comparisons; no disconnected fields or speculative maps."}


class PbirWriter:
    def apply(self, folder: Path, model_folder: str, plan: dict) -> list[str]:
        write_json(folder / "definition.pbir", {"$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definitionProperties/2.0.0/schema.json",
            "version": "4.0", "datasetReference": {"byPath": {"path": "../" + model_folder}}})
        root = folder / "definition"
        write_json(root / "version.json", {"$schema": schema("versionMetadata"), "version": "2.0.0"})
        theme = dict(plan["theme"]["definition"])
        import json
        filename = "Analyst-" + identity(json.dumps(theme, sort_keys=True)) + ".json"
        theme["name"] = filename
        write_json(folder / "StaticResources" / "RegisteredResources" / filename, theme)
        write_json(root / "report.json", {"$schema": schema("report"),
            "settings": {"filterPaneHiddenInEditMode": True, "defaultFilterActionIsDataFilter": True, "useEnhancedTooltips": True},
            "objects": {"outspacePane": [{"properties": {"expanded": literal(False), "visible": literal(False)}}]},
            "themeCollection": {"customTheme": {"name": filename, "type": "RegisteredResources", "reportVersionAtImport": {"visual": "2.9.0", "report": "3.1.0", "page": "2.1.0"}}},
            "resourcePackages": [{"name": "RegisteredResources", "type": "RegisteredResources", "items": [{"name": filename, "path": filename, "type": "CustomTheme"}]}]})
        order = [p["name"] for p in plan["pages"]]
        write_json(root / "pages" / "pages.json", {"$schema": schema("pagesMetadata"), "pageOrder": order, "activePageName": next(p["name"] for p in plan["pages"] if not p.get("hidden"))})
        for page in plan["pages"]:
            self.page(root, page, plan)
        return [str(p.relative_to(folder)) for p in sorted(folder.rglob("*")) if p.is_file()]

    def page(self, root, page, plan):
        directory = root / "pages" / page["name"]
        definition = {"$schema": schema("page"), "name": page["name"], "displayName": page["title"], "displayOption": "FitToPage",
            "width": page.get("width", plan["width"]), "height": page.get("height", plan["height"]),
            "objects": {"background": [{"properties": {"color": color(plan["theme"]["palette"]["canvas"]), "transparency": literal(0)}}]}}
        if page.get("hidden"):
            definition["visibility"] = "HiddenInViewMode"
        if page.get("drillthrough"):
            binding = page["drillthrough"]
            fid = "Filter" + identity(page["name"], "drill") + "0000"
            definition["filterConfig"] = {"filters": [{"name": fid, "field": expression(binding), "type": "Categorical", "howCreated": "Drillthrough"}]}
            definition["pageBinding"] = {"name": "Pod", "type": "Drillthrough", "parameters": [{"name": "Param_" + fid, "boundFilter": fid, "fieldExpr": expression(binding)}]}
        if page.get("tooltip"):
            definition["pageBinding"] = {"name": "Pod", "type": "Tooltip"}
        if page.get("filters"):
            definition.setdefault("filterConfig", {}).setdefault("filters", []).extend(page["filters"])
        if page.get("interactions"):
            definition["visualInteractions"] = page["interactions"]
        write_json(directory / "page.json", definition)
        header = {"$schema": schema("visualContainer"), "name": identity(page["name"], "header"),
            "position": {"x": 32, "y": 16, "width": 660, "height": 54, "z": 0, "tabOrder": 0},
            "visual": {"visualType": "textbox", "objects": {"general": [{"properties": {"paragraphs": [
                {"textRuns": [{"value": page["title"], "textStyle": {"fontFamily": "Segoe UI Semibold", "fontSize": "24pt", "color": plan["theme"]["palette"]["ink"]}}]}]}}]},
                "visualContainerObjects": {"background": [{"properties": {"show": literal(False)}}]}}}
        if not page.get("tooltip"):
            header["position"]["width"] = min(660, definition["width"] - 64)
            write_json(directory / "visuals" / header["name"] / "visual.json", header)
            import copy
            subtitle = copy.deepcopy(header)
            subtitle["name"] = identity(page["name"], "subtitle")
            subtitle["position"].update(y=72, height=34, z=100, tabOrder=100)
            run = subtitle["visual"]["objects"]["general"][0]["properties"]["paragraphs"][0]["textRuns"][0]
            run["value"] = page.get("subtitle", "")
            run["textStyle"].update(fontFamily="Segoe UI", fontSize="11pt", color=plan["theme"]["palette"]["muted"])
            write_json(directory / "visuals" / subtitle["name"] / "visual.json", subtitle)
        if not page.get("tooltip") and len([p for p in plan["pages"] if not p.get("hidden")]) > 1:
            navname = identity(page["name"], "navigation")
            write_json(directory / "visuals" / navname / "visual.json", {
                "$schema": schema("visualContainer"), "name": navname,
                "position": {"x": 32, "y": 112, "width": min(1216, definition["width"] - 64), "height": 32, "z": 500, "tabOrder": 500},
                "visual": {"visualType": "pageNavigator", "objects": {
                    "pages": [{"properties": {"showHiddenPages": literal(False), "showTooltipPages": literal(False)}}],
                    "text": [{"selector": {"id": "default"}, "properties": {"fontSize": literal(11)}}],
                    "outline": [{"selector": {"id": "default"}, "properties": {"show": literal(False)}}]}}})
        for i, visual in enumerate(page["visuals"], 1):
            name = visual.get("name") or identity(page["name"], str(i), visual["title"])
            write_json(directory / "visuals" / name / "visual.json", self.visual(visual, name, i, plan["theme"]["palette"]))

    @staticmethod
    def visual(spec, name, order, palette):
        query = {}
        for role, bindings in spec.get("roles", {}).items():
            query[role] = {"projections": [{"field": expression(b), "queryRef": b["table"] + "." + b["name"], "nativeQueryRef": humanize(b["name"])} for b in bindings]}
        visual = {"visualType": spec["type"], "query": {"queryState": query},
            "visualContainerObjects": {"title": [{"properties": {"show": literal(spec["type"] != "cardVisual"), "text": literal(spec["title"]), "fontSize": literal(13)}}],
                "background": [{"properties": {"show": literal(True), "color": color(palette["surface"]), "transparency": literal(0)}}],
                "border": [{"properties": {"show": literal(False)}}]}}
        if spec.get("sort"):
            visual["query"]["sortDefinition"] = {"sort": [{"field": expression(spec["sort"]), "direction": "Descending" if spec.get("descending") else "Ascending"}], "isDefaultSort": True}
        if spec["type"] == "cardVisual":
            visual["objects"] = {k: [{"selector": {"id": "default"}, "properties": p}] for k, p in {
                "outline": {"show": literal(False)}, "value": {"fontSize": literal(28), "fontColor": color(palette["ink"]), "labelDisplayUnits": literal(1)},
                "label": {"fontSize": literal(12)}, "padding": {"paddingUniform": literal(8)}, "layout": {"paddingUniform": literal(4)}}.items()}
        if spec["type"] == "slicer":
            visual["objects"] = {"data": [{"properties": {"mode": literal("Dropdown")}}], "header": [{"properties": {"show": literal(False)}}]}
        if spec.get("objects"):
            visual.setdefault("objects", {}).update(spec["objects"])
        if spec.get("container_objects"):
            visual["visualContainerObjects"].update(spec["container_objects"])
        result = {"$schema": schema("visualContainer"), "name": name, "position": {**spec["position"], "z": order * 1000, "tabOrder": order * 1000}, "visual": visual}
        if spec.get("filters"):
            result["filterConfig"] = {"filters": spec["filters"]}
        return result
