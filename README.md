# Stakeholder Anchors (SA-QCA)

Stakeholder-based calibration sensitivity analysis for fuzzy-set QCA.

> **Status:** a candidate protocol for discussion, not a finished standard. Under development (phase 4 of 6).

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

## Phase 3: wizard UI (demo project, no API key needed)
```bash
cd backend && .venv/bin/uvicorn app.main:app --port 8001      # needs Rscript with QCA installed
cd frontend && npm install && npm run dev                    # http://localhost:5173
```
The five-step wizard (data, roles with approval, run design with exact-prompt preview and cost/call estimate, live run, results) runs against a scripted demo provider. Choose "Anthropic" in step 3 and enter a key to use a real model; the key stays in browser memory and is sent per request only.

## Your own data
Step 1 > "Upload my own data": CSV (comma, semicolon or tab) or Excel (first sheet), up to 10 MB. Pick the outcome and conditions, give each a construct definition and measurement instrument, declare its direction, and optionally enter your original anchors, cutoffs and directional expectations (needed for the mechanical source and the comparison with your published solution). Variable names must start with a letter and use letters, digits and underscores (a QCA requirement); rename columns in your file if needed. Rows with missing values are dropped only if you tick the listwise-deletion box, and the count is recorded. The uploaded file stays in the local database; models receive only definitions and summary statistics.

"Scripted test responses" in step 3 works on any project and needs no key, but it is a stand-in, not LLM output.
