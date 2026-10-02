"""Substantive rationale text for the SCRIPTED test provider. Built from each condition's own definition and
instrument, the role's vantage point and the observed data, so the demo shows what a good rationale looks like
(a real model writes its own). Deterministic; not LLM output."""

from __future__ import annotations

from app.domain.prompt import VariableSpec

# One vantage-point sentence per anchor position (out / mid / in) for the roles used in the demo.
LENS: dict[str, dict[str, str]] = {
    "Small-firm owner-manager": {
        "out": "From the owner-manager's seat this is where the firm is plainly not living it: nothing in the daily routine would show it, and I would not count it as a partial case.",
        "mid": "As an owner-manager I would hesitate here: some weeks the firm looks like it has this and some weeks it does not, and I would want to see more before calling it either.",
        "in": "To an owner-manager this is the level at which the matter stops being a worry; more of it would not change how I run the firm.",
    },
    "Vendor account manager": {
        "out": "Across the accounts I handle, this is where a firm is plainly outside what I would call a genuine instance; I would not present it as a reference customer.",
        "mid": "I tend to read the middle generously, because many accounts at this level move on to fuller engagement, so my crossover reflects direction of travel as well as the present level.",
        "in": "At this level I would be comfortable describing the firm as a clear case when speaking to other prospects.",
    },
    "Independent IT consultant": {
        "out": "As an outside adviser I discount surface signals: below this I would say the firm has not really taken the matter on, whatever it reports.",
        "mid": "I apply a demanding standard for the crossover because firms tend to overstate; a mid-scale reading usually reflects intention more than practice.",
        "in": "I accept full membership only when the evidence is behaviour I could audit, so this anchor sits deliberately high on the scale.",
    },
    "Operations lead": {
        "out": "From the operations side, this is where day-to-day work is plainly unaffected: the routines run as before and no one relies on it.",
        "mid": "In operations the middle is a mixed picture: some processes depend on it and others quietly bypass it, which is why I would not call it either way.",
        "in": "Here operations depend on it routinely; a further increase would not change who does what.",
    },
    "Finance officer": {
        "out": "Seen from finance, this is where the firm has plainly not committed resources to it, so it would not appear as a line I would defend in a budget review.",
        "mid": "For finance the middle is ambiguous because the commitment is partial and could still be reversed without much loss.",
        "in": "At this level the commitment is large enough to show up in budgets and be hard to unwind, which is how I recognise full membership.",
    },
}
TT_LENS: dict[str, str] = {
    "Small-firm owner-manager": "As an owner-manager I would rather see a pattern that holds for most comparable firms than one explained by a handful of cases.",
    "Vendor account manager": "From the accounts I see, a pattern is credible when it recurs across several firms, not when one firm is a striking example.",
    "Independent IT consultant": "As an adviser I would want a combination to hold up across several engagements before I would recommend building on it.",
    "Operations lead": "In operations I trust a pattern that shows up repeatedly, not one that depends on a single unusual firm.",
    "Finance officer": "For finance a pattern is only actionable if it recurs, so I prefer a threshold that screens out one-off cases.",
}
GENERIC = {
    "out": "Without a particular stakeholder in mind I read the measure literally: this is the part of the scale that stands for clear absence.",
    "mid": "Reading the measure literally, this is where the evidence for presence and absence is evenly balanced.",
    "in": "Reading the measure literally, from here the evidence for presence is unambiguous and further increases add nothing.",
}


def _lc(text: str) -> str:
    t = text.strip().rstrip(".")
    return t[:1].lower() + t[1:] if t else "the construct"


def _first_sentence(text: str) -> str:
    return text.strip().split(".")[0].strip()


def _lens(role: str, role_desc: str, pos: str) -> str:
    if not role or role == "generic":
        return GENERIC[pos]
    if role in LENS:
        return LENS[role][pos]
    who = _first_sentence(role_desc) or role
    return f"Reading this as {role} ({who[:1].lower() + who[1:]}), I weigh what is visible from that position and place the anchor where the evidence from there stops being ambiguous."


POS = {"full_non_membership": "out", "crossover": "mid", "full_membership": "in"}


