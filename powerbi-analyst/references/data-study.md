# Phase 1 — Dataset Study (always done first)

Before writing any M code, model, measure, or visual, study the data and
produce a written Dataset Study. This is the foundation for every later
decision. A column that needs nothing but a type conversion is a valid and
common outcome.

## Step 1 — Profile each column individually

For every column examine:

- Name and likely meaning
- Sample values and data type
- Cardinality (distinct count vs. row count)
- Null count and null percentage
- Value distribution (range, skew, repeating values, obvious errors)

If you can run code, profile programmatically (e.g., pandas
`df.describe(include='all')`, `df.nunique()`, `df.isna().mean()`). Otherwise
profile from the provided sample rows and reason explicitly.

## Step 2 — Classify each column

Assign each column exactly one role:

| Role | What it is |
|---|---|
| Primary Key | Uniquely identifies a row in a dimension/entity |
| Foreign Key | References a key in another table |
| Transaction Identifier | Identifies a transaction/event (often not unique per row) |
| Date | Calendar/timestamp used for time analysis |
| Numeric Measure | Additive/aggregatable quantity (units, counts, scores) |
| Financial Measure | Money amount (revenue, cost, profit, invoice, price) |
| Percentage | Rate/ratio (0–1 or 0–100) |
| Categorical Attribute | Low-cardinality label used to group/filter |
| Descriptive Text | Free text (names, descriptions, notes) |
| Status Field | Workflow/lifecycle state (Open/Closed, Active/Inactive) |
| Boolean Flag | True/false indicator |
| System Field | Technical/internal (GUIDs, row hashes, source system) |
| Audit Field | CreatedBy/CreatedDate/ModifiedDate and similar |

## Step 3 — Determine business meaning

In plain language, state what each column represents in the business and how it
is likely used in reporting (filter, group-by, aggregate, display-only, key).

## Step 4 — Decide required treatment

Only after Steps 1–3, decide per column whether any of the following is
genuinely required: type conversion, text cleaning, standardization,
missing-value handling, outlier handling, validation, or a derived column.
Many columns need nothing beyond a type conversion.

## Deliverable — Dataset Study table

Present the study as a table, one row per column:

| Column | Classification | Business Meaning | Required Treatment |
|---|---|---|---|
| OrderDate | Date | Date the order was placed; primary time axis | Convert to date; keep nulls → filter if essential |
| Discount | Numeric Measure | Discount applied; 0 is valid | Convert to number; null → 0 (zero is business-valid) |
| CustomerEmail | Descriptive Text | Contact email; display only | Trim; keep nulls (no imputation) |
| Region | Categorical Attribute | Sales region for grouping | Standardize casing; mode-impute only if justified |
| InternalRowHash | System Field | Source-system technical id | Drop — no reporting value |

For columns where the answer is "nothing needed", write `None needed — <reason>`.

## Calendar / date table decision

Create a calendar table **only** if the model has genuine date columns used for
time-based reporting. If created, include only the attributes the reporting
actually needs (commonly: Date, Year, Quarter, MonthNumber, MonthName; add
WeekNumber, FiscalYear, IsWeekend, etc. only when a visual calls for them). Do
not generate a sprawling date table of unused attributes.

A reusable M pattern for a date table is in `power-query.md`.
