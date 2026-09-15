# End-to-end demo and verification

`examples/sales.csv` is a deterministic, fictitious dataset: 1,200 order rows,
80 customers, four products, four regions and dates across 2024–2025. Recreate it
with `python scripts/make_demo_data.py`.

```powershell
python -m powerbi_agent build examples/sales-request.json
python scripts/integration_smoke.py --remote-schema
python -m powerbi_agent build examples/sales-desktop-request.json --output ../output/FinalSales/FinalSales.pbip
```

The first command exercises direct file execution. The second uses the installed
Microsoft Modeling MCP server and full PBIR schema validation, and separately
tests advanced calculation-group, named-expression and RLS TMDL parsing.

## Created artifacts

- Actual `.pbip`, `.Report` and `.SemanticModel` artifacts, with `.platform` metadata.
- `sales`, `DimProduct`, `DimCustomer`, `DimDate`; three single-direction relationships.
- M source preparation, dimensions and a dynamic full-year calendar.
- Ten measures: quantity, revenue, cost, orders, customers, profit, margin,
  average order value, previous-year revenue and YoY percentage.
- Four pages: sales overview, product, region and hidden entity
  drillthrough; bound charts/tables/cards, year and segment slicers, native
  navigation and a restrained theme.
- Persistent profiling, plans, source-derived runtime checks, validation evidence,
  checkpoints and, in the live run, screenshots.

No binary PBIX is modified. The original reference guides remain unchanged.

## Observed validation

The real Microsoft server loaded the generated model, created all ten measures
through MCP and exported canonical TMDL. The advanced sample model also loaded
through TOM. Microsoft's full PBIR validation returned zero errors and warnings.

The final all-in-one Desktop build is `output/FinalSales/FinalSales.pbip`.
Its report has four pages: the sample's product category and product name have
proven identical entity groupings, so only the more descriptive product-name
analysis is retained. Earlier five-page verification runs remain separately under
`output/McpSales`, `output/VerifiedSales` and `output/AutonomousSales`.

Windows Store Power BI Desktop **2.157.1354.0** was found during final verification.
Its secure local API bridge exposed report reload and screenshots. The CLI's
default executable search missed this Store installation; the adapter now
discovers the registered Store package and supplies `PBI_DESKTOP_PATH` locally.

The generated project opened in Desktop and source loading succeeded. The
all-in-one Desktop request also ran native Refresh and DAX verification.
The expanded suite contains 36 checks covering grand totals, fact-category
contexts, both dimension relationships and explicit year comparisons:

| Metric | Full dataset |
|---|---:|
| Revenue | 403,637 |
| Cost | 230,019 |
| Profit | 173,618 |
| Margin | 43.0134006545% |
| Quantity | 5,425 |
| Orders | 1,200 |
| Customers | 80 |
| Average order value | 336.3641667 |

Runtime results are saved as `runtime-results.json` and comparisons in the run's
`state.json`. Year-over-year checks use explicit calendar-year contexts rather
than interpreting a multi-year grand total as one year's growth.

The first real screenshot exposed a clipped subtitle, overly granular trend,
rounded order count and hidden-page navigation. The builder was refined from
that evidence. A screenshot captured immediately after reload was nearly blank;
the Desktop adapter now checks for near-uniform captures and retries at most
three times instead of treating an empty capture as successful visual QA.

The final demo's Desktop snapshots are under `output/FinalSales/screenshots/`. The
integration evidence file is `output/integration-evidence.json`. Host-agent visual
review and any external vision-provider loop are distinct from structural checks.
The final host review is `output/FinalSales/host-visual-review.json`: four real
screenshots, a subjective 90.4/100 score, and recorded nonblocking improvements.
It does not claim that a separately configured vision-provider loop ran.

Native refresh is an optional English-UI accessibility invocation, not mouse
automation. It was added after Desktop XMLA refresh hung. The bridge's report
reload does not reload the semantic model. A successful native command dispatch
alone is not counted as a verified refresh: live expected-result checks follow.

## Test coverage

The regression suite covers profiling/null preservation, duplicate and ambiguous
inputs, XLSX and SQLite readers, key/relationship inference, date roles, contextual
DAX, M escaping, advanced TMDL, dynamic report plans, PBIR resource bindings,
layout/contrast, CLI diagnostics, deterministic rebuilds, failed adapters,
partial-publication rollback, drift protection, MCP schema/error behavior,
Desktop PID selection, bounded screenshot QA, reasoning-provider contracts and
independent runtime result comparisons.

The final regression run passed **48 tests**. Run `python -m pytest -q`.
Microsoft integration tests are separate from the unit
suite so an environment without Desktop/MCP can still test file execution and
adapter contracts. CI runs the Python suite on Windows and Linux.
