"""Deployment mode and limits. Read at call time so tests (and operators) can change the environment."""

from __future__ import annotations

import os


def demo_only() -> bool:
    """Public demo: scripted responses only, no uploads, no API keys, strict limits."""
    return os.environ.get("SA_QCA_MODE", "full") == "demo"


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


def max_reps() -> int:
    return _int("SA_QCA_MAX_REPS", 5) if demo_only() else 1000


def max_roles() -> int:
    return _int("SA_QCA_MAX_ROLES", 6) if demo_only() else 100


def max_concurrent_runs() -> int:
    return _int("SA_QCA_MAX_CONCURRENT", 2) if demo_only() else 1000


def retention_hours() -> int:
    return _int("SA_QCA_RETENTION_HOURS", 24)
