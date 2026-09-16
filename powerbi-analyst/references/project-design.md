# Project-specific analytical design

The host agent supplies the reasoning. The Python planner is a technical starting
point. Record the decisions below in the analysis brief and embody them in
executable plans. Obtain actual JSON schemas with `scripts/agent.py schemas`.

## Understand the decision before choosing pages

Establish the audience, decisions, observation grain, event dates, available
history, important entities and metric definitions. Distinguish transactions,
snapshots and events: employee snapshots are not additive headcount, stored
percentages are not automatically averaged, and a transaction ID may repeat
across line items. Inspect distributions and cross-field dependencies where the
profile alone cannot establish meaning.

Record observed findings with exact source table/column references, an analytical
implication and explicit assumptions. Do not infer causality from correlation
or invent targets, costs, exits, conversion stages or retention windows.

## Build a story specific to these requirements

Create page architecture from the questions. There is no required overview page,
page count, KPI row or default trio of trend/bar/table. Reuse trustworthy native
visual primitives, not a finished dashboard design.

The same order dataset can support a board's margin/trend review or an operations
team's exception investigation. The former may need a compact performance story
and period comparisons; the latter may need a ranked exception table, product
drillthrough and focused filters. These are possibilities, not layouts to copy.
A workforce snapshot may need composition with no time chart. A finance ledger
needs defensible account groupings before a P&L or variance story is created.

Use visual families by purpose: trends, comparisons, contribution, distributions,
variance, detailed records or relationships. Inspect Microsoft's installed
catalog before authoring less common native visual types and role bindings.
Avoid a map without valid geography or a waterfall without a meaningful additive
bridge. Keep distinct insights. Equal cardinality does not prove equivalent
groupings; inspect the dependency before dropping a dimension.

## Design the reading experience

Decide whether the page should lead with a trend, comparison, exceptions or a few
headline metrics. Size visuals for category counts, labels, number widths and
likely report use. Set a grid and spacing rhythm for that layout, then reuse it
consistently within the project. Do not vary colors and geometry merely to look
different. Choose brand colors if supplied, otherwise a restrained palette.
Preserve semantic colors and verify contrast and rendered text.

The writer emits exactly the authored page elements. There is no reserved header
area, mandatory navigation strip, KPI row, card size or chart grid. Use the whole
canvas. A page's `title` is its tab label, not an automatic heading. Add a
`textbox` with `text` and `text_style` if an on-canvas heading or annotation helps.
Navigation is an explicit `pageNavigator` or other supported native element.

Set top-level canvas dimensions and optional per-page `width`/`height`,
`background`, `display_option` and native `objects`. Visuals accept exact
`position`, `objects`, `container_objects`, `z_index` and `tab_order`. Typography,
card orientation, label units, slicer style and borders come from those authored
objects or the authored theme. Discover the native property names from the
installed Microsoft catalog. `text_style` uses native text-run properties such
as `fontFamily`, `fontSize` (e.g. `22pt`) and `color`.

For intentional section backgrounds, use an unbound shape/textbox/image with
`layer: "background"` and a negative `z_index`. Content stays at nonnegative z.
Backgrounds may sit beneath content; overlapping content visuals still fail
validation. Review custom text/background combinations visually: a palette-level
contrast check does not inspect every native formatting override.

Do not leave everything to Power BI defaults. Author formatting deliberately and
inspect it in Desktop where available. Raw properties are checked by Microsoft's
report validator; static layout checks cannot prove that labels fit when rendered.

## Analysis-brief contract

Write an object containing:

- `audience`: who will use the report.
- `decisions`: actions/questions the report must support.
- `grain`: every source table's name and the meaning of one row.
- `findings`: observation, evidence (`table`, `column`), and implication.
- `pages`: exact report page ID, decision and why the page is needed.
- `design_rationale`: why this story, hierarchy, density and palette fit.
- `assumptions`: unresolved business rules, if any.

Measure reasons and visual questions belong in their respective plans; do not
duplicate them all here. Custom transformed data and advanced DAX may need
authored runtime expectations; unknown expectations remain under review.

## Review before publication

Check that the particular pages follow from the data and business objective.
If a materially different audience or grain would receive the same experience,
revisit the reasoning. Similar needs can reasonably produce similar visuals;
uniqueness is relevance, not random novelty.

Review source totals, filter propagation, chart bindings and screenshots where
the engine is available. Preserve limitations such as missing credentials or
unresolved definitions. A skill directs a capable host agent; it cannot guarantee
an expert result from every model or ambiguous dataset.
