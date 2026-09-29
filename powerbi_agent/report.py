"""Compile authored plans to PBIR without injecting a dashboard design."""
from __future__ import annotations

import re
from pathlib import Path

from .core import identity, write_json

SCHEMA_ROOT = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition"
SCHEMAS = {"report": "3.1.0", "page": "2.1.0", "pagesMetadata": "1.0.0", "visualContainer": "2.9.0", "versionMetadata": "1.0.0"}


def schema(kind: str) -> str:
    return f"{SCHEMA_ROOT}/{kind}/{SCHEMAS[kind]}/schema.json"


def literal(value, integer=False):
    if isinstance(value, bool):
        encoded = str(value).lower()
    elif integer:
        encoded = str(int(value)) + "L"
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


# Elements that carry no data question of their own and never get a container title.
DECORATIVE = {"shape", "basicShape", "textbox", "image", "actionButton", "pageNavigator", "bookmarkNavigator"}
SLICERS = {"slicer", "advancedSlicerVisual", "listSlicer", "textSlicer", "filterSlicer"}
# Native integer properties; Desktop rejects a double ("12D") literal for these.
INTEGER_PROPERTIES = {"shape": {"roundEdge", "rectangleRoundedCurve", "tabRoundCornerTop", "tabRoundCornerBottom", "tabRoundCornerTopRight"}}


def z_order(spec, order):
    """Background elements stack below content from z 0 upward. Desktop does not draw negative z."""
    return spec.get("z_index", order if spec.get("layer") == "background" else order * 1000)


def effective_style(spec, plan):
    """Authored style tokens: report defaults for all visuals, then per type, then the visual's own."""
    defaults = plan.get("style_defaults", {})
    return {**defaults.get("*", {}), **defaults.get(spec["type"], {}), **spec.get("style", {})}


def props(**values):
    return {k: v for k, v in values.items() if v is not None}


def compile_style(spec, style):
    """Translate the compact authored style into native PBIR objects. Nothing here is a default:
    a property is emitted only when the author set its token."""
    container, objects = {}, {}
    if "background" in style:
        background = style["background"]
        container["background"] = [{"properties": {"show": literal(bool(background)), **({"color": color(background),
            "transparency": literal(style.get("background_transparency", 0))} if background else {})}}]
    if "border" in style or "radius" in style:
        border = style.get("border")
        container["border"] = [{"properties": props(show=literal(bool(border)), color=color(border) if border else None,
            width=literal(style["border_width"]) if border and "border_width" in style else None,
            radius=literal(style["radius"]) if "radius" in style else None)}]
    if "shadow" in style:
        container["dropShadow"] = [{"properties": {"show": literal(bool(style["shadow"])), **({"preset": literal(
            style["shadow"] if isinstance(style["shadow"], str) else "Bottom"), "transparency": literal(style.get("shadow_transparency", 85))} if style["shadow"] else {})}}]
    if "padding" in style:
        container["padding"] = [{"properties": {side: literal(style["padding"]) for side in ("top", "bottom", "left", "right")}}]
    if "header_icons" in style:
        container["visualHeader"] = [{"properties": {"show": literal(bool(style["header_icons"]))}}]
    title = props(fontColor=color(style["title_color"]) if "title_color" in style else None,
        fontSize=literal(style["title_size"]) if "title_size" in style else None,
        fontFamily=literal(style["title_font"]) if "title_font" in style else None,
        bold=literal(style["title_bold"]) if "title_bold" in style else None,
        alignment=literal(style["title_align"]) if "title_align" in style else None)
    if spec["type"] == "cardVisual" and "card_outline" in style:
        # cardVisual draws its own grey box around each value unless told otherwise.
        outline = style["card_outline"]
        objects["outline"] = [{"selector": {"id": "default"}, "properties": props(show=literal(bool(outline)),
            color=color(outline) if outline else None)}]
    if spec["type"] in {"shape", "basicShape"}:
        shape = props(tileShape=literal(style["shape"]) if "shape" in style else None,
            roundEdge=literal(style["corner"], integer=True) if "corner" in style else None)
        if shape:
            objects["shape"] = [{"selector": {"id": "default"}, "properties": shape}]
        if "fill" in style:
            objects["fill"] = [{"selector": {"id": "default"}, "properties": {"show": literal(bool(style["fill"])), **({"fillColor": color(style["fill"]),
                "transparency": literal(style.get("fill_transparency", 0))} if style["fill"] else {})}}]
        if "outline" in style:
            outline = style["outline"]
            objects["outline"] = [{"selector": {"id": "default"}, "properties": props(show=literal(bool(outline)),
                lineColor=color(outline) if outline else None, weight=literal(style.get("outline_width", 1)) if outline else None)}]
    return container, objects, title


