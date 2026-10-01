# How the protocol maps to the code

| Protocol step | Where |
|---|---|
| 1. Roles derived from the phenomenon, approved before running | `RunConfig.roles`; approval UI arrives in phase 3 |
| 2. Judgment separate from computation | `rservice/R/pipeline.R` is pure; `backend/app/engine/rinput.py` copies values through untouched |
| 3. Agents get understanding, not just a distribution | `backend/app/domain/templates/default_v2.j2`; `prompt_warnings()` flags empty definitions/instruments |
| 4. Generic and mechanical baselines | generic: `render_prompt(role=None)`; mechanical: `app/domain/mechanical.py` |
| 5. Structural validation only | `app/domain/validator.py`: rejects, never repairs |

Run rules (`app/engine/runner.py`): one validation retry with errors appended; second failure is an `invalid` judgment that is kept and never sent to R; rate-limit retries are logged in `call_log`, separately from the validation retry; spend cap halts the batch, and batches resume without repeating finished runs.

Statuses: `valid`, `invalid` (agent failed validation twice; counted in the invalid rate), `valid_no_solution`, `r_error`, `provider_error` (not counted as invalid), `pending`.

Mechanical source: `generate_skaaning_configs` follows Skaaning (2011) as read from the paper (full factorial of lower/original/higher anchor sets per condition, all three anchors moved together, outcome not perturbed, frequency 1->2, consistency +/-0.10). Its offset size (`shift_fraction`, default 5% of observed range) is our choice; Skaaning hand-picked raw offsets. `generate_mechanical_configs` (percentile shifts) is kept as an alternative variant, not the default.

Provisional choices: cost estimates use an empty price table unless the user supplies one; validation tolerance is a fraction of the observed range.

## Exports (phase 5)
`backend/app/exports/bundle.py` (ZIP + manifest), `replicate.R` (standalone replication using the same `pipeline.R`), `verify.py` (manifest check, then replication), `report.py` (HTML report and AI-use statement). Each run freezes a project snapshot and role approval (`RunConfig.project_snapshot`, `.role_approval`), so editing a project never changes what earlier runs used. The replication parses its inputs with the same jsonlite calls as at run time and compares results with `identical()`, excluding only the recorded package versions.
