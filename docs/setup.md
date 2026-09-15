# Setup and operation

## Local execution

Requires Python 3.11+ and Node 20+. Windows is required for Power BI Desktop.
From the repository root:

```powershell
python -m pip install -e ".[test]"
npm ci
python -m powerbi_agent doctor
python -m pytest -q
```

Installing the Python package also provides `powerbi-agent`. Running
`python -m powerbi_agent` directly from the checkout needs no editable install if
its Python dependencies are already available. The original skill may still be
copied into an agent's skills directory as before; the standalone executor is a
separate installation. Installing only the skill folder does not install Python
or Microsoft's packages.

Pinned Microsoft packages, verified during this implementation:

| Package | Version | Use |
|---|---|---|
| `@microsoft/powerbi-modeling-mcp` | `0.5.0-beta.13` | Offline TOM model authoring and live DAX/runtime operations |
| `@microsoft/powerbi-report-authoring-cli` | `0.1.4` | Visual catalog, formatting discovery, PBIR validation |
| `@microsoft/powerbi-desktop-bridge-cli` | `0.1.2` | Desktop discovery, opening, report reload, screenshots |

Packages are installed locally; no global app configuration is modified. The
builder discovers local npm entrypoints or existing global installations. MCP
schemas are discovered using `tools/list` before operations are sent. Upgrade
packages deliberately and rerun integration tests when preview contracts change.

## Build a new project

```powershell
powerbi-agent build --project ./PowerBI-AI-Starter.pbip --data ./sales.xlsx --goal "Analyze revenue, profitability, products and regional trends"
```

The target may be absent or essentially blank. An existing unmanaged analytical
model/report is preserved and rejected as an overwrite target. Use `--output`
to create a new project while leaving it intact. This is a greenfield builder
and a rebuilder of its own managed artifacts, not an automatic migration tool
for arbitrary existing dashboards.

```powershell
powerbi-agent build ./examples/sales-request.json --modeling mcp
```

All request paths, including `output`, resolve relative to the request JSON.
With direct flags, paths resolve relative to the current working directory.
Generated M uses absolute source paths. Moving the dataset requires rebuilding
or editing an explicit source parameter in a reviewed plan.

Source support:

- CSV/TSV: UTF-8, headers, quoted delimiters, optional `delimiter`.
- XLSX: selected `sheet` or all nonempty sheets; cached formula values. Calculate
  and save the workbook first if formula cells lack cached results.
- JSON: flat array of records; union of record keys. Nested data requires an
  explicit preprocessing/flattening plan.
- Folder: each supported file becomes source tables; explicit naming resolves
  collisions. Files are not blindly appended at potentially different grains.
- SQLite: read-only exact profiling, then an explicit project-owned CSV snapshot.
  This is a snapshot, not a live SQLite refresh connector.
- SQL Server: `pip install '.[sql]'`, an ODBC driver and a read-only connection
  supplied by environment variable. The generated M uses native `Sql.Database`
  navigation; Power BI manages refresh credentials separately.
- Legacy XLS, ambiguous regional dates, nested JSON, composite-key bridges and
  other specialized connectors need explicit preparation or an agent-authored
  plan. They are not silently guessed.

Example SQL source descriptor:

```json
{
  "kind": "sqlserver",
  "name": "Sales",
  "server": "sql.example.internal",
  "database": "Warehouse",
  "schema": "dbo",
  "table": "Sales",
  "connection_env": "SALES_ODBC_CONNECTION"
}
```

Profiling is exact up to `max_rows` (default 100,000). Larger inputs stop with an
actionable budget message; sampled cardinality is never treated as a uniqueness
proof. Numeric precision, grain, snapshot counts and ratios still need domain
review. No missing financial values are fabricated.

## Use the existing AI knowledge

For the portable agent skill and a workflow intended for end users, start with
[Install and use the agent skill](agent-skill.md). Skill-driven builds enable
`agent_mode:true` and supply an analysis brief plus both authored plans; the
bootstrap example commands above deliberately remain available outside that mode.

Run `powerbi-agent plan ...` to obtain `profile.json`, `model-plan.json`, and
`report-plan.json`. An agent uses the original six guides to refine these plans,
then supplies their paths in a build request. This supports arbitrary advanced
DAX and M rather than a closed catalog of measures.

A standalone AI provider can be configured with:

```json
"reasoning": {
  "command": ["C:/Tools/my-planner.exe"],
  "knowledge_root": "C:/Skills/powerbi-analyst"
}
```

The builder appends one argument: the absolute path of a JSON request containing
the original skill, profiles, source descriptors and baseline plans. The command
must return `{"model_plan": {...}, "report_plan": {...}}` on stdout. Authentication
and AI-provider choice belong to the configured command. No cloud provider or
dataset upload is selected by default. This adapter is an integration contract;
the repository does not bundle a paid LLM service or pretend its heuristics are one.

## Desktop, refresh and DAX verification

