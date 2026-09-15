# Repository audit and implementation decisions

Inspected every tracked source file before implementation (2026-09-15).

The original repository is a prompt-based skill, not an application. `powerbi-analyst/SKILL.md`
orchestrates six references: data study, Power Query, relationships, DAX measures,
visualization blueprint, and governance. There are no existing runtime agents,
functions, package manifests, executors, APIs, or tests. The six references contain
the reusable reasoning: classify before transforming, retain meaningful nulls,
infer grain before relationships, justify measures, and select visuals by question.

Execution currently ends at phase 2 (M Markdown), phase 3 (relationship scripts),
phase 4 (measure scripts), and phase 5 (manual visualization instructions).
The `createOrReplace` examples are scripts, not serialized TMDL folder definitions;
the new file adapter must serialize model objects without wrapping them in scripts.

Smallest extension: preserve all six references and the original artifact workflow;
add an autonomous workflow to the skill and a separately installable Python package.
Structured plans are the seam between the existing AI reasoning and execution.
The CLI includes a conservative deterministic planner for common data, and accepts
full model/report plans created by an agent using the original references. It does
not pretend that column-name heuristics replace a language model's domain reasoning.

## Boundaries

- `analysis`: file/database discovery and exact bounded profiling.
- `planning`: conservative model and report planning, arbitrary agent-authored plans.
- `model`: M/DAX generation and TMDL serialization.
- `report`: schema-based PBIR, dynamic pages, layout and theme.
- `adapters`: file executor, discovered MCP operations, official report CLI, Desktop.
- `validation`: references, relationships, layout, schemas, runtime evidence.
- `orchestrator`: persistent state, staged writes, backup/checkpoint, rollback.
- `qa`: bounded screenshot/reviewer loop with explicit evidence levels.

Offline files can be structurally validated, but DAX/M execution, refresh and rendered
quality require Power BI runtime capabilities. The result records these separately;
absence of Desktop is never reported as a passed runtime or visual test.

## Environment discovery

Python, Node, npm and .NET are present. Python openpyxl, jsonschema, pytest and MCP
SDK are present; pyodbc is absent. No Power BI process, executable in the usual
Desktop locations, Modeling MCP registration, or global Power BI npm package was
found during the initial checks. The three Microsoft packages were subsequently
installed locally and exercised against their actual advertised contracts. Microsoft source repos
were cloned into sibling reference directories, outside this repository.

Follow-up discovery found the Microsoft Store installation of Power BI Desktop
2.157.1354.0. The original checks missed its versioned WindowsApps location.
After setting the discovered executable path, the official Desktop Bridge opened
the sample and connected; live model queries and screenshots became available.
The adapter includes Store package discovery so this is not a manual setup step.

Official references inspected:

- https://github.com/microsoft/powerbi-modeling-mcp (MCP supports local TMDL folders,
  runtime models, tools/list discovery, transactions and DAX queries).
- https://github.com/microsoft/skills-for-fabric/tree/main/skills/powerbi-report-authoring
  (PBIR authoring and CLI validation; embedded `powerbi-report-authoring` is a
  different API and is not the local project authoring CLI).
- https://learn.microsoft.com/power-bi/developer/projects/projects-overview
- https://learn.microsoft.com/power-bi/developer/projects/projects-report

Adapters use explicit command argument arrays, timeouts, and capability discovery.
Desktop report reload is not assumed to reload semantic model definitions. The
builder does not edit binary PBIX or use coordinate-based UI automation.
