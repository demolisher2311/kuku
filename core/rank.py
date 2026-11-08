"""Turn judge scores into one ranked list. Simple, transparent weights (kept as code, not AI)."""
from __future__ import annotations

from .promo import Promo, overlap_seconds

WEIGHTS = {"hook": 0.30, "cliffhanger": 0.30, "standalone": 0.25, "intensity": 0.10, "clean_cut": 0.05}
SPOILER_PENALTY = {"none": 0.0, "minor": 0.3, "major": 1.0}
# Assumption: a promo sends a new viewer to Episode 1. Clips from early episodes show the
# story they will actually start watching and spoil nothing, so they get a small boost.
EARLY_BONUS = [(5, 0.4), (15, 0.2)]
# Review round 1: AI clips of 45s+ were rated Good 5 times in 6. Round 2 did NOT confirm this
# (45s+ clips Good 3 times in 9), so this bonus is weakly supported; kept small.
LONG_BONUS = (45.0, 0.4)  # clips at least this long get this bonus
DUP_OVERLAP = 0.35      # >35% of the shorter clip is shared -> treat as a near-duplicate


APPROVED_BONUS = 0.5     # strict judge: total >= 22 and hook >= 7


def score(p: Promo) -> float:
    present = {k: w for k, w in WEIGHTS.items() if k in p.scores} or WEIGHTS
    s = sum(w * p.scores.get(k, 5.0) for k, w in present.items()) / sum(present.values())
    if p.approved:
        s += APPROVED_BONUS
    s += next((b for ep, b in EARLY_BONUS if p.episode <= ep), 0.0)
    s -= SPOILER_PENALTY.get(p.spoiler_level, 0.3)
    s += 0.1 * (p.confidence - 3)
    if p.total >= LONG_BONUS[0]:
        s += LONG_BONUS[1]
    return round(s, 2)


def _reason(p: Promo) -> str:
    sc = p.scores
    parts = []
    strengths = [k for k in ("hook", "cliffhanger", "standalone", "intensity") if sc.get(k, 0) >= 8]
    weak = [k for k in ("hook", "cliffhanger", "standalone") if sc.get(k, 10) <= 5]
    if strengths:
        parts.append("strong " + ", ".join(f"{k} {sc[k]:.0f}/10" for k in strengths))
    if weak:
        parts.append("weak " + ", ".join(f"{k} {sc[k]:.0f}/10" for k in weak))
    if p.approved:
        parts.append("approved by the strict judge")
    elif p.approved is False:
        parts.append("not approved by the strict judge (weak hook or total under 22/30)")
    if p.total >= LONG_BONUS[0]:
        parts.append(f"{p.total:.0f}s: long enough to build (reviewers preferred 45s+)")
    if p.episode <= 5:
        parts.append(f"from ep {p.episode}: zero spoilers, viewer lands right in this story")
    if p.spoiler_level == "major":
        parts.append("penalised: gives away a major twist")
    if len(p.segments) > 1:
        parts.append(f"{len(p.segments)}-part cut")
    return "; ".join(parts) or "average on all criteria"


def rank(promos: list[Promo]) -> list[Promo]:
    """Rank valid promos; near-duplicates of a better promo are moved to the bottom."""
    valid = [p for p in promos if p.valid]
    for p in valid:
        p.final_score = score(p)
        p.rank_reason = _reason(p)
    valid.sort(key=lambda p: p.final_score, reverse=True)
    return dedupe_and_number(valid)


def dedupe_and_number(valid: list[Promo]) -> list[Promo]:
    """Walk an ordered list; a near-duplicate of a clip already kept goes to the bottom."""
    kept: list[Promo] = []
    dups: list[Promo] = []
    for p in valid:
        twin = next((q for q in kept
                     if overlap_seconds(p, q) > DUP_OVERLAP * min(p.total, q.total)), None)
        if twin:
            p.duplicate_of = twin.id
            p.rank_reason = f"near-duplicate of {twin.id}; " + p.rank_reason
            dups.append(p)
        else:
            kept.append(p)
    ordered = kept + dups
    for i, p in enumerate(ordered, 1):
        p.rank = i
    return ordered
