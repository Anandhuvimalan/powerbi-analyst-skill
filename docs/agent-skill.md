# Install and use the agent skill

Download `powerbi-analyst.zip` from the repository's GitHub release. Extract the
top-level `powerbi-analyst` folder into a skill-capable host's skills directory.
The folder includes instructions, the original reference guides, host metadata,
a setup/launch helper and executor source under `runtime/`.

The host AI reads the skill and makes the project-specific analytical decisions.
The executable applies those decisions. A standalone unattended deployment can
instead supply `reasoning.command` and `qa.reviewer_command` for its chosen AI
providers; neither service nor credentials are included by default.

## Setup

Requires Python 3.11+ and Node 20+ with npm. From any working directory:

```powershell
python <skill-directory>/scripts/agent.py setup
python <skill-directory>/scripts/agent.py run doctor
```

Setup creates `.venv` inside the executor directory, installs its Python package
and runs `npm ci` for pinned Microsoft tools. It does not change another skill or
your global agent configuration. `setup --file-only` skips Node/Microsoft tools
and permits file execution with those validation capabilities unavailable.

The release ZIP is portable; do not flatten its folders. If only the small skill
folder was installed from the GitHub source tree, setup uses Git to retrieve the
matching `v0.2.0` repository into `.runtime`. Run setup again after upgrading the
skill. Close applications using its private environment before replacing files.

Desktop installation and source credentials are managed through Power BI. See
[Desktop setup](setup.md#desktop-refresh-and-dax-verification). Schema validation
and offline file construction can run without a live Desktop. Runtime/visual
checks stay explicitly unverified until executed.

## What the person provides

Give the agent accessible data, the business question/audience and a target PBIP
path. A blank project is supported. For example:

> Study orders.xlsx for our regional managers. Help them identify weak margins
> and prioritize product actions. Create RegionalDecisions.pbip, with purposeful
> pages, useful filters and verified calculations. Use our navy brand color.

The agent should inspect the data, clarify only material unknown business rules,
and execute. Users should not need to hand-author JSON or paste DAX. The internal
artifacts below are for the agent and for debugging.

## Internal execution contract

Use `run plan` to profile data and obtain executable connector/model scaffolding.
Read the profiles and original reference guides, then author the analysis brief,
model plan and report plan. Obtain the complete schemas with `agent.py schemas`.

An agent-authored request looks like:

```json
{
  "project": "./RegionalDecisions.pbip",
  "sources": ["./orders.xlsx"],
  "business_goal": "Prioritize product actions and improve regional margins",
  "agent_mode": true,
  "analysis_brief": "./work/analysis-brief.json",
  "model_plan": "./work/model-plan.json",
  "report_plan": "./work/report-plan.json",
  "modeling": {"mode": "mcp"}
}
```

All request paths resolve relative to that JSON. Run with:

```powershell
python <skill-directory>/scripts/agent.py run build ./request.json
```

The three work files must have been authored by the agent; the example is not a
ready-made dashboard. Agent mode fails before publication if these are absent,
if evidence references nonexistent source fields, or if page decisions are
missing. It cannot detect a dishonest explanation or guarantee business meaning.

With `reasoning.command`, return `analysis_brief`, `model_plan` and `report_plan`.
The provider receives the original skill and schemas. It must use source evidence
and the user's objective; the supplied baseline is technical scaffolding only.

## Quality and verification

Select the page architecture, chart families, layout, density and palette for the
actual decisions. Reusable visual primitives and consistent spacing are useful;
renaming a fixed sales report is not sufficient. Data with no useful dates should
not acquire a trend page just because the example has one.

Execute through TMDL/MCP/PBIR. Compare DAX outputs with source totals and relevant
filter contexts. Review screenshots if the host can see them. An optional bounded
external vision loop can refine titles and geometry, with validations/checkpoints.
Complex redesigns require a new authored plan.

The supported Desktop refresh fallback invokes the named English Refresh command
through accessibility, with a verified project/PID. It uses no mouse coordinates
and never creates measures or visuals through the UI. This is optional because
the current Microsoft bridge exposes no data-refresh operation.

An actual saved project, meaningful analysis and honest evidence are the result.
No skill can promise uniquely excellent dashboards for every source or AI model;
missing business definitions and unsupported connectors remain explicit limits.
