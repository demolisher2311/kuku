"""Offline baseline: keyword rules, no AI.

Two jobs: (1) the tool still runs with no API key, and (2) it is a "dumb" baseline
the LLM version has to beat in the quality check.
"""
from __future__ import annotations

import re

from .parser import Episode, Line
from .promo import LineIndex, Promo, build_promo, MIN_LEN, MAX_LEN, HOOK_WINDOW

HOOK_WORDS = re.compile(
    r"\b(slap\w*|strik\w*|struck|punch\w*|grab\w*|seiz\w*|shov\w*|blood\w*|fire|flames?|explo\w*|scream\w*|"
    r"kneel\w*|knee|chain\w*|sword|dagger|blade|kiss\w*|arrest\w*|guards?|poison\w*|dead|death|die|hang\w*|"
    r"execut\w*|witch\w*|burn\w*|crop|whip\w*|collaps\w*|gasp\w*|betray\w*|marry|married|marriage|propos\w*|"
    r"traitor|thief|theft|liar|murder\w*|kill\w*|duke|duchess|wife|husband|sister|father|mother)\b", re.I)
TONE_WORDS = re.compile(
    r"(furious|shock\w*|scream\w*|outrag\w*|cruel|gloat\w*|mock\w*|desperat\w*|horrif\w*|menac\w*|threat\w*|"
    r"venom\w*|vicious|sob\w*|terrif\w*|enrag\w*|cold|defiant|commanding|sneer\w*|spite\w*|fierce|murderous)", re.I)
CLIFF_SFX = re.compile(r"(cliffhanger|swell|ominous|sting|silence|cut to black|freeze)", re.I)


def hook_score(ln: Line) -> float:
    if ln.kind == "camera":
        w = 0.4
    elif ln.kind == "dialogue":
        w = 1.0
    else:
        w = 0.8
    s = 2.0 * len(HOOK_WORDS.findall(ln.text)) + 1.5 * len(TONE_WORDS.findall(ln.tone + " " + ln.text))
    s += 1.0 * ln.text.count("!") + 0.5 * ln.text.count("?")
    return w * s


def cliff_score(ln: Line) -> float:
    s = 0.0
    if ln.kind == "dialogue":
        s += 2.5 * ("?" in ln.text) + 1.0 * ("..." in ln.text) + 0.5 * len(HOOK_WORDS.findall(ln.text))
    if ln.kind == "sfx" and CLIFF_SFX.search(ln.text):
        s += 3.0
    if ln.kind in ("camera", "action") and CLIFF_SFX.search(ln.text):
        s += 1.5
    return s


def _candidate(ep: Episode, h: Line, c: Line) -> dict:
    return {"title": f"Ep{ep.number}: {h.text[:30]}",
            "segments": [{"start_line": h.id, "end_line": c.id}],
            "hook_line": h.id, "hook": h.text[:120],
            "cliffhanger_line": c.id, "cliffhanger": c.text[:120],
            "why": "Rule-based: strongest keyword/emotion line as hook, question or ominous beat as ending.",
            "standalone_note": "", "spoiler_level": "none", "confidence": 2}


def find_promos(ep: Episode, index: LineIndex, n: int = 3) -> list[Promo]:
    content = [l for l in ep.lines if l.kind != "camera"]
    hooks = sorted(content, key=hook_score, reverse=True)[:12]
    picks: list[Promo] = []
    for h in hooks:
        window = [c for c in content if h.start + MIN_LEN + 2 <= c.end <= h.start + MAX_LEN - 4]
        if not window:
            continue
        c = max(window, key=lambda x: (cliff_score(x), x.end))
        p = build_promo(_candidate(ep, h, c), f"E{ep.number:02d}-H{len(picks) + 1}", "heuristic", index)
        if p.valid and all(_overlap(p, q) < 10 for q in picks):
            picks.append(p)
        if len(picks) >= n:
            break
    return picks


def judge(p: Promo, index: LineIndex) -> None:
    """Rule-based stand-in for the LLM judge (only used in offline mode)."""
    h, c = index.get(p.hook_line), index.get(p.cliffhanger_line)
    ep = index.eps[p.episode]
    inside = [l for l in ep.lines if p.segments[0].start <= l.start < p.segments[-1].end]
    first3 = [l for l in inside if l.start - p.segments[0].start <= HOOK_WINDOW]
    hk = sum(hook_score(l) for l in first3)
    names = sum(1 for l in inside if l.kind == "dialogue" and HOOK_WORDS.search(l.text))
    p.scores = {
        "hook": min(10.0, 2 + hk / 2),
        "cliffhanger": min(10.0, 3 + cliff_score(c) * 1.2) if c else 3.0,
        "standalone": min(10.0, 3 + names),
        "intensity": min(10.0, 2 + sum(hook_score(l) for l in inside) / 8),
        "clean_cut": 7.0 if (h and h.kind == "dialogue") else 5.0,
    }
    p.judge_verdict = "rule-based score (no AI)"


def _overlap(a: Promo, b: Promo) -> float:
    from .promo import overlap_seconds
    return overlap_seconds(a, b)
