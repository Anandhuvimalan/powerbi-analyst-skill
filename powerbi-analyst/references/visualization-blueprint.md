# Phase 5 — Visualization blueprint

A clear, actionable, step-by-step guide that someone with no Power BI experience
could follow to build the report. But the report's shape is driven by business
questions and the data — not a fixed template.

## Drive visuals from business questions

- Every visual must answer a **real business question** — state it for each.
- The number of pages and visuals follows the reporting objectives. A focused
  two-visual report can be the right answer.
- Advanced visuals are **opt-in**, included only when they add genuine value for
  this dataset and audience: Decomposition Tree, Waterfall, Map, KPI cards,
  Drill-through pages, What-if parameters. If they don't help, don't add them.
- Add a Data Quality monitoring page **only** if DQ flags were actually created
  and the client needs to monitor them.

## Specify every included visual fully

Write each visual as:

**Visual N: [Exact Power BI visual type] — [Business question it answers]**
- Position: [where on the page]
- Visual type: [exact Power BI visual name]
- Fields:
  - [Well: Axis / Rows / Columns / Values / Legend / Tooltips / Filters]: `table.column` or `table.measure`
- Title: "[exact title text]"
- Formatting: [data labels on/off, conditional formatting rule + colors, sort column + direction, number format e.g. `$#,##0` or `0.0%`]
- Interaction: [cross-filter / drill / slicer scope]

## Page organization (only what the objectives require)

- **Executive summary page** (if leadership is the audience): a small row of the
  few KPIs that matter, then 1–3 charts answering the top questions.
- **Analytical page** (if deep-dive is needed): trend, breakdown, and comparison
  visuals; add hierarchy drill-down only if the data has real hierarchy.
- Use only the pages that serve the stated objectives.

## Slicers

For each slicer the audience actually needs, specify: field, slicer type
(dropdown / list / between for dates), default selection, and sync scope across
pages. Don't add slicers for fields nobody will filter on.

## Best practices (apply where relevant)

- Chart-selection rationale (why bar vs. line vs. donut for this question).
- Sorting strategy per visual (usually by the measure, descending).
- Disciplined palette: one consistent scheme, max 5–7 colors.
- Conditional formatting tied to a real threshold or business rule.
- Dynamic titles via DAX when the title should reflect the selection.
- Tooltip pages, drill-through, mobile layout, bookmarks/navigation — each only
  when it adds value, not by default.

## Example (illustrative — adapt to the real questions)

**Visual 1: Card — "What is total revenue in the selected period?"**
- Position: top-left
- Visual type: Card
- Fields:
  - Value: `sales.Total Sales`
- Title: "Total Revenue"
- Formatting: number format `$#,##0`; no decimals
- Interaction: filtered by the page date slicer

**Visual 2: Clustered Column Chart — "Which regions drive the most revenue?"**
- Position: top-right, half width
- Visual type: Clustered Column Chart
- Fields:
  - X-axis: `customer.Region`
  - Y-axis: `sales.Total Sales`
- Title: "Revenue by Region"
- Formatting: data labels on; sort by `sales.Total Sales` descending; `$#,##0`
- Interaction: cross-filters the table below on click
