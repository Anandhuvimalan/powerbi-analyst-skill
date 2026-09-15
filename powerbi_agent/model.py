"""M/DAX construction and serialized TMDL (not createOrReplace scripts)."""
from __future__ import annotations

import json
from pathlib import Path

from .core import BuildError, identity, write_json


def tq(value: str) -> str:
    if any(c in value for c in "\r\n\t"):
        raise BuildError("Model object names cannot contain line breaks or tabs.")
    return "'" + value.replace("'", "''") + "'"


def dq(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def mq(value: str) -> str:
    return dq(value.replace("#(", "#(#)(").replace("\r", "#(cr)").replace("\n", "#(lf)").replace("\t", "#(tab)"))


def ref(table: str, column: str) -> str:
    return tq(table) + "[" + column.replace("]", "]]") + "]"


def source_m(source: dict, columns: list[dict]) -> str:
    kind = source["kind"]
    path = mq(source.get("path", ""))
    if kind in {"csv", "tsv"}:
        steps = [f'Source = Csv.Document(File.Contents({path}), [Delimiter={mq(source.get("delimiter", ","))}, Encoding=65001, QuoteStyle=QuoteStyle.Csv])',
                 'Headers = Table.PromoteHeaders(Source, [PromoteAllScalars=true])']
        previous = "Headers"
    elif kind == "xlsx":
        steps = [f'Source = Excel.Workbook(File.Contents({path}), null, true)',
                 f'Sheet = Source{{[Item={mq(source["sheet"])},Kind="Sheet"]}}[Data]',
                 'Headers = Table.PromoteHeaders(Sheet, [PromoteAllScalars=true])',
                 'NonBlank = Table.SelectRows(Headers, each List.NonNullCount(Record.FieldValues(_)) > 0)']
        previous = "NonBlank"
    elif kind == "json":
        steps = [f'Source = Table.FromRecords(Json.Document(File.Contents({path})), null, MissingField.UseNull)']
        previous = "Source"
    elif kind == "sqlserver":
        if not source.get("server") or not source.get("database"):
            raise BuildError("SQL Server sources need server and database for the native Power Query connector.")
        steps = [f'Source = Sql.Database({mq(source["server"])}, {mq(source["database"])})',
                 f'Navigation = Source{{[Schema={mq(source.get("schema", "dbo"))},Item={mq(source["table"])}]}}[Data]']
        previous = "Navigation"
    elif kind == "sqlite":
        raise BuildError("SQLite is profiled directly and snapshotted to a project CSV before M serialization.")
    else:
        raise BuildError(f"No M connector for {kind}")
    types = {"string": "type text", "int64": "Int64.Type", "double": "type number", "decimal": "Currency.Type", "dateTime": "type date", "boolean": "type logical"}
    # Type text first for keys; this preserves leading-zero identifiers in CSV.
    pairs = ", ".join("{" + mq(c["name"]) + ", " + types[c["data_type"]] + "}" for c in columns)
    # CSV blanks must become null before numeric/date conversion.
    if kind in {"csv", "tsv"}:
        cols = ", ".join(mq(c["name"]) for c in columns)
        steps.append(f'EmptyToNull = Table.ReplaceValue({previous}, "", null, Replacer.ReplaceValue, {{{cols}}})')
        previous = "EmptyToNull"
    trims = [c for c in columns if c.get("trim")]
    if trims:
        operations = ", ".join("{" + mq(c["name"]) + ', each if _ = null then null else if Text.Trim(Text.From(_)) = "" then null else Text.Trim(Text.From(_)), type nullable text}' for c in trims)
        steps.append(f"Trimmed = Table.TransformColumns({previous}, {{{operations}}})")
        previous = "Trimmed"
    steps.append(f'Typed = Table.TransformColumnTypes({previous}, {{{pairs}}}, "en-US")')
    return "let\n    " + ",\n    ".join(steps) + "\nin\n    Typed"


def dimension_m(table: str, columns: list[str], key: str) -> str:
    names = ", ".join(mq(c) for c in columns)
    return (f"let\n    Source = #{mq(table)},\n    Selected = Table.SelectColumns(Source, {{{names}}}),\n"
            f"    NonNullKeys = Table.SelectRows(Selected, each Record.Field(_, {mq(key)}) <> null),\n"
            "    Unique = Table.Distinct(NonNullKeys)\nin\n    Unique")


def date_m(date_fields: list[tuple[str, str]]) -> str:
    lists = ", ".join(f'Table.Column(#{mq(t)}, {mq(c)})' for t, c in date_fields)
    return f'''let
    Observed = List.RemoveNulls(List.Combine({{{lists}}})),
    StartDate = Date.StartOfYear(Date.From(List.Min(Observed))),
    EndDate = Date.EndOfYear(Date.From(List.Max(Observed))),
    Dates = List.Dates(StartDate, Duration.Days(EndDate - StartDate) + 1, #duration(1,0,0,0)),
    Source = Table.FromList(Dates, Splitter.SplitByNothing(), {{"Date"}}),
    Typed = Table.TransformColumnTypes(Source, {{{{"Date", type date}}}}),
    Year = Table.AddColumn(Typed, "Year", each Date.Year([Date]), Int64.Type),
    Quarter = Table.AddColumn(Year, "Quarter", each "Q" & Text.From(Date.QuarterOfYear([Date])), type text),
    MonthNumber = Table.AddColumn(Quarter, "MonthNumber", each Date.Month([Date]), Int64.Type),
    Month = Table.AddColumn(MonthNumber, "Month", each Date.MonthName([Date], "en-US"), type text),
    YearMonth = Table.AddColumn(Month, "YearMonth", each Date.ToText([Date], "yyyy-MM"), type text)
in
    YearMonth'''


class TmdlWriter:
    def apply(self, folder: Path, plan: dict) -> list[str]:
        folder.mkdir(parents=True, exist_ok=True)
        write_json(folder / "definition.pbism", {"version": "4.0", "settings": {}})
        definition = folder / "definition"
        (definition / "tables").mkdir(parents=True, exist_ok=True)
        (definition / "database.tmdl").write_text("database\n\tcompatibilityLevel: 1601\n", encoding="utf-8")
        model = ["model Model", "\tculture: en-US", "\tdefaultPowerBIDataSourceVersion: powerBI_V3",
                 "\tsourceQueryCulture: en-US", "\tdataAccessOptions", "\t\tlegacyRedirects", "\t\treturnErrorValuesAsNull",
                 "", "\tannotation PBI_QueryOrder = " + json.dumps([t["name"] for t in plan["tables"]]),
                 "\tannotation __PBI_TimeIntelligenceEnabled = 0", ""]
        if plan.get("calculation_groups"):
            model.insert(1, "\tdiscourageImplicitMeasures")
        model.extend("ref table " + tq(t["name"]) for t in plan["tables"])
        for group in plan.get("calculation_groups", []):
            model.append("ref table " + tq(group["name"]))
        for role in plan.get("roles", []):
            model.append("ref role " + tq(role["name"]))
        (definition / "model.tmdl").write_text("\n".join(model) + "\n", encoding="utf-8")
        for table in plan["tables"]:
            (definition / "tables" / (identity(table["name"]) + ".tmdl")).write_text(self.table(table, plan), encoding="utf-8")
        rels = []
        for rel in plan.get("relationships", []):
            rels += ["relationship " + tq(rel["name"]),
                f'\tfromColumn: {tq(rel["from_table"])}.{tq(rel["from_column"])}',
                f'\ttoColumn: {tq(rel["to_table"])}.{tq(rel["to_column"])}',
                "\tfromCardinality: many", "\ttoCardinality: one", "\tcrossFilteringBehavior: oneDirection"]
            if not rel.get("active", True):
                rels.append("\tisActive: false")
            rels.append("")
        if rels:
            (definition / "relationships.tmdl").write_text("\n".join(rels), encoding="utf-8")
        if plan.get("expressions"):
            expressions = []
            for exp in plan["expressions"]:
                expressions.append("expression " + tq(exp["name"]) + " =")
                expressions.extend("\t" + line for line in exp["expression"].splitlines())
                expressions.append("")
            (definition / "expressions.tmdl").write_text("\n".join(expressions), encoding="utf-8")
        for group in plan.get("calculation_groups", []):
            lines = ["table " + tq(group["name"]), "\tcalculationGroup", f'\t\tprecedence: {group.get("precedence", 10)}']
            for index, item in enumerate(group["items"]):
                lines += [f'\t\tcalculationItem {tq(item["name"])} = {item["expression"]}', f"\t\t\tordinal: {index}"]
                if item.get("format_expression"):
                    lines += ["\t\t\tformatStringDefinition = " + item["format_expression"]]
            lines += ["\tcolumn Name", "\t\tdataType: string", "\t\tsourceColumn: Name", "\t\tsummarizeBy: none"]
            (definition / "tables" / (identity(group["name"]) + ".tmdl")).write_text("\n".join(lines) + "\n", encoding="utf-8")
        for role in plan.get("roles", []):
            target = definition / "roles" / (identity(role["name"]) + ".tmdl")
            target.parent.mkdir(exist_ok=True)
            lines = ["role " + tq(role["name"]), "\tmodelPermission: read"]
            lines.extend(f'\ttablePermission {tq(t)} = {expr}' for t, expr in role["filters"].items())
            target.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return [str(p.relative_to(folder)) for p in sorted(folder.rglob("*")) if p.is_file()]

    @staticmethod
    def table(table: dict, plan: dict) -> str:
        lines = ["table " + tq(table["name"])]
        if table.get("is_date"):
            lines += ["\tdataCategory: Time"]
        if table.get("hidden"):
            lines += ["\tisHidden"]
        for measure in [m for m in plan["measures"] if m["table"] == table["name"]]:
            lines += ["", f'\tmeasure {tq(measure["name"])} = {measure["expression"]}',
                      "\t\tformatString: " + dq(measure.get("format", "#,##0.00")),
                      "\t\tdisplayFolder: " + dq(measure.get("folder", "KPIs"))]
        for column in table["columns"]:
            expression = " = " + column["expression"] if column.get("expression") else ""
            lines += ["", "\tcolumn " + tq(column["name"]) + expression, "\t\tdataType: " + column["data_type"], "\t\tsummarizeBy: none"]
            if not expression:
                lines += ["\t\tsourceColumn: " + dq(column.get("source_column", column["name"]))]
            if column.get("hidden"):
                lines += ["\t\tisHidden"]
            if column.get("is_key"):
                lines += ["\t\tisKey"]
            if column.get("sort_by"):
                lines += ["\t\tsortByColumn: " + tq(column["sort_by"])]
            if column.get("category"):
                lines += ["\t\tdataCategory: " + column["category"]]
            fmt = column.get("format", "yyyy-MM-dd" if column["data_type"] == "dateTime" else None)
            if fmt:
                lines += ["\t\tformatString: " + dq(fmt)]
        for hierarchy in table.get("hierarchies", []):
            lines += ["", "\thierarchy " + tq(hierarchy["name"])]
            for ordinal, col in enumerate(hierarchy["levels"]):
                lines += ["\t\tlevel " + tq(col), f"\t\t\tordinal: {ordinal}", "\t\t\tcolumn: " + tq(col)]
        lines += ["", "\tpartition " + tq(table["name"]) + " = m", "\t\tmode: import", "\t\tsource ="]
        lines.extend("\t\t\t" + line for line in table["m"].splitlines())
        return "\n".join(lines) + "\n"