def compile_slicer(settings, title, title_style):
    objects = {}
    if "mode" in settings:
        objects["data"] = [{"properties": {"mode": literal(settings["mode"])}}]
    selection = props(strictSingleSelect=literal(settings["single_select"]) if "single_select" in settings else None,
        selectAllCheckboxEnabled=literal(settings["select_all"]) if "select_all" in settings else None)
    if selection:
        objects["selection"] = [{"properties": selection}]
    header = {"show": literal(settings.get("show_header", True)), "text": literal(title)}
    header.update({{"fontSize": "textSize"}.get(k, k): v for k, v in title_style.items() if k in {"fontColor", "fontSize", "fontFamily", "bold"}})
    objects["header"] = [{"properties": header}]
    if settings.get("item_color") or settings.get("item_size"):
        objects["items"] = [{"properties": props(fontColor=color(settings["item_color"]) if settings.get("item_color") else None,
            textSize=literal(settings["item_size"]) if settings.get("item_size") else None)}]
    return objects


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
            write_json(directory / "visuals" / name / "visual.json", self.visual(visual, name, i, plan["theme"]["palette"], plan))

    @staticmethod
    def visual(spec, name, order, palette, plan=None):
        query = {}
        for role, bindings in spec.get("roles", {}).items():
            query[role] = {"projections": [{"field": expression(b), "queryRef": b["table"] + "." + b["name"], "nativeQueryRef": humanize(b["name"]),
                **({"displayName": b["label"]} if b.get("label") else {})} for b in bindings]}
        visual = {"visualType": spec["type"]}
        if query:
            visual["query"] = {"queryState": query}
        if spec.get("sort"):
            visual.setdefault("query", {"queryState": {}})["sortDefinition"] = {"sort": [{"field": expression(spec["sort"]), "direction": "Descending" if spec.get("descending") else "Ascending"}], "isDefaultSort": True}
        if spec["type"] == "textbox" and "text" in spec:
            visual["objects"] = {"general": [{"properties": {"paragraphs": [
                {"textRuns": [{"value": spec["text"], "textStyle": spec.get("text_style", {})}]}]}}]}
        container, objects, title_style = compile_style(spec, effective_style(spec, plan or {}))
        if spec["type"] in SLICERS and spec["type"] != "advancedSlicerVisual":
            # A slicer's own header is its title; a container title as well would print it twice.
            objects.update(compile_slicer(spec.get("slicer", {}), spec["title"], title_style))
            container["title"] = [{"properties": {"show": literal(False)}}]
        elif spec["type"] not in DECORATIVE:
            # The authored title is the visual's heading; never let Power BI fall back to "Sum of X by Y".
            shown = spec.get("show_title", True)
            container["title"] = [{"properties": {"show": literal(shown), **({"text": literal(spec["title"]), **title_style} if shown else {})}}]
            if spec.get("subtitle"):
                container["subTitle"] = [{"properties": {"show": literal(True), "text": literal(spec["subtitle"]),
                    **({"fontColor": color(spec["style"]["subtitle_color"])} if spec.get("style", {}).get("subtitle_color") else {})}}]
        if objects:
            visual.setdefault("objects", {}).update(objects)
        if spec.get("objects"):
            visual.setdefault("objects", {}).update(spec["objects"])
        container.update(spec.get("container_objects", {}))
        if container:
            visual["visualContainerObjects"] = container
        if spec.get("slicer", {}).get("sync_group"):
            visual["syncGroup"] = {"groupName": spec["slicer"]["sync_group"], "fieldChanges": True, "filterChanges": True}
        result = {"$schema": schema("visualContainer"), "name": name, "position": {**spec["position"],
            "z": z_order(spec, order),
            "tabOrder": spec.get("tab_order", order * 1000)}, "visual": visual}
        if spec.get("filters"):
            result["filterConfig"] = {"filters": spec["filters"]}
        return result
