"""Compile authored plans to PBIR without injecting a dashboard design."""
from __future__ import annotations

import re
from pathlib import Path

from .core import identity, write_json

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


def humanize(value):
    return re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", value).replace("_", " ")


# Compatibility exports for callers of the original technical demo helpers.
def theme_for(domain, brand=None):
    from .bootstrap import theme_for as bootstrap_theme
    return bootstrap_theme(domain, brand)


def grid(*args, **kwargs):
    from .bootstrap import grid as bootstrap_grid
    return bootstrap_grid(*args, **kwargs)


def plan_report(model, goal, brand=None):
    from .bootstrap import plan_report as bootstrap_plan
    return bootstrap_plan(model, goal, brand)


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
            "settings": plan.get("settings", {}),
            "objects": plan.get("objects", {}),
            "themeCollection": {"customTheme": {"name": filename, "type": "RegisteredResources", "reportVersionAtImport": {"visual": "2.9.0", "report": "3.1.0", "page": "2.1.0"}}},
            "resourcePackages": [{"name": "RegisteredResources", "type": "RegisteredResources", "items": [{"name": filename, "path": filename, "type": "CustomTheme"}]}]})
        order = [p["name"] for p in plan["pages"]]
        write_json(root / "pages" / "pages.json", {"$schema": schema("pagesMetadata"), "pageOrder": order, "activePageName": next(p["name"] for p in plan["pages"] if not p.get("hidden"))})
        for page in plan["pages"]:
            self.page(root, page, plan)
        return [str(p.relative_to(folder)) for p in sorted(folder.rglob("*")) if p.is_file()]

    def page(self, root, page, plan):
        directory = root / "pages" / page["name"]
        definition = {"$schema": schema("page"), "name": page["name"], "displayName": page["title"], "displayOption": page.get("display_option", "FitToPage"),
            "width": page.get("width", plan["width"]), "height": page.get("height", plan["height"]),
            "objects": {"background": [{"properties": {"color": color(page.get("background", plan["theme"]["palette"]["canvas"])), "transparency": literal(0)}}], **page.get("objects", {})}}
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
        for i, visual in enumerate(page["visuals"], 1):
            name = visual.get("name") or identity(page["name"], str(i), visual["title"])
            write_json(directory / "visuals" / name / "visual.json", self.visual(visual, name, i, plan["theme"]["palette"]))

    @staticmethod
    def visual(spec, name, order, palette):
        query = {}
        for role, bindings in spec.get("roles", {}).items():
            query[role] = {"projections": [{"field": expression(b), "queryRef": b["table"] + "." + b["name"], "nativeQueryRef": humanize(b["name"])} for b in bindings]}
        visual = {"visualType": spec["type"]}
        if query:
            visual["query"] = {"queryState": query}
        if spec.get("sort"):
            visual.setdefault("query", {"queryState": {}})["sortDefinition"] = {"sort": [{"field": expression(spec["sort"]), "direction": "Descending" if spec.get("descending") else "Ascending"}], "isDefaultSort": True}
        if spec["type"] == "textbox" and "text" in spec:
            visual["objects"] = {"general": [{"properties": {"paragraphs": [
                {"textRuns": [{"value": spec["text"], "textStyle": spec.get("text_style", {})}]}]}}]}
        if spec.get("objects"):
            visual.setdefault("objects", {}).update(spec["objects"])
        if spec.get("container_objects"):
            visual["visualContainerObjects"] = spec["container_objects"]
        result = {"$schema": schema("visualContainer"), "name": name, "position": {**spec["position"],
            "z": spec.get("z_index", -1000 if spec.get("layer") == "background" else order * 1000),
            "tabOrder": spec.get("tab_order", order * 1000)}, "visual": visual}
        if spec.get("filters"):
            result["filterConfig"] = {"filters": spec["filters"]}
        return result
