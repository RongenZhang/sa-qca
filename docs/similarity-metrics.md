# Similarity metrics

A solution is a set of *terms*; a term is a set of signed literals (`A`, `~B`). `A*~B` and `~B*A` are the same term, and `~X` is a distinct literal from `X` (negated set, not a reversed calibration). Terms come from QCA's own solution object, not from parsing free text.

When a solution has several models (M1, M2, ...), the dashboard lets you choose: **union** (every term in any model; default) or **first model only**.

| Metric | Definition | Use |
|---|---|---|
| `jaccard_terms` (default) | \|A ∩ B\| / \|A ∪ B\| over exact terms | Strict. `A*B` vs `A*B*C` scores 0. |
| `subset_aware` | Best-match term similarity averaged both ways; two terms score `min(len)/max(len)` if one contains the other, 1 if equal, else 0 | Credits "same recipe, extra or missing ingredient" |
| `literal_jaccard` | Jaccard over the signed literals appearing anywhere | Separates "right ingredients" from "right recipe" |

Conventions: two empty solutions score 1.0 (both find nothing); one empty scores 0.0. Runs with `invalid` status have no solution and are excluded from similarity and from the robustness denominators. Adding a metric: register a function `(a, b) -> float in [0, 1]` in `backend/app/domain/similarity.py::METRICS`.

Path robustness: for each path (term) in the analyst's reference solution, the share of a source's *valid* runs whose solution contains it. Across-role label: `all roles`, `some roles`, `one role only`, or `no role`, computed over stakeholder sources with at least one valid run.
