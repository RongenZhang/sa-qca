# How the protocol maps to the code

| Protocol step | Where |
|---|---|
| 1. Roles derived from the phenomenon, approved before running | `RunConfig.roles`; approval UI arrives in phase 3 |
| 2. Judgment separate from computation | `rservice/R/pipeline.R` is pure; `backend/app/engine/rinput.py` copies values through untouched |
| 3. Agents get understanding, not just a distribution | `backend/app/domain/templates/default_v1.j2`; `prompt_warnings()` flags empty definitions/instruments |
| 4. Generic and mechanical baselines | generic: `render_prompt(role=None)`; mechanical: `app/domain/mechanical.py` |
| 5. Structural validation only | `app/domain/validator.py`: rejects, never repairs |

Run rules (`app/engine/runner.py`): one validation retry with errors appended; second failure is an `invalid` judgment that is kept and never sent to R; rate-limit retries are logged in `call_log`, separately from the validation retry; spend cap halts the batch, and batches resume without repeating finished runs.

Statuses: `valid`, `invalid` (agent failed validation twice; counted in the invalid rate), `valid_no_solution`, `r_error`, `provider_error` (not counted as invalid), `pending`.

Provisional choices: mechanical-arm defaults are unverified against Skaaning (2011); cost estimates use an empty price table unless the user supplies one; validation tolerance is a fraction of the observed range.
