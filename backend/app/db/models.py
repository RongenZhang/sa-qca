"""Storage for run provenance. Every displayed number should trace to attempt/judgment/r_result rows."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class RunConfig(Base):
    __tablename__ = "run_config"
    id: Mapped[int] = mapped_column(primary_key=True)
    template_version: Mapped[str] = mapped_column(String)
    template_sha256: Mapped[str] = mapped_column(String)
    provider: Mapped[str] = mapped_column(String)
    model: Mapped[str] = mapped_column(String)
    sampling: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    reps: Mapped[int] = mapped_column(Integer)
    tolerance: Mapped[float] = mapped_column(Float, default=0.0)
    spend_cap: Mapped[float | None] = mapped_column(Float, nullable=True)
    roles: Mapped[list[Any]] = mapped_column(JSON, default=list)
    arms: Mapped[list[Any]] = mapped_column(JSON, default=list)
    mechanical_params: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    runs: Mapped[list[Run]] = relationship(back_populates="config")


class Run(Base):
    __tablename__ = "run"
    id: Mapped[int] = mapped_column(primary_key=True)
    run_config_id: Mapped[int] = mapped_column(ForeignKey("run_config.id"))
    arm: Mapped[str] = mapped_column(String)  # "role:<name>" | "generic" | "mechanical"
    rep_index: Mapped[int] = mapped_column(Integer)
    # pending | valid | invalid | r_error | valid_no_solution | provider_error | cancelled
    status: Mapped[str] = mapped_column(String, default="pending")
    mechanical_id: Mapped[str | None] = mapped_column(String, nullable=True)
    config: Mapped[RunConfig] = relationship(back_populates="runs")
    attempts: Mapped[list[RunAttempt]] = relationship(back_populates="run", order_by="RunAttempt.id")
    judgment: Mapped[Judgment | None] = relationship(back_populates="run", uselist=False)


class RunAttempt(Base):
    __tablename__ = "run_attempt"
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("run.id"))
    attempt_kind: Mapped[str] = mapped_column(String)  # first | validation_retry
    rendered_prompt: Mapped[str] = mapped_column(Text)
    prompt_sha256: Mapped[str] = mapped_column(String)
    provider: Mapped[str] = mapped_column(String)
    model_id: Mapped[str | None] = mapped_column(String, nullable=True)
    sampling: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    raw_response: Mapped[str | None] = mapped_column(Text, nullable=True)
    tokens_in: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tokens_out: Mapped[int | None] = mapped_column(Integer, nullable=True)
    est_cost: Mapped[float | None] = mapped_column(Float, nullable=True)
    rate_limit_retries: Mapped[int] = mapped_column(Integer, default=0)
    validation_ok: Mapped[bool | None] = mapped_column(nullable=True)
    validation_errors: Mapped[list[Any]] = mapped_column(JSON, default=list)
    run: Mapped[Run] = relationship(back_populates="attempts")


class CallLog(Base):
    """Rate-limit retries are logged here, separately from protocol validation retries."""

    __tablename__ = "call_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("run.id"))
    attempt_id: Mapped[int | None] = mapped_column(ForeignKey("run_attempt.id"), nullable=True)
    kind: Mapped[str] = mapped_column(String)  # rate_limit_retry | provider_error
    detail: Mapped[str] = mapped_column(Text, default="")
    at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class Judgment(Base):
    __tablename__ = "judgment"
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("run.id"), unique=True)
    source: Mapped[str] = mapped_column(String)  # agent | mechanical | analyst
    attempt_id: Mapped[int | None] = mapped_column(ForeignKey("run_attempt.id"), nullable=True)
    decision: Mapped[dict[str, Any]] = mapped_column(JSON)
    run: Mapped[Run] = relationship(back_populates="judgment")
    r_result: Mapped[RResult | None] = relationship(back_populates="judgment", uselist=False)


class RResult(Base):
    __tablename__ = "r_result"
    id: Mapped[int] = mapped_column(primary_key=True)
    judgment_id: Mapped[int] = mapped_column(ForeignKey("judgment.id"), unique=True)
    r_input: Mapped[dict[str, Any]] = mapped_column(JSON)
    r_output: Mapped[dict[str, Any]] = mapped_column(JSON)
    judgment: Mapped[Judgment] = relationship(back_populates="r_result")


class RoleApproval(Base):
    """Protocol step 1: the role set is locked by an explicit approval."""

    __tablename__ = "role_approval"
    id: Mapped[int] = mapped_column(primary_key=True)
    roles: Mapped[list[Any]] = mapped_column(JSON)
    roles_hash: Mapped[str] = mapped_column(String, unique=True)
    approved_by: Mapped[str] = mapped_column(String)
    approved_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
