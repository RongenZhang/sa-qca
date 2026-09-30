# Stakeholder Anchors (SA-QCA)

Stakeholder-based calibration sensitivity analysis for fuzzy-set Qualitative Comparative Analysis (fsQCA).

> **Status: a candidate protocol for discussion, not a finished standard.** The software is research code under active development. Please read [Limitations](#limitations) before relying on it.

## What it does

In fsQCA the analyst sets the calibration anchors, and results can depend on those choices. Usual robustness checks nudge the analyst's own numbers. SA-QCA asks a different question: across the range of calibration decisions based on stakeholders' different interpretations of conditions and outcomes, which findings survive?

1. You describe the phenomenon and define each condition and the outcome, then approve a set of stakeholder roles drawn from your own cases.
2. Each role (and a role-free "generic" LLM calibration) proposes anchors and truth-table cutoffs, with a written rationale.
3. The same QCA (R) code analyses every proposal, so judgment and calculation stay separate.
4. Structurally invalid answers are rejected, never repaired, and the invalid rate is reported as a finding.
5. You compare solutions across roles, the generic calibration, a mechanical perturbation of your own anchors (Skaaning-style), and your original solution.

Design rules: only an agent, the mechanical generator or the analyst ever supplies anchors; model output is never edited before R; the R core is pure (identical inputs give identical solutions, tested); nothing runs before roles are approved; every number in the UI traces to a stored run.

## Quickstart (no API key needed)

Requirements: R 4.5+ with the packages `QCA`, `SetMethods`, `jsonlite`, `plumber`, `testthat`; Python 3.11+; Node 22+.

```bash
# terminal 1: backend
cd backend && python3.11 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/uvicorn app.main:app --port 8001

# terminal 2: frontend
cd frontend && npm install && npm run dev      # open http://localhost:5173
```

Start with the bundled **demo project** (synthetic data). In step 3 choose "Scripted test responses": a stand-in that needs no key and is **not** LLM output. To use a real model, choose Anthropic and enter your key (and a workspace ID if your key is not scoped to one). The key stays in browser memory and is sent per request only.

## Your own data

Step 1 › "Upload my own data": CSV (comma, semicolon or tab) or Excel (first sheet), up to 10 MB. Choose the outcome and conditions; give each a construct definition and measurement instrument; declare its direction; optionally enter your original anchors, cutoffs and directional expectations (needed for the mechanical source and the comparison with your published solution). Variable names must start with a letter and use letters, digits and underscores. Rows with missing values are dropped only if you tick the listwise-deletion box. The file stays in the local database; models receive only definitions and summary statistics, never rows.

## Exports and verification

The results screen offers a **replication bundle** (ZIP: analysis data, project definitions, approved roles, every rendered prompt, every raw model response, the decisions handed to R, the R code, recorded results, environment versions and a SHA-256 manifest; never API keys), an **HTML report** with a draft AI-use statement filled from the run's actual models and parameters (print to PDF from the browser), and **Verify bundle**, which re-runs the QCA computation with no LLM calls and checks every stored result is reproduced exactly:

```bash
cd backend && .venv/bin/python -m app.exports.verify path/to/sa-qca-run2-replication.zip
```

The QCA computation is reproduced exactly. Model answers are not regenerated: the stored raw responses are the record.

## Limitations

- The Anthropic adapter is covered by mocked tests and has had only a first real-API attempt; expect rough edges. OpenAI and OpenAI-compatible providers are not implemented yet.
- "Suggest roles" returns scripted examples, not LLM suggestions.
- The mechanical source follows Skaaning (2011) as read from the paper (lower/original/higher anchor sets crossed across conditions, outcome unchanged, frequency and consistency cutoffs varied); the offset size is this tool's choice, and the grid grows as 3^k with k conditions.
- Only the `default_v1` prompt template is available; there is no template editor yet.
- A `docker-compose.yml` exists but has never been run. The app has no authentication and is meant to run locally for one researcher; do not expose it to the internet.
- PDF export is via the browser's print dialog. Accessibility has had only basic attention (keyboard use, a colour-blind-safe palette).
- Similarity scores compare solution terms; see [docs/similarity-metrics.md](docs/similarity-metrics.md) for definitions and caveats.

## Documentation

[docs/protocol-to-code.md](docs/protocol-to-code.md) maps each protocol step to the code; [docs/similarity-metrics.md](docs/similarity-metrics.md) documents the metrics.

## Citing

See [CITATION.cff](CITATION.cff); the paper reference will be completed on publication. Released under the MIT License.
