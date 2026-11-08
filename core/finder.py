"""LLM steps: series bible, promo candidates per episode, one repair round, cold-viewer judge."""
from __future__ import annotations

import json
from collections import Counter

from . import prompts as P
from .llm import LLM
from .parser import Episode
from .promo import LineIndex, Promo, build_promo, excerpt

NEXT_EP_SECONDS = 60.0   # how much of the next episode the finder may use for cross-episode promos


# --------------------------------------------------------------------------- bible
def build_bible(llm: LLM | None, episodes: list[Episode], title: str) -> dict:
    if llm is None:
        return {"title": title, "premise": episodes[0].logline if episodes else "",
                "characters": [], "major_twists": []}
    speakers = Counter(l.speaker for e in episodes for l in e.lines if l.kind == "dialogue")
    eps_txt = "\n".join(f"Ep {e.number}: {e.logline} | Notes: {e.continuity}" for e in episodes)
    data, _ = llm.json(P.BIBLE_SYSTEM, P.BIBLE_USER.format(
        title=title, episodes=eps_txt, speakers=", ".join(s for s, _ in speakers.most_common(60))))
    data.setdefault("title", title)
    return data


def bible_text(bible: dict) -> str:
    out = [f"Title: {bible.get('title', '')}", f"Premise: {bible.get('premise', '')}"]
    for c in bible.get("characters", [])[:25]:
        al = ", ".join(c.get("aliases", []) or [])
        out.append(f"- {c.get('name')}{f' (also: {al})' if al else ''}: {c.get('role', '')}")
    tw = bible.get("major_twists", [])
    if tw:
        out.append("Major twists (showing these is a spoiler): " +
                   "; ".join(f"ep{t.get('episode')}: {t.get('twist')}" for t in tw[:12]))
    return "\n".join(out)


# --------------------------------------------------------------------------- finder
def _find_prompt(ep: Episode, prev: Episode | None, nxt: Episode | None, bible: str, n: int) -> str:
    lines = "\n".join(l.render() for l in ep.lines)
    next_block, next_note = "", ""
    if nxt:
        nl = "\n".join(l.render() for l in nxt.lines if l.start <= NEXT_EP_SECONDS)
        next_block = P.NEXT_BLOCK.format(ep=nxt.number, lines=nl)
        next_note = f" (a later segment may come from the start of EPISODE {nxt.number})"
    return P.FIND_USER.format(bible=bible, prev_logline=prev.logline if prev else "(this is the first episode)",
                              ep=ep.number, logline=ep.logline, lines=lines, next_block=next_block,
                              next_note=next_note, n=n)


REPAIR_ROUNDS = 2


def _autofix(p: Promo, raw: dict, index: LineIndex) -> Promo | None:
    """Code-only fix: the model's segments are wrong, but its own hook -> cliffhanger span may be valid."""
    h, c = index.get(p.hook_line), index.get(p.cliffhanger_line)
    if not (h and c and h.episode == c.episode and h.idx < c.idx):
        return None
    q = build_promo(dict(raw, segments=[{"start_line": h.id, "end_line": c.id}]), p.id + "a", p.source, index)
    if not q.valid:
        return None
    q.stage, q.repaired = "autofix", True
    p.errors.append(f"(replaced by {q.id}: cut from its own hook_line to cliffhanger_line, in code)")
    return q


def _triage(raws: list[dict], ids: list[str], stage: str, llm: LLM, index: LineIndex
            ) -> tuple[list[Promo], list[Promo], list[Promo]]:
    """Build + validate candidates. Returns (valid, still_invalid, rejected_originals)."""
    valid, invalid, replaced = [], [], []
    for pid, r in zip(ids, raws):
        p = build_promo(r, pid, llm.name, index)
        p.stage, p.repaired = stage, stage != "first"
        if p.valid:
            valid.append(p)
        elif (q := _autofix(p, r, index)):
            valid.append(q)
            replaced.append(p)
        else:
            invalid.append(p)
    return valid, invalid, replaced


