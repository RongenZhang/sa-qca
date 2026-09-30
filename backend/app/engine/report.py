"""Live validation report: invalid-output rate by arm with failure reasons."""

from __future__ import annotations

from collections import Counter
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import Run


def validation_report(session: Session, run_config_id: int) -> dict[str, dict[str, Any]]:
    runs = session.query(Run).filter_by(run_config_id=run_config_id).all()
    out: dict[str, dict[str, Any]] = {}
    for arm in sorted({r.arm for r in runs}):
        rs = [r for r in runs if r.arm == arm and r.status != "pending"]
        status = Counter(r.status for r in rs)
        reasons: Counter[str] = Counter()
        first_fail = 0
        for r in rs:
            if r.status == "invalid" and r.attempts:
                for e in r.attempts[-1].validation_errors:
                    reasons[e["code"]] += 1
            if r.attempts and r.attempts[0].validation_ok is False:
                first_fail += 1
        n = len(rs)
        out[arm] = {
            "n_runs": n,
            "status_counts": dict(status),
            "invalid_rate": status["invalid"] / n if n else None,
            "first_attempt_failure_rate": first_fail / n if n else None,
            "failure_reasons": dict(reasons),
        }
    return out
