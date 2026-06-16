# Phase 2 — Power Query (M) engineering

Apply **only** the transformations the Dataset Study justified. Do not add
columns, flags, or derived fields that no report needs. One `.md` file of M code
per table. Every M file is paste-ready with ZERO comments and contains the full
exact source path.

## Naming standards

- Table names: lowercase
- Columns: PascalCase
- Key columns: end with `Key`
- No spaces in physical column names

## Source connectors — detect the source type and use the right one

Use the exact full path provided. Replace the path and item names with the real
values. Never use relative paths or omit the `Source` step.

### CSV

```
let
    Source = Csv.Document(File.Contents("C:\Full\Exact\Path\file.csv"), [Delimiter=",", Encoding=65001, QuoteStyle=QuoteStyle.Csv]),
    PromotedHeaders = Table.PromoteHeaders(Source, [PromoteAllScalars=true])
in
    PromotedHeaders
```

### Excel (.xlsx / .xls) — by sheet

```
let
    Source = Excel.Workbook(File.Contents("C:\Full\Exact\Path\file.xlsx"), null, true),
    SheetData = Source{[Item="Sheet1",Kind="Sheet"]}[Data],
    PromotedHeaders = Table.PromoteHeaders(SheetData, [PromoteAllScalars=true])
in
    PromotedHeaders
```

### Excel — by named table

```
let
    Source = Excel.Workbook(File.Contents("C:\Full\Exact\Path\file.xlsx"), null, true),
    TableData = Source{[Item="SalesTable",Kind="Table"]}[Data]
in
    TableData
```

### JSON (records → table)

```
let
    Source = Json.Document(File.Contents("C:\Full\Exact\Path\file.json")),
    ToTable = Table.FromRecords(Source)
in
    ToTable
```

### Folder of like files (combine)

```
let
    Source = Folder.Files("C:\Full\Exact\Path\Folder"),
    Filtered = Table.SelectRows(Source, each [Extension] = ".csv"),
    AddData = Table.AddColumn(Filtered, "Data", each Csv.Document([Content], [Delimiter=",", Encoding=65001, QuoteStyle=QuoteStyle.Csv])),
    Expanded = Table.Combine(Table.Column(AddData, "Data")),
    PromotedHeaders = Table.PromoteHeaders(Expanded, [PromoteAllScalars=true])
in
    PromotedHeaders
```

For other sources (Parquet, databases, APIs), use the corresponding native
connector (`Parquet.Document`, `Sql.Database`, `Web.Contents`, etc.) following
the same pattern: explicit source, then minimal necessary steps.

## Transformation order (only for steps you actually use)

This is the correct **order** for whichever steps the study justified — not a
list of mandatory steps:

1. Source (with full path) — always
2. Promote headers — always
3. Type conversion — as needed
4. Remove blank rows — only if present
5. Clean text fields — only if needed
6. Replace / standardize invalid values — only if needed
7. Missing-value handling — only when a decision other than "keep null" was made
8. Outlier handling — only if warranted
9. Remove duplicates — dimensions only, only if duplicates exist
10. Derived columns — only those that support reporting
11. Rename columns
12. Reorder columns

End with a clean final step name. Be performance-aware.

## Type conversion

- Use `try ... otherwise null` where source values may be malformed:
  `try Number.From([Amount]) otherwise null`, `try Date.From([OrderDate]) otherwise null`.
- Skip the wrapper where data is already clean and well-typed — don't add noise.
- Currency: round to 2 decimals with `Number.Round([Amount], 2)` only if the
  source precision warrants it.

## Missing-value handling — decision-driven, NEVER automatic

Nulls are often a valid, meaningful business state. For **every** column with
nulls, work through:

1. Business meaning of the column
2. Null percentage
3. Impact on reporting
4. Choose ONE action and justify it:
   - **Keep nulls** (frequently correct)
   - **Filter records**
   - **Mean imputation**
   - **Median imputation**
   - **Mode imputation**
   - **Controlled default** (e.g., 0, "Unknown")
   - **Escalate** as a data-quality issue for business review

Mean/median/mode are used **only** when both statistically and business-wise
appropriate, with the reason stated.

Context guardrails:

