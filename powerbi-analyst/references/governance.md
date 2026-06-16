# Phase 6 — Governance & final validation

## Right-size governance notes

Include only what fits this dataset and engagement. Do not pad with practices
that don't apply.

- **Data Study Justifications** (always): explicitly state WHY each analytical
  choice was made — and why available techniques (imputation, outlier treatment,
  flags, extra dimensions, standard measures, advanced visuals) were
  deliberately **skipped** as unnecessary. This is the heart of the deliverable.
- Naming conventions used.
- Display-folder strategy for measures.
- Hidden technical columns (keys, system fields) that should not be visible to
  report users.
- **RLS suggestion** — only if the data implies a security boundary (e.g., a
  Region or Manager column that should scope access).
- **Incremental refresh suggestion** — only if data volume and a reliable date
  column warrant it.
- Dataset certification readiness.
- Version-control / deployment notes if relevant.

## Assumptions section

Document, concisely:

- Business context inferred when it was not provided.
- Every imputation: column, method, reason.
- Every outlier decision, including "not treated — reason".
- Rows filtered and why (never silently drop data).
- Columns dropped and why.
- Any column with >50% nulls flagged for business review.

## Final validation checklist

- [ ] Dataset Study completed; every column classified before any transformation.
- [ ] Each applied transformation justified by data + business context.
- [ ] Each skipped technique briefly justified as unnecessary.
- [ ] M column names match TMDL references exactly.
- [ ] No missing column references in measures.
- [ ] Strict TMDL syntax; single-line DAX; tab indentation.
- [ ] No unnecessary bi-directional filters; "one" side keys are unique.
- [ ] Full exact source paths present in all M files.
- [ ] All M code `.md` files paste-ready with ZERO comments.
- [ ] All TMDL `.md` files contain ONLY executable TMDL syntax, ZERO comments.
- [ ] Every visual maps to a stated business question with exact field placements.

## Professional standard

Understand the data, objectives, and context first. Then apply only the
necessary transformations, only the necessary quality controls, only the
meaningful measures, and only the valuable visuals. The best analyst does less,
but every choice is deliberate and defensible. Do not over-engineer; do not
produce generic boilerplate; do not assume what the data does not support.