The Power BI runtime dependency is **Power BI Desktop with a supported
Desktop Bridge build**. Enable the preview option named **Enable external tool
access to Power BI Desktop through secure local APIs**, then restart Desktop.
Availability depends on the Desktop build; consult
[Microsoft's report-authoring documentation](https://github.com/microsoft/skills-for-fabric/tree/main/skills/powerbi-report-authoring)
if the feature is missing. Enable the project/TMDL/PBIR preview features exposed
by your Desktop version as needed.

`auto_open_powerbi: true` uses the official bridge CLI to open the generated
project. File-based TMDL changes require reopening the project; report reload
is not treated as semantic-model reload. No coordinate clicking is used.

For the tested Windows/Desktop workflow, run:

```powershell
powerbi-agent build examples/sales-desktop-request.json
```

This executes MCP model authoring, PBIR construction, validation, Desktop opening,
native data refresh and live DAX verification in one build. It requires the
English Desktop UI and the secure local API preview. The optional
`runtime.native_refresh` fallback invokes only the named Refresh accessibility
command in the process whose open PBIP matches the target. No keyboard shortcuts,
focus changes, mouse clicks or coordinates are used. The current bridge has no
refresh method; this isolated fallback is not used for model/report authoring.
An invoked command is recorded separately from successful runtime verification.
Loading errors or credential prompts leave the saved project available for review.
CLI exit code 2 means the project was written but explicitly requested runtime or
visual verification did not pass; exit code 1 means a command/build error. A file-only
build may succeed with runtime checks clearly marked as not run.

To verify an already loaded project without copying a local port:

```powershell
powerbi-agent verify-runtime ./output/AutonomousSales/AutonomousSales.pbip --desktop
```

Add `--native-refresh` to request that optional refresh fallback first. Discovery
matches the Analysis Services parent process to the verified Desktop PID, so
other open reports are not selected by filename similarity. The open adapter
also checks the resulting project path: CLI 0.1.2 can initially report a different
already-connected instance.

After the generated model is open, set `PBI_CONNECTION` to its local Analysis
Services connection string, such as `Data Source=localhost:<actual port>`:

```powershell
powerbi-agent verify-runtime ./output/SalesAnalytics/SalesAnalytics.pbip --connection-env PBI_CONNECTION
```

Load data using Desktop's native Refresh or the optional fallback first. The current bridge exposes report
reload, but no data-refresh method. XMLA refresh of Desktop M partitions hung in
live testing, so the adapter rejects `--refresh` on localhost connections.
`--refresh` is reserved for configured non-Desktop XMLA servers and requests
`RefreshWithXMLA` through MCP. Source credentials must be configured.
The verifier checks that connected measure definitions match the plan, validates and executes DAX, saves
results and execution metrics, compares supported totals/filter contexts with
independent source calculations, and flags blanks/unfamiliar result formats.
Time-intelligence, RLS and other advanced scenarios can still need further test
queries; a returned row is not itself proof of business correctness.

## Visual QA

Set `visual_qa: true` and configure:

```json
"qa": {
  "reviewer_command": ["C:/Tools/my-vision-reviewer.exe"],
  "max_iterations": 3,
  "threshold": 90
}
```

The vision command receives a request-file path and returns scores, issues,
`blocking_issues`, and optional title/geometry patches. See `qa.py` for the exact
contract. The builder captures every page from a matching Desktop PID, applies
only supported patches, validates and checkpoints the report, reloads serially,
and captures again. It stops on a passing score, no applicable fixes, or the
iteration limit. Unknown scores and unsupported patches are rejected. Without a
Desktop/vision connection, visual QA is explicitly unavailable; no score is invented.

## Validation and troubleshooting

`--remote-schema` enables Microsoft's online schema checks in addition to its
offline structural/visual catalog checks. Network-unreachable schema warnings
are recorded as incomplete schema validation, not successful schema validation.

`powerbi-agent discover-tools --out output/mcp-tools.json` records current MCP
tool contracts. `doctor` reports installed entrypoints and Desktop status.

- MCP failure: confirm `npm ci`, Windows runtime permissions and a compatible
  server build. `--modeling file` is the supported offline fallback.
- No Desktop bridge: open the target project, enable secure local APIs, restart
  and inspect `doctor`; `desktop.pid` disambiguates matching instances.
- External file edits: the builder refuses to overwrite changed managed files.
  Save/reconcile Desktop edits or build to a new output target.
- Interrupted publication: after confirming the build process stopped, run
  `powerbi-agent recover <project.pbip>`. It restores the recorded backup. Do not
  remove journals or reset Git to bypass failed validation.
- Deep Windows paths: choose a short output location. Staging names are compact,
  but native Power BI and Git can still encounter operating-system path limits.

Build artifacts and evidence are under the target directory's `.powerbi-agent`:
`latest.json` points to state; each run stores profiles, plans, runtime checks,
errors, staged files, checkpoint ZIP, an independent Git checkpoint when available,
and optional screenshots/reviews. Original source rows are not copied to logs;
SQLite snapshots and configured external reviewers are explicit exceptions.