- **Financial measures** (revenue, profit, cost, sales, invoice, price): do not
  blindly impute. A missing amount usually means "no transaction" or a data
  issue → keep null, filter, or escalate. Do not fabricate value.
- **Project-management data** (task dates, status, completion %, owner,
  priority, milestone): blanks usually mean "not started" / "unassigned" / "not
  set" — real states. Keep null.
- **Operational data**: missing values are often legitimate states → keep null.
- **Customer data** (name, email, phone, address): never statistically impute.
  Use a controlled default ("Unknown"/"N/A") only if a non-null label is
  required for reporting; otherwise keep null.
- **Keys**: never impute. Null key → filter the row or escalate.
- **Dates**: never impute with mean/median/mode. Keep null, filter, or escalate.

When imputation is genuinely chosen, compute the statistic as a separate step
and round to the original column's precision:

```
ColumnValues = List.RemoveNulls(Table.Column(PreviousStep, "ColumnName")),
MedianValue = List.Median(ColumnValues),
Imputed = Table.ReplaceValue(PreviousStep, null, MedianValue, Replacer.ReplaceValue, {"ColumnName"})
```

Use `List.Average` for mean and `List.Mode(List.RemoveNulls(...))` for mode.
Document each imputed column, the method, and the reason in Assumptions.

## Text / categorical cleaning

- `Text.Trim(Text.Clean([Column]))` only where whitespace/control chars actually
  appear or would break joins.
- Convert `""` to null: `if [Column] = "" then null else [Column]`.
- Standardize casing/spelling variants (`"active"/"ACTIVE"` → `"Active"`) only
  for low-cardinality categorical/status fields used to group or filter. Do not
  reformat descriptive free text.
- Standardize key columns (trim, consistent type) when join integrity needs it.

## Outlier handling — not mandatory

Detection is **not** a required step. First verify: the column is a true
numeric/financial measure; outliers would actually distort the intended
reporting; and the extremes are not legitimate business events (bulk orders, VIP
transactions, refunds, spikes). If treatment is unnecessary, skip it and say so.

If warranted, detect with IQR:

```
ColumnValues = List.RemoveNulls(Table.Column(PreviousStep, "ColumnName")),
Q1 = List.Percentile(ColumnValues, 0.25),
Q3 = List.Percentile(ColumnValues, 0.75),
IQR = Q3 - Q1,
LowerBound = Q1 - (1.5 * IQR),
UpperBound = Q3 + (1.5 * IQR)
```

Then choose: correct/null+median-impute clear data-entry errors; **flag** (not
remove) legitimate extremes; or cap/Winsorize only when extremes distort
aggregations. If more than ~5% of rows fall outside the bounds, the distribution
is naturally wide — do not treat as outliers. Never apply outlier logic to keys,
dates, booleans, or categorical text. Document every outlier decision, including
the decision NOT to treat.

## Data-quality checks — only where relevant

Do **not** auto-generate `DataQualityFlag` columns, duplicate flags,
invalid-value flags, or missing-value reports. Add them only when justified —
e.g., duplicates would corrupt a dimension or double-count a measure, null keys
would break a relationship, or the client explicitly needs DQ monitoring. Keep
any such checks minimal and purposeful.

## Reusable date table (only if needed)

```
let
    StartDate = #date(2020, 1, 1),
    EndDate = #date(2026, 12, 31),
    DayCount = Duration.Days(EndDate - StartDate) + 1,
    Dates = List.Dates(StartDate, DayCount, #duration(1, 0, 0, 0)),
    ToTable = Table.FromList(Dates, Splitter.SplitByNothing(), {"Date"}),
    TypedDate = Table.TransformColumnTypes(ToTable, {{"Date", type date}}),
    AddYear = Table.AddColumn(TypedDate, "Year", each Date.Year([Date]), Int64.Type),
    AddQuarter = Table.AddColumn(AddYear, "Quarter", each "Q" & Text.From(Date.QuarterOfYear([Date])), type text),
    AddMonthNumber = Table.AddColumn(AddQuarter, "MonthNumber", each Date.Month([Date]), Int64.Type),
    AddMonthName = Table.AddColumn(AddMonthNumber, "MonthName", each Date.MonthName([Date]), type text)
in
    AddMonthName
```

Adjust the date range to the data's actual min/max. Add or remove attribute
columns based on what the reporting requires.
