# Study Notes: Context Engineering for Long-Running Assistants

Date: 2026-04-20
Type: study note
Topic: LLM context engineering

## Notes

- Context windows are finite attention budgets, not storage systems.
- Stable knowledge should be externalized into durable markdown notes instead of being repeatedly stuffed into prompts.
- Notes are more useful when split into source facts, reusable concepts, and current decisions.
- Retrieval should prefer concise summaries that point back to the full source.
- When a workflow repeats, encode it as a method page so future sessions do not reconstruct it from scratch.

## Takeaways

- Separate evidence from interpretation.
- Use layered notes: source -> topic/concept -> decision/method.
- Preserve conflicts when two sources disagree; do not collapse them too early.
