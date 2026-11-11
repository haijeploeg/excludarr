# Preview outcomes

Implement the approved preview improvements with English CLI text.

- Describe the concrete action, including monitoring, import exclusions, searches and configured cleanup.
- Read the grace queue to classify simulated matches as execute, queue, wait or skipped after an earlier removal. The preview command simulates actions for preview-only rules as well, with an explicit banner naming rules requiring preview: false before execution.
- Estimate file bytes separately for the next run and after grace. Deduplicate movies and Sonarr file IDs across rules and levels.
- Keep actual execution behavior intact. Predictions assume successful preceding actions and future queue re-evaluation.
- Verify queue dates and read-only behavior, overlapping rules/files, action descriptions and CLI output using existing tests plus focused regressions.
