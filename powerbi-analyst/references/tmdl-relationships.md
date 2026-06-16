# Phase 3 — TMDL relationships (professional model design)

Output file: `relationships.tmdl.md`. Paste-ready, ZERO comments, ONLY TMDL
syntax. Model the data the way an experienced Power BI developer would — based on
the real grain and keys, never on a template.

## Design the model from the data — do not force a shape

1. **Find the grain of each table.** What does one row represent (one order
   line, one transaction, one customer, one day)? The fact table is the one at
   the finest event/transaction grain with numeric measures. Everything that
   merely describes an entity referenced by the fact is a dimension.
2. **Identify facts vs. dimensions.**
   - Fact = events/measurements, many rows, foreign keys + measures.
   - Dimension = descriptive entities (customer, product, date, region), fewer
     rows, a unique key + attributes.
3. **Prefer a clean star schema when the data supports it** — one fact in the
   middle, dimensions around it, single-direction filters flowing dimension →
   fact. This is the professional default *when it fits*.
4. **Do not force it.** If the source is a single flat table with no separable
   entities, keep it as one table and say so in Assumptions. Never invent
   dimensions or split columns into fake tables just to "look like" a star.
5. **Avoid unnecessary snowflaking.** Only chain dimension → dimension when the
   sub-entity genuinely has its own attributes and reuse; otherwise flatten it
   into the parent dimension.

## Keys — handle them like a professional

- The **"one" side key must be unique and non-null**. Verify this (it was
  enforced in Power Query). If it isn't unique, the relationship is invalid —
  fix the grain or deduplicate the dimension first.
- Match data types exactly on both sides (text-to-text, integer-to-integer).
  Type mismatches silently break joins.
- Prefer a single-column key. If the source only has a composite key, create a
  merged key column in Power Query on both tables and relate on that.
- Use the natural key when it is clean and stable; introduce a surrogate
  (index) key only when natural keys are dirty, composite, or unstable — and
  build it in Power Query, not here.

## Cardinality & filter direction

- Default is **many-to-one, single-direction** (fact-to-dimension), filter
  flowing from the "one" (dimension) side to the "many" (fact) side.
- Use **bi-directional** filtering only when a specific need justifies it (e.g.,
  a bridge table for many-to-many, or cross-filtering a dimension by a fact).
  Justify every bi-directional relationship in Assumptions — never in the file.
- Resolve **ambiguous paths**: if two relationship paths could connect the same
  tables, keep only one active and mark the other inactive. Avoid creating
  ambiguity in the first place.
- Handle genuine **many-to-many** with a bridge/junction dimension (the
  professional approach) rather than a direct M:M relationship where avoidable.

## Role-playing dimensions (e.g., OrderDate, ShipDate, DueDate)

When a fact has several date columns all pointing at one date dimension, you
cannot have multiple active relationships to the same table. Two professional
options:

- **Active + inactive relationships** to a single `date` table, activated in DAX
  with `USERELATIONSHIP` inside specific measures. Mark the secondary ones
  `isActive: false`.
- Or create **separate date tables** (e.g., `orderdate`, `shipdate`) when each
  role needs its own independent slicing on the report.

Choose based on how the report will slice time, and document the choice.

## Rules

- Exact Power BI Desktop TMDL syntax; tab indentation; no unsupported keywords.
- Name each relationship `<fromTable>_to_<toTable>` (foreign key on `fromColumn`
  = many side; primary key on `toColumn` = one side).
- One active relationship per pair of tables; extras `isActive: false`.

## Structure

```
createOrReplace

	relationship Sales_to_Customer
		fromColumn: sales.CustomerKey
		toColumn: customer.CustomerKey
		crossFilteringBehavior: oneDirection

	relationship Sales_to_Product
		fromColumn: sales.ProductKey
		toColumn: product.ProductKey
		crossFilteringBehavior: oneDirection

	relationship Sales_to_OrderDate
		fromColumn: sales.OrderDate
		toColumn: date.Date
		crossFilteringBehavior: oneDirection

	relationship Sales_to_ShipDate
		fromColumn: sales.ShipDate
		toColumn: date.Date
		crossFilteringBehavior: oneDirection
		isActive: false
```

Activate the inactive role-playing relationship inside the relevant measure,
e.g. `CALCULATE([Total Sales], USERELATIONSHIP(sales[ShipDate], date[Date]))`,
and place that measure in `measures.tmdl.md`.
