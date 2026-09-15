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

The current writer adds a title/subtitle and optional page navigator to ordinary
pages. Reserve the top 144 logical pixels for that chrome; top-right filters may
occupy its free area. Data visuals usually begin at y=160. Tooltip pages omit
this chrome. Layout can vary below it; respect the actual page dimensions.

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
