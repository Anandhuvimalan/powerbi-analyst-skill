# Phase 3 — TMDL relationships

Output file: `relationships.tmdl.md`. Paste-ready, ZERO comments, ONLY TMDL
syntax.

## Decide the model shape from the data — do not force one

- Build relationships **only** where real keys support them.
- Do **not** invent dimensions or force a star schema onto data that does not
  support one. A single flat table is a valid model when the data is flat — say
  so in Assumptions rather than fabricating dimensions.
- Create only meaningful facts and dimensions. A dimension earns its place when
  a real categorical/descriptive entity is referenced by a key from a fact.
- Prefer one fact table at the data's natural grain; split dimensions out only
  when the source genuinely contains a distinct entity with its own attributes.

## Rules

- Exact Power BI Desktop TMDL syntax.
- Tab indentation.
- No unsupported keywords.
- `crossFilteringBehavior: oneDirection` unless bi-directional is specifically
  justified (and justify it in Assumptions, never in the file).
- Only valid relationships supported by real keys with compatible types.
- Verify the "one" side key is unique; otherwise the relationship is invalid.

## Structure

```
createOrReplace

	relationship Sales_to_Customer
		fromColumn: sales.CustomerKey
		toColumn: customer.CustomerKey
		crossFilteringBehavior: oneDirection

	relationship Sales_to_Date
		fromColumn: sales.OrderDate
		toColumn: date.Date
		crossFilteringBehavior: oneDirection
```

Name each relationship `<fromTable>_to_<toTable>`. Place the foreign key on the
`fromColumn` (many side) and the primary key on the `toColumn` (one side).