def find_promos(llm: LLM, ep: Episode, prev: Episode | None, nxt: Episode | None, bible: str,
                index: LineIndex, n: int = 4) -> tuple[list[Promo], dict]:
    """Ask for candidates, validate them in code, auto-fix what code can, and give the model
    up to REPAIR_ROUNDS chances (with pre-computed options) to fix the rest."""
    user = _find_prompt(ep, prev, nxt, bible, n)
    raw_log = {}
    try:
        data, raw = llm.json(P.FIND_SYSTEM, user)
    except Exception as e:  # noqa: BLE001 - keep the run going, record the failure
        raw_log["find_error"] = str(e)
        return [], raw_log
    raw_log["find"] = raw
    raws = data.get("promos", [])
    valid, pending, rejected = _triage(raws, [f"E{ep.number:02d}-P{k + 1}" for k in range(len(raws))],
                                       "first", llm, index)

    for rnd in range(1, REPAIR_ROUNDS + 1):
        if not pending:
            break
        errors = "\n".join(f"- {p.id} \"{p.title}\": " + "; ".join(p.errors) for p in pending)
        payload = json.dumps({"promos": [p.raw_for_llm() for p in pending]}, indent=1)
        try:
            fixed, raw_fix = llm.json(P.FIND_SYSTEM, user + "\n\n" + P.REPAIR_USER.format(errors=errors, promos=payload))
        except Exception as e:  # noqa: BLE001
            raw_log[f"repair{rnd}_error"] = str(e)
            break
        raw_log[f"repair{rnd}"] = raw_fix
        for p in pending:
            p.errors.append(f"(rejected; sent to repair round {rnd})")
        rejected += pending
        raws = fixed.get("promos", [])
        v, pending, rep = _triage(raws, [f"E{ep.number:02d}-R{rnd}.{k + 1}" for k in range(len(raws))],
                                  f"repair{rnd}", llm, index)
        valid += v
        rejected += rep
    # keep every failure, so the output shows what was rejected and why
    return valid + rejected + pending, raw_log


# --------------------------------------------------------------------------- judge
def judge_promos(llm: LLM, promos: list[Promo], index: LineIndex) -> str:
    """Score clips as a cold viewer: the judge sees ONLY the clip, no bible, no episode context."""
    if not promos:
        return ""
    clips = "\n\n".join(f"### CLIP id={p.id} ({p.total:.0f}s)\n{excerpt(p, index)}" for p in promos)
    data, raw = llm.json(P.JUDGE_SYSTEM, P.JUDGE_USER.format(clips=clips))
    by_id = {str(s.get("id")): s for s in data.get("scores", [])}
    for p in promos:
        s = by_id.get(p.id)
        if not s:
            continue
        p.scores = {k: _num(s.get(k)) for k in ("hook", "cliffhanger", "standalone", "intensity", "clean_cut")}
        p.judge_verdict = str(s.get("verdict", ""))
        p.judge_confusing = str(s.get("confusing", ""))
    return raw


# Approval rule from the strict judge prompt, computed in code (the model's own total/flag are not trusted)
APPROVE_TOTAL, APPROVE_HOOK = 22, 7


def strict_scores(data: dict) -> tuple[dict, bool]:
    sc = data.get("scores", {}) or {}
    scores = {"hook": _num(sc.get("hook")), "cliffhanger": _num(sc.get("cliffhanger")),
              "standalone": _num(sc.get("coherence"))}
    approved = sum(scores.values()) >= APPROVE_TOTAL and scores["hook"] >= APPROVE_HOOK
    return scores, approved


def judge_strict(llm: LLM, promos: list[Promo], index: LineIndex) -> str:
    """Strict judge: one call per clip, analysis before scores. Sees ONLY the clip."""
    raws = []
    for p in promos:
        data, raw = llm.json(P.STRICT_JUDGE_SYSTEM,
                             P.STRICT_JUDGE_USER.format(seconds=p.total, clip=excerpt(p, index)))
        raws.append(f'{{"id": "{p.id}", "response": {raw}}}')
        p.scores, p.approved = strict_scores(data)
        a = data.get("analysis", {}) or {}
        p.judge_verdict = " ".join(str(a.get(k, "")) for k in ("hook_check", "cliffhanger_check")).strip()
        p.judge_confusing = str(a.get("coherence_check", ""))
    return "[\n" + ",\n".join(raws) + "\n]"


def _num(v) -> float:
    try:
        return max(1.0, min(10.0, float(v)))
    except (TypeError, ValueError):
        return 5.0
