# Stakeholder Anchors (SA-QCA)

Stakeholder-based calibration sensitivity analysis for fuzzy-set QCA.

> **Status:** a candidate protocol for discussion, not a finished standard. Under development (phase 2 of 6).

## Design rules
- Agents (or the mechanical generator, or the analyst) supply anchors and truth-table cutoffs. Nothing else is discretionary.
- The R core is pure: identical inputs give byte-identical solutions (tested).
- Values are never clamped, trimmed, rounded or repaired before R.

## Phase 1 contents
- `rservice/`: R pipeline (calibrate, truth table, necessity, complex/parsimonious/intermediate minimization) and Plumber API.
- `demo/`: synthetic demo dataset and project spec.
- `backend/`: FastAPI skeleton with pass-through to R.

## Run the R tests
```bash
cd rservice && Rscript tests/testthat.R
```
Requires R ≥ 4.5 with `QCA`, `SetMethods`, `plumber`, `jsonlite`, `testthat`.

## Phase 2: agent engine (backend)
Validator, prompt renderer, mechanical generator, provider abstraction (Anthropic + mock), runner with retry/invalid handling, cost cap, storage models, validation report. See `docs/protocol-to-code.md`.
```bash
cd backend && python3.11 -m venv .venv && .venv/bin/pip install -e ".[dev]" && .venv/bin/pytest
```
