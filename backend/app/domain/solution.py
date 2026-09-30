"""Canonical solution representation. Terms are frozensets of (condition, present) literals, so
`A*~B` and `~B*A` are equal and negation (~X) stays a distinct literal from X."""

from __future__ import annotations

Literal = tuple[str, bool]
Term = frozenset[Literal]


def parse_term(expr: str) -> Term:
    lits = set()
    for part in expr.split("*"):
        part = part.strip()
        if not part:
            raise ValueError(f"empty literal in term {expr!r}")
        lits.add((part[1:], False) if part.startswith("~") else (part, True))
    return frozenset(lits)


def format_term(t: Term) -> str:
    return "*".join(f"{'' if present else '~'}{name}" for name, present in sorted(t))


def solution_terms(models: list[list[str]], policy: str = "union") -> frozenset[Term]:
    """A solution may contain several models (M1, M2, ...). Policy 'union' takes every term appearing
    in any model; 'first' takes the first model only."""
    if not models:
        return frozenset()
    if policy == "first":
        models = models[:1]
    elif policy != "union":
        raise ValueError(f"unknown model policy {policy}")
    return frozenset(parse_term(e) for m in models for e in m)


def solution_key(terms: frozenset[Term]) -> str:
    return " + ".join(sorted(format_term(t) for t in terms)) or "(none)"
