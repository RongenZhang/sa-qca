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