def anchor_rationale(role: str, role_desc: str, var: VariableSpec, key: str, value: float, values: list[float]) -> str:
    d = _lc(var.construct_definition)
    inst = var.instrument.strip().rstrip(".") or "the measurement scale"
    x = f"{value:g}"
    if key == "full_non_membership":
        a = (f"At {x} a case shows essentially none of what the construct names ({d}); read against the instrument ({inst}), "
             f"this is the part of the range that stands for clear absence and not merely a weak degree.")
        b = ("Placing it nearer the scale midpoint would start to count cases with some, if weak, presence as fully outside the set, "
             "while placing it further out would leave almost no case at the 0.05 level.")
    elif key == "crossover":
        a = (f"A value of {x} is where {d} is neither clearly present nor clearly absent: a careful reader of the instrument ({inst}) "
             f"could argue either way, which is what the 0.5 membership point is meant to capture.")
        b = ("Moving it toward either end of the scale would turn cases that already clearly show, or clearly lack, the construct "
             "into ambiguous ones, so small shifts matter more here than at the other two anchors.")
    else:
        a = (f"From {x} onward {d} is unambiguously present on the instrument ({inst}); additional increases would not change "
             f"a case's standing in the set.")
        b = ("Lowering it would admit cases whose presence is still developing as fully in the set, while raising it would set a bar "
             "that almost no case in this study could reach.")
    lens = _lens(role, role_desc, POS[key])
    s = sorted(values)
    n = len(s)
    below = sum(1 for v in s if v < value)
    above = sum(1 for v in s if v > value)
    check = (f"As an empirical check only, {x} lies inside the observed range with {below} of the {n} cases on one side and {above} on the other, "
             f"so the anchor is attainable and does not sit in an empty part of the data.")
    return " ".join([a, b, lens, check])


def consistency_rationale(role: str, c: float, n: int, k: int) -> str:
    base = (f"A cutoff of {c:g} tolerates about {round((1 - c) * 100)} in 100 cases that share a combination of conditions without showing the outcome. "
            f"The measures in this study are survey- or index-based and carry noise, so demanding perfect consistency would reject combinations "
            f"over a few noisy cases, while a much lower cutoff would call a combination sufficient on a bare majority of its cases.")
    return base + " " + TT_LENS.get(role, "Without a particular stakeholder in mind, I want sufficiency claims to rest on a pattern that holds for most cases.")


def frequency_rationale(role: str, f: int, n: int, k: int) -> str:
    rows = 2**k
    base = f"With {n} cases and {k} conditions there are {rows} possible combinations, so an average combination holds only about {n / rows:.1f} cases. "
    if f == 1:
        mid = ("A threshold of 1 keeps every combination that has at least one case. In a study this small, dropping thin combinations would discard "
               "exactly the routes a configurational design is meant to detect; the cost is that a single case can carry a route, so I would read such routes cautiously. ")
    else:
        mid = (f"A threshold of {f} means a combination counts as evidence only when at least {f} cases sit in it; that keeps sparse combinations from "
               f"driving the solution without discarding the thin but real routes that studies with few cases depend on. ")
    return base + mid + TT_LENS.get(role, "Without a particular stakeholder in mind, I treat very sparse combinations cautiously.")


def pri_rationale(p: float) -> str:
    return (f"A PRI cut of {p:g} excludes combinations that are almost as consistent with the absence of the outcome as with its presence, "
            f"which a consistency cutoff alone would let through; I set it low enough not to discard combinations that are genuinely informative.")


def breakpoint_rationale(role: str, role_desc: str, var: VariableSpec, key: str, value: float, values: list[float]) -> str:
    """Rationale for a four-value (breakpoint) calibration. Scripted text built from the variable's own definition."""
    d = _lc(var.construct_definition)
    inst = var.instrument.strip().rstrip(".") or "the measurement scale"
    neg = var.direction == "negative"
    side = "at or above" if neg else "at or below"
    beyond = "below" if neg else "above"
    x = f"{value:g}"
    if key == "break_0":
        a = (f"A case {side} {x} scores 0 and is treated as fully outside the set: it shows none of what the construct names ({d}); "
             f"read against the instrument ({inst}), this is the part of the scale that marks complete absence, not merely little.")
        b = ("Moving this boundary further toward more membership would push cases with some real presence into the fully-out category, "
             "while moving it the other way would leave nobody scored 0 and blur the distinction between absent and minimal.")
    elif key == "break_33":
        a = (f"The boundary at {x} separates cases that only minimally or partly meet the idea of the set ({d}) from those that meet it "
             f"substantially: {side} {x} a case scores 0.33, {beyond} it a case scores at least 0.67. On the instrument ({inst}) this is the point at which the evidence stops being thin.")
        b = ("Placing it much closer to the empty end would credit cases with scant evidence as substantial; placing it much closer to the "
             "full end would demote cases that already meet the idea in a substantive way.")
    else:
        a = (f"The boundary at {x} separates cases that substantially meet the idea ({d}) from those that fully meet it: {side} {x} a case scores 0.67, "
             f"{beyond} it a case scores 1. On the instrument ({inst}) this marks the level at which nothing more could reasonably be asked of a case.")
        b = ("Lowering it would give full membership to cases that are strong but still developing, while raising it would reserve full "
             "membership for so few cases that the set stops distinguishing among the strong ones.")
    lens = _lens(role, role_desc, {"break_0": "out", "break_33": "mid", "break_67": "in"}[key])
    s = sorted(values)
    n = len(s)
    on_low = sum(1 for v in s if (v >= value if neg else v <= value))
    check = (f"As an empirical check only, {on_low} of the {n} cases fall {side} {x} and {n - on_low} {beyond} it, so the boundary actually "
             f"divides the cases it is meant to divide.")
    return " ".join([a, b, lens, check])
