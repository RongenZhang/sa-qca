"""Pluggable solution-similarity metrics. Each takes two term sets and returns a score in [0, 1].
Both empty (no solution on either side) scores 1.0; exactly one empty scores 0.0. See docs/similarity-metrics.md."""

from __future__ import annotations

from collections.abc import Callable

from app.domain.solution import Term

Metric = Callable[[frozenset[Term], frozenset[Term]], float]


def jaccard_terms(a: frozenset[Term], b: frozenset[Term]) -> float:
    """Jaccard over exact terms. Strict: A*B vs A*B*C scores 0."""
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b)


def _term_sim(x: Term, y: Term) -> float:
    if x == y:
        return 1.0
    if x < y or y < x:
        return min(len(x), len(y)) / max(len(x), len(y))
    return 0.0


def subset_aware(a: frozenset[Term], b: frozenset[Term]) -> float:
    """Credits partial matches when one term contains the other (more/fewer literals), averaging the
    best match of each term in both directions."""
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    ab = sum(max(_term_sim(x, y) for y in b) for x in a) / len(a)
    ba = sum(max(_term_sim(y, x) for x in a) for y in b) / len(b)
    return (ab + ba) / 2


def literal_jaccard(a: frozenset[Term], b: frozenset[Term]) -> float:
    """Jaccard over the signed literals appearing anywhere in the solution ('right ingredients')."""
    la = {lit for t in a for lit in t}
    lb = {lit for t in b for lit in t}
    if not la and not lb:
        return 1.0
    return len(la & lb) / len(la | lb)


METRICS: dict[str, tuple[Metric, str]] = {
    "jaccard_terms": (jaccard_terms, "Jaccard over exact solution terms (default)."),
    "subset_aware": (subset_aware, "Partial credit when one term is a subset of the other."),
    "literal_jaccard": (literal_jaccard, "Jaccard over signed literals present anywhere in the solution."),
}
