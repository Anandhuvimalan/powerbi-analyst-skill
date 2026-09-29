# Project design system, canvas, visuals and filters

Read this before writing `report-plan.json`. The executor renders exactly what you
author and Power BI fills every gap with its own defaults: blue theme blocks for
unstyled shapes, "Sum of X by Y" titles, grey boxes around card values, vertical
list slicers. A report looks designed only when every one of those gaps is closed
deliberately, from facts about this project.

## 1. Derive the design system first

Author `report_plan.design_system` before any page. Agent mode rejects a plan
without it, and rejects the preset demo palette (`#F2F5F7` canvas with the demo
accents).

```json
"design_system": {
  "concept": "Quarterly margin ledger for regional directors: calm, dense, print-like",
  "derived_from": [
    "Audience: 6 regional directors reviewing monthly in a meeting room screen",
    "Brand primary #8A4B2A supplied by the client",
    "Only 4 regions and 4 categories: rankings fit without scrolling",
    "Profit is the decision metric; revenue is context"
  ],
  "tokens": {"canvas": "#F4F1EA", "panel": "#FFFFFF", "band": "#2B2118", "ink": "#2B2118",
             "muted": "#6B6259", "accent": "#8A4B2A", "positive": "#2E7D5B", "negative": "#B4474D"},
  "typography": {"heading": "Segoe UI Semibold", "body": "Segoe UI"},
  "grid": {"margin": 24, "gutter": 16, "columns": 12},
  "radius": 12,
  "filter_strategy": "Region and Year dropdowns in the header band, synced across pages; no filter pane use"
}
```

Every token must trace to a `derived_from` fact: the brand, domain, audience, how
the report is viewed (meeting screen, laptop, print), data density and the decision
metric. If a fact changes, the design should change. Two projects with different
audiences must not come out with the same palette, band, grid and typography. Do
not randomize either: equal facts may justify similar choices.

Choosing tokens:
- **Canvas vs panel.** Use a tinted canvas (warm, cool or neutral to suit the brand)
  with lighter panels, or a dark canvas with slightly lighter panels for control-room
  use. The contrast between panel and canvas creates the grouping.
- **One accent** for the decision metric. Use grey or muted colours for context
  series, and keep semantic colours (positive/negative) only for actual variance.
- **Text contrast.** Ink on panel and muted on canvas need at least 4.5:1 (this is
  validated). Light text on a dark band must be checked in the screenshot.
- **Typography.** Use a heading and a body family that exist on Windows (Segoe UI,
  Segoe UI Semibold, Segoe UI Light, DIN, Georgia, Bahnschrift). Use 18–24pt for
  page headings, 11–13pt for visual titles and 20–32pt for KPI values.

## 2. Lay out the canvas with background shapes

Build every page as layers:

1. **Page background.** Set `page.background` to `tokens.canvas`.
2. **Background shapes.** These are `type: "shape"` with `layer: "background"`: a
   header band, and one panel behind each group of related visuals (the KPI strip,
   a trend and the chart that explains it, a filter rail).
3. **Content.** Visuals sit inside their panels, inset by the grid padding.

```json
{"type": "shape", "title": "Trend panel", "question": "Group the trend and its explanation",
 "layer": "background", "position": {"x": 24, "y": 240, "width": 760, "height": 456},
 "style": {"fill": "#FFFFFF", "outline": "#E4DDD0", "outline_width": 1,
           "shape": "rectangleRoundedByPixel", "corner": 12}}
```

Rules the validator enforces (each one caused real blank or broken output):
- **Background elements stack at z ≥ 0 and below every content visual.** Power BI
  Desktop does not draw visuals with a negative z at all. Omit `z_index` and the
  executor stacks them correctly.
- **A shape must set `style.fill`.** A shape without a fill renders as a
  theme-coloured block. Also set `style.outline` (a colour, or `false`).
- **`corner` is an integer property** (compiled to `12L`). Raw `roundEdge` written
  as `12D` is rejected.
- **A page with two or more data visuals needs grouping:** either panels, or a card
  treatment (`style.background` on every visual). Otherwise state
  `design_system.flat_layout_reason`.

Grid arithmetic: content x = margin (+ panel padding), and widths divide
`canvas width − 2·margin − (n−1)·gutter`. Keep every panel edge on the same grid
lines throughout the report. Typical 1280×720 bands:

| Zone | Height |
|---|---|
| Header band | 72–96 px |
| KPI strip | 100–120 px |
| Main analysis | the rest, minus the margin |

Use a taller canvas (for example 1280×1080 with `display_option: "FitToWidth"`)
rather than shrinking charts.

## 3. Design every visual deliberately

Set shared chrome once with `style_defaults` (keys: `"*"` or a visual type), and
override it per visual with `style`:

```json
"style_defaults": {
  "*": {"background": false, "header_icons": false, "title_color": "#2B2118",
        "title_size": 12, "title_font": "Segoe UI Semibold", "padding": 8},
  "cardVisual": {"card_outline": false}
}
```

`style` tokens:

