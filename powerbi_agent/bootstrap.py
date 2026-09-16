"""Preset technical demo, used only after explicit bootstrap opt-in.

This is deliberately not the agent's report designer. Authored builds bypass it.
"""
import datetime
import math
import re

from .core import BuildError, identity
from .report import color, field, humanize, literal


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


def plan_report(model, goal, brand=None):
    """Explicit bootstrap demo only. Production agent builds author their own plan."""
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
    # The demo owns its chrome and formatting; the renderer has no preset design.
    for page in pages:
        for visual in page["visuals"]:
            visual["container_objects"] = {
                "title": [{"properties": {"show": literal(visual["type"] != "cardVisual"), "text": literal(visual["title"]), "fontSize": literal(13)}}],
                "background": [{"properties": {"show": literal(True), "color": color(theme["palette"]["surface"]), "transparency": literal(0)}}],
                "border": [{"properties": {"show": literal(False)}}]}
            if visual["type"] == "cardVisual":
                visual["objects"] = {k: [{"selector": {"id": "default"}, "properties": p}] for k, p in {
                    "outline": {"show": literal(False)}, "value": {"fontSize": literal(28), "fontColor": color(theme["palette"]["ink"]), "labelDisplayUnits": literal(1)},
                    "label": {"fontSize": literal(12)}, "padding": {"paddingUniform": literal(8)}, "layout": {"paddingUniform": literal(4)}}.items()}
            if visual["type"] == "slicer":
                visual["objects"] = {"data": [{"properties": {"mode": literal("Dropdown")}}], "header": [{"properties": {"show": literal(False)}}]}
        for title, text, y, height, size, ink in [
            ("Heading", page["title"], 16, 54, "24pt", "ink"),
            ("Context", page.get("subtitle", ""), 72, 34, "11pt", "muted")]:
            page["visuals"].append({"type": "textbox", "title": title, "text": text,
                "text_style": {"fontFamily": "Segoe UI", "fontSize": size, "color": theme["palette"][ink]},
                "question": "Identify this page and its context", "roles": {},
                "position": {"x": 32, "y": y, "width": 660, "height": height},
                "container_objects": {"background": [{"properties": {"show": literal(False)}}]}})
        if len([p for p in pages if not p.get("hidden")]) > 1:
            page["visuals"].append({"type": "pageNavigator", "title": "Pages", "question": "Navigate analytical questions", "roles": {},
                "position": {"x": 32, "y": 112, "width": 1216, "height": 32},
                "objects": {"pages": [{"properties": {"showHiddenPages": literal(False), "showTooltipPages": literal(False)}}],
                    "text": [{"selector": {"id": "default"}, "properties": {"fontSize": literal(11)}}],
                    "outline": [{"selector": {"id": "default"}, "properties": {"show": literal(False)}}]}})
    return {"composition": "bootstrap", "width": 1280, "height": 720, "theme": theme, "pages": pages,
            "design_rationale": "Pages follow available related dimensions and requested comparisons; no disconnected fields or speculative maps."}


