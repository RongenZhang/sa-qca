# Calibration kinds

Each variable in a project is calibrated in one of three ways. Choose per variable in Step 1 (or `calibration` in a project file).

| Kind | What the values are | Who sets what | In R |
|---|---|---|---|
| **direct** (default) | a raw measure | the agent proposes three anchors: full non-membership, crossover, full membership | logistic direct method |
| **breakpoints** | a raw measure scored on a four-value scale (0, 0.33, 0.67, 1) | the agent proposes three breakpoints: `break_0` (0 \| 0.33), `break_33` (0.33 \| 0.67), `break_67` (0.67 \| 1) | indirect calibration by bands |
| **precalibrated** (pass-through) | values that already are set memberships in [0, 1], for example coder-assigned scores | nothing: the values are fixed for every source | used exactly as given |

## Pass-through
A pre-calibrated condition is taken exactly as it is. Agents are told the set is fixed and are not asked to calibrate it (it is not in the decision schema at all), but they see its definition, the coding rule and the distribution of its scores so that they understand what it means. Memberships must lie in [0, 1]. Only conditions can be pre-calibrated: the outcome must be calibrated by the agents, either with anchors or breakpoints.

## Breakpoints
For a variable whose membership runs with the raw scale, a value at or below `break_0` scores 0, at or below `break_33` scores 0.33, at or below `break_67` scores 0.67, and above that scores 1. For a variable whose membership runs opposite to the raw scale the order is reversed. **A value exactly on a boundary takes the lower of the two scores** in both orientations (so with breakpoints 0 / 15 / 90, 15 proposals score 0.33 and 90 score 0.67).

Validation (structural only): the breakpoints must be strictly ordered for the declared direction; `break_33` and `break_67` must lie in the observed range (plus any tolerance); `break_0` only decides whether any case scores 0, so it may lie beyond the observed range on the empty side, by at most one range width; each needs a non-empty rationale.

## Mechanical source
Anchors are shifted by a share of the observed range, as before. Breakpoints are shifted by a share of the distance between the original first and last breakpoint instead, because a range-based offset would swamp breakpoints on skewed counts. When every condition is pre-calibrated, only the outcome can be perturbed, so it is.

## Reproducing a published analysis
`rservice/tests/testthat/fixtures/zhang_ramesh_2024_isj.csv` holds the published data of Zhang & Ramesh (2024, *Information Systems Journal*; CC BY 4.0, see the README beside it). With the five conditions pre-calibrated, the outcome calibrated from raw proposal counts with breakpoints 0 / 15 / 90, raw consistency 0.80, PRI 0.75 and frequency 1, the tool reproduces the paper's outcome scores for all 14 platforms and its solution (three configurations, overall consistency 1.000, coverage 0.815). This is a known-answer test in the R suite.

## Project files and the loader
A project can be kept as a CSV plus a JSON file with the same fields as the Step 1 form, and loaded with `python -m app.cli load-project --csv data.csv --config project.json`, which prints a `/?project=<id>` link.