| Area | Tokens |
|---|---|
| Container | `background` (hex or `false`), `background_transparency`, `border`, `border_width`, `radius`, `shadow` (bool or preset), `padding`, `header_icons` |
| Title | `title_color`, `title_size`, `title_font`, `title_bold`, `title_align`, `subtitle_color` |
| Shape | `fill`, `fill_transparency`, `outline`, `outline_width`, `shape`, `corner` |
| Card | `card_outline` |

The visual's `title` is rendered as its heading. Add a `subtitle` for context such
as the unit, the period or the sort order. Use `show_title: false` only when a
textbox or the panel already labels the visual. Give fields a friendly header with
`label` on the binding: `{"table": "DimProduct", "name": "ProductName", "label": "Product"}`.

Anything the tokens don't cover goes in raw `objects` / `container_objects`. Look up
the names first with the installed Microsoft CLI instead of guessing:

```text
powerbi-report-author formatting list-objects <visualType>
powerbi-report-author formatting describe-object <visualType> <object>
powerbi-report-author expr encode 12 --kind integer
```

Per-family checklist (all verified to render in Desktop):
- **Cards (`cardVisual`).** Set `card_outline: false` inside a panel; the default
  draws a grey box around each value. Set `value.fontSize` and `fontColor`, and
  `labelDisplayUnits` to suit the magnitude. Size ≥ 120×80.
- **Line or area.** Match the axis grain to the question. A daily `Date` over two
  years is noise, so use a month-level date column with
  `categoryAxis.axisType: "Scalar"`. Text `YearMonth` labels rotate once there are
  more than about 12 of them. Turn off obvious axis titles (`showAxisTitle: false`)
  and use `lineStyles.strokeWidth` 2–3. Show comparisons in muted colours.
- **Bar or column.** Sort by the measure (`sort` + `descending`). Use horizontal bars
  for long labels. Show data labels (`labels.show`) when the number itself matters,
  and switch off `valueAxis.gridlineShow` then.
- **Table or matrix.** Use `columnHeaders.columnAdjustment: "growToFit"` so the
  table fills its panel, turn off `grid.gridVertical`, use `rowPadding` 4–8 and
  labels on every field. Size the panel to the expected row count.
- **Donut or pie.** Only for 2–5 parts of a whole. Otherwise use bars.
- **Numbers.** Give every measure a `format` in the model plan (e.g. `"$#,0"`,
  `"#,0"`, `"0.0%"`). The fallback is `#,##0.00`, which prints two decimals on
  every count and currency value (`1,43,612.00`).

## 4. Design the filters as part of the layout

Decide `filter_strategy` from the questions: which fields the audience actually
filters on, and where the filters live.
- **Header band.** Use this for 1–3 global filters.
- **Left filter rail.** Use a rail panel for exploratory pages with 4 or more
  filters.
- **Filter pane only.** Use this for rarely used filters. Style the pane with the
  page objects `outspacePane` and `filterCard` (`backgroundColor`,
  `foregroundColor`, `border`, `borderColor`, `fontFamily`).

Pick the slicer style from the field. Every `slicer` must set `slicer.mode`.

| Field | `slicer.mode` |
|---|---|
| Dates or periods | `Between`, or `Relative` for rolling windows; a `Dropdown` of Year / Year-Month for fiscal periods |
| 2–6 values, often switched | `HorizontalList` (tile buttons) |
| Many values | `Dropdown` |
| Single-choice scenarios | `single_select: true` |

```json
{"type": "slicer", "title": "Region", "question": "Which regions should the page compare?",
 "position": {"x": 900, "y": 10, "width": 170, "height": 76},
 "roles": {"Values": [{"table": "sales", "name": "Region"}]},
 "slicer": {"mode": "Dropdown", "select_all": true, "sync_group": "region"},
 "style": {"title_color": "#F4F1EA", "background": false}}
```

- **Sizing.** A `Dropdown` with a header needs a height of **at least 76 px**
  (header 28 + selector 32 + padding 16); without a header it needs 48 px. This is
  enforced both by Microsoft's validator and by the plan check.
- **Title.** The slicer's title becomes its own header. Style it with `title_*` and
  its items with `slicer.item_color` / `slicer.item_size`.
- **Sync.** When the same field is filtered on several pages, give each slicer the
  same `slicer.sync_group` so selections carry across. Unsynced repeats are flagged.
- **Fixed scope.** Use page or visual `filters` for fixed scope, not visible
  slicers.
- **Navigation.** A multi-page report needs visible navigation: a `pageNavigator`
  (style its buttons for the band it sits on) or `actionButton`s.

## 5. Review the rendered pages

Static checks cannot see rendering. When Desktop is available, open, reload and
screenshot every page, then inspect it for:
- panels and bands present, and aligned to the grid;
- no boxes inside boxes;
- titles authored, not auto-generated, and not truncated;
- axis labels readable, not rotated;
- numbers formatted;
- slicer headers visible against their background;
- tables and charts filling their panels;
- navigation styled.

Fix, rebuild and screenshot again. Report what the screenshots showed, never an
assumed result.
