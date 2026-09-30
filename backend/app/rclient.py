"""Thin client for the stateless R service. Sends values to R exactly as given."""

import os
from typing import Any

import httpx

RSERVICE_URL = os.environ.get("RSERVICE_URL", "http://localhost:8000")


def run_pipeline(payload: dict[str, Any], timeout: float = 120.0) -> dict[str, Any]:
    r = httpx.post(f"{RSERVICE_URL}/run_pipeline", json=payload, timeout=timeout)
    r.raise_for_status()
    result: dict[str, Any] = r.json()
    return result


def run_pipeline_local(payload: dict[str, Any], rservice_dir: str) -> dict[str, Any]:
    """No-HTTP variant: call the R core via Rscript (used by tests and the replication script)."""
    import json
    import subprocess

    code = 'source("R/pipeline.R"); cat(run_pipeline_json(readLines("stdin", warn=FALSE)))'
    proc = subprocess.run(
        ["Rscript", "-e", code], input=json.dumps(payload), capture_output=True, text=True,
        cwd=rservice_dir, check=True,
    )
    result: dict[str, Any] = json.loads(proc.stdout)
    return result
