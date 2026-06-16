# powerbi-analyst — a Claude / Agent Skill

A reusable [Agent Skill](https://docs.claude.com/en/docs/claude-code/skills)
that makes an AI study source data **like a senior data analyst** and produce
production-ready Power BI artifacts — instead of blindly running a fixed
transformation template.

Give it a **CSV, Excel, JSON, a folder of files, or another tabular source**,
and it will study the data first, decide what each column actually needs, and
output:

- **Power Query (M)** — one paste-ready `.md` per table, with the exact source path
- **`relationships.tmdl.md`** — only the relationships real keys support
- **`measures.tmdl.md`** — only measures that answer a real business question
- **Visualization Blueprint** — step-by-step, every visual tied to a question
- **Data Quality & Governance Notes** + **Assumptions / Justifications**

## Philosophy

It behaves like a **Senior Enterprise Data Analyst and BI Consultant**, not a
rule-based engine. The reference files are a *toolkit, not a checklist*:

- Studies and classifies every column before any transformation.
- **Never auto-imputes** missing values — decides per column and justifies it.
- Treats outliers only when warranted; flags rather than deletes by default.
- Never forces a star schema or invents dimensions.
- Creates only meaningful measures and only valuable visuals.
- Explains why each technique was applied **and why others were skipped**.
- Avoids over-engineering and generic enterprise boilerplate.

All M and TMDL output is 100% copy-paste ready into Power BI Desktop (Advanced
Editor / TMDL files) with zero comments.

## Structure

```
powerbi-analyst/
├── SKILL.md                         # philosophy + workflow + hard output rules
└── references/
    ├── data-study.md                # column profiling & classification (phase 1)
    ├── power-query.md               # M connectors (CSV/Excel/JSON/folder), cleaning, imputation, outliers
    ├── tmdl-relationships.md        # relationship modeling
    ├── tmdl-measures.md             # DAX measures in TMDL
    ├── visualization-blueprint.md   # business-question-driven visuals
    └── governance.md                # right-sized governance + validation checklist
```

## Install

**Claude Code** — copy the skill into your skills directory:

```bash
# user-level (all projects)
cp -r powerbi-analyst ~/.claude/skills/

# or project-level
cp -r powerbi-analyst .claude/skills/
```

Then invoke it by asking, e.g. *"build a Power BI model from this CSV"*, or call
`/powerbi-analyst` directly.

## Usage

Provide the source file's **full local path** (required — it goes verbatim into
the M `Source` step). Optionally add business rules, reporting objectives, and
the target audience. Anything not provided is inferred from the data and noted
in the Assumptions section.

## License

MIT — see [LICENSE](LICENSE).
