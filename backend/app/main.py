from typing import Any

from fastapi import FastAPI

from app import rclient

app = FastAPI(title="SA-QCA backend")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/pipeline")
def pipeline(payload: dict[str, Any]) -> dict[str, Any]:
    """Phase 1: pass-through to the R core. Agent-supplied values are never altered here."""
    return rclient.run_pipeline(payload)
