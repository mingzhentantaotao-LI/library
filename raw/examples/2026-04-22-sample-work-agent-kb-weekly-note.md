# Weekly Note: Personal Knowledge Base V1

Date: 2026-04-22
Type: work note
Project: Personal Knowledge Base V1

## Context

This week I set up the first version of a personal knowledge base.
The goal is to manage work notes, study notes, and clipped learning materials in one markdown repository.

## Decisions

- Keep V1 markdown-only.
- Do not build a frontend or database.
- Treat `raw/` as an evidence layer and never rewrite source files.
- All new materials should enter through `raw/inbox/` before being organized elsewhere.

## Operating Notes

- Each ingest should create a source page first.
- Important insights should be lifted into topics, concepts, methods, or decisions.
- `index.md` should only keep stable entry points.
- `log.md` should append every material ingest or structural change.

## Next Actions

- Test the workflow with 3-5 sample files.
- Define a small lint checklist for dead links and missing backreferences.
