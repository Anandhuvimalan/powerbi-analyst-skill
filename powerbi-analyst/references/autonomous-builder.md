# Autonomous PBIP execution

The original six references remain the modeling and design knowledge. The Python
package alongside this skill adds execution, validation, transactions and QA.
Install the repository package; copying this skill folder alone retains artifact
mode but does not install the executor. Run `powerbi-agent doctor` to discover it.

## Agent-driven workflow

1. Receive source paths, business objective and a `.pbip` target. Run
   `powerbi-agent plan --project <target.pbip> --data <source> --goal <objective>`.
   Read its `output/plan/profile.json` before modifying any plan. Original source
   rows are not written into the profiling artifact.
2. Apply `data-study.md`, `power-query.md`, `tmdl-relationships.md`,
   `tmdl-measures.md`, `visualization-blueprint.md` and `governance.md` where
   relevant. Review `model-plan.json` and author a fresh `report-plan.json` with the business
   meaning, correct grain, advanced measures, source-specific preparation, useful
   hierarchies, report questions, and visual design. Do not mistake generated
   column-name heuristics for verified business facts.
3. Pass those files as `model_plan` and `report_plan` in a request JSON, then run
   `powerbi-agent build request.json`. Request paths resolve relative to the JSON.
   Build writes actual tables/partitions/relationships/measures and bound visuals.
   The executor validates plans, stages files, validates report definitions,
   checkpoints the target and publishes only after validation.
   Also author `analysis_brief` using
   `project-design.md`. Agent mode is the default. An explicit `--bootstrap` build is
   only a technical example; do not present it as the host agent's design work.
4. Prefer `modeling.mode: "mcp"` when Microsoft's Modeling MCP is installed.
   It loads the staged model, creates measures through MCP and exports canonical
   TMDL. `file` mode serializes TMDL directly. Neither offline path runs a data
   refresh or evaluates DAX. Do not claim it does.
5. Open/refresh the resulting PBIP with Desktop when available. Run
   `powerbi-agent verify-runtime <project.pbip> --desktop`
   against the resulting Desktop model to execute measure checks. Review results,
   missing periods and totals against source data. Alternatively use
   `--connection-env <variable>` for an explicit endpoint. On Windows/English
   Desktop, `--native-refresh` optionally invokes the named native Refresh
   command, because the current bridge exposes no data-refresh method.
   `examples/sales-desktop-request.json` demonstrates build/open/refresh/verify
   in one request. This accessibility fallback never authors models or visuals.
6. Set `visual_qa: true`, a Desktop PID when ambiguous, and a configured vision
   reviewer command for screenshot review. The loop is bounded, saves screenshots
   and scores, validates geometry changes, and checkpoints refinements. Without a
   vision reviewer, report visual QA as unavailable rather than inventing scores.

For a standalone autonomous AI run, `reasoning.command` receives the original
skill, structured data profiles, brand and a provisional model scaffold. No report
template is supplied. It must return both complete
plans and an analysis brief as JSON. A host agent can instead perform step 2
itself. No particular AI
vendor, API key or cloud upload is silently selected.

## Execution plan contract

Inspect an emitted plan for exact structure. Model plans carry `tables` with
columns and complete `m` expressions; `measures` with table/name/expression/format,
business `reason`, and optional checks; `relationships` with exact endpoints,
proven unique one-side keys and activation; optional named `expressions`,
`calculation_groups` and `roles`. Tables may include justified column DAX,
hierarchies, number formats and hidden technical fields.

Report plans carry theme, canvas size, pages and visuals. Each visual needs a
business `question`, a supported PBIR type, exact role bindings and a position.
Use the installed Microsoft report CLI `catalog describe` and `formatting` commands
to discover current roles and formatting; never invent preview APIs. Rich PBIR
formatting/filter objects may be supplied in plans. Drillthrough pages and native
page navigation are supported; tooltip pages and visual tooltip bindings must
be justified and validated. No fixed dashboard is required.

## Safety and evidence

- Do not hand-edit a binary PBIX or automate Desktop clicks as the main path.
- Save manual Desktop edits before file authoring. A managed-file hash mismatch
  blocks overwrites. Existing unmanaged analytical projects require a reviewed
  migration or a separate output target; the builder never blindly replaces them.
- Each publication has a ZIP backup and, when Git is available, an independent
  Git checkpoint. The user's Git index is never reset or repurposed.
- Preserve all errors and intermediate plans. Runtime/visual failures after file
  publication leave the structurally validated project available with explicit
  incomplete verification status.
- Avoid inventing advanced KPIs or forcing calculation groups/RLS. Arbitrary
  DAX/M stays possible through the full plans; correctness requires runtime tests.
