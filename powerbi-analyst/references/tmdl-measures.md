# Phase 4 — TMDL measures

Output file: `measures.tmdl.md` (one per model). Paste-ready, ZERO comments,
ONLY TMDL syntax.

## Create only meaningful measures

Create **only** measures that answer a real business question for THIS dataset.
Do **not** auto-create YoY Growth, Margin %, Return Rate, Running Total, Average
Order Value, or any other "standard" measure unless the data supports the
calculation and a reporting objective needs it. Every measure must have a
business justification — stated in the Assumptions/Justifications section, never
inside the TMDL file.

Checklist before adding a measure:

- Does a stated (or clearly implied) business question require it?
- Do the required columns exist at the right grain?
- Is it distinct from existing measures (not a trivial restatement)?

## Rules

- One `measures.tmdl.md` file per model; may contain multiple `ref table`
  sections.
- Measures live under `ref table`.
- Single-line DAX only.
- No `expression` keyword. No braces around the measure body.
- Always include `formatString`.
- Use `displayFolder` where it aids organization.
- Tab indentation. Paste-ready. ZERO comments.

## Measure placement

- Revenue / margin / amount KPIs → the fact table.
- Dimension counts → the respective dimension.
- Model-wide KPIs → the primary fact table.

## Canonical structure

```
createOrReplace

	ref table sales

		measure 'Total Sales' = SUM(sales[SalesAmount])
			formatString: "\$#,##0"
			displayFolder: KPIs

		measure 'Order Count' = DISTINCTCOUNT(sales[OrderId])
			formatString: 0
			displayFolder: KPIs

	ref table product

		measure 'Total Products' = COUNTROWS(product)
			formatString: 0
```

## Common patterns (use only when justified by the data)

- Margin %: `DIVIDE([Total Profit], [Total Sales])` with `formatString: "0.0%"`
  — only if both profit and sales exist.
- YoY Growth: time-intelligence over a real date table — only if a contiguous
  date dimension exists.
- Running Total: `CALCULATE([Total Sales], FILTER(ALL(date[Date]), date[Date] <= MAX(date[Date])))`
  — only if a date table exists and cumulative analysis is requested.

Always wrap division in `DIVIDE(...)` to avoid divide-by-zero.
