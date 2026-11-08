"""Pairwise (A/B) judge and tournament ranking.

Why: absolute 1-10 scores bunched at 9/9/9, so the judge could not separate the top clips.
Models are more reliable at "which of these two is better?" than at absolute scores.

1. Within each episode every pair of clips is compared once. A/B order is randomised (seeded)
   so position bias averages out instead of doubling the number of calls.
2. Each clip gets: win rate, and a majority vote on the fact checks the judge makes
   (is the tension resolved inside the clip? is it coherent on its own?).
3. Each episode's best clip ("champion") enters a Swiss tournament against other champions,
   so the top of the global list is decided by direct comparisons too.
4. Final order: clips that pass the fact checks first (champions by tournament points, then the
   rest by win rate), then clips that fail them. Code decides all of this;
   the model only answers "A or B" and the fact checks.
"""
from __future__ import annotations

import itertools
import json
import random
from concurrent.futures import ThreadPoolExecutor

from . import prompts as P
from .llm import LLM
from .promo import LineIndex, Promo, excerpt

SWISS_ROUNDS = 5
SEED = 7


def compare(llm: LLM, a_text: str, a_sec: float, b_text: str, b_sec: float) -> tuple[dict, str]:
    """One A/B call. Returns (parsed, raw)."""
    data, raw = llm.json(P.PAIR_JUDGE_SYSTEM, P.PAIR_JUDGE_USER.format(a=a_text, a_sec=a_sec, b=b_text, b_sec=b_sec))
    return data, raw


def _side(v) -> str | None:
    s = str(v or "").strip().lower()
    return "A" if s.endswith(" a") or s == "a" else "B" if s.endswith(" b") or s == "b" else None


def _bool(v) -> bool | None:
    if isinstance(v, bool):
        return v
    s = str(v).strip().lower()
    return True if s == "true" else False if s == "false" else None


class Ledger:
    """Everything the pairwise judge said about each clip."""

    def __init__(self):
        self.games: dict[str, list[float]] = {}           # clip id -> results (1 win, 0 loss)
        self.hook: dict[str, list[float]] = {}
        self.resolved: dict[str, list[bool]] = {}
        self.coherent: dict[str, list[bool]] = {}
        self.swiss: dict[str, float] = {}
        self.log: list[dict] = []

    def record(self, a: Promo, b: Promo, data: dict, raw: str, stage: str):
        win = _side(data.get("winner"))
        hook = _side((data.get("comparison") or {}).get("better_hook"))
        for p, side in ((a, "A"), (b, "B")):
            facts = data.get(f"clip_{side}") or {}
            r, c = _bool(facts.get("is_tension_resolved_within_clip")), _bool(facts.get("is_coherent_standalone"))
            if r is not None:
                self.resolved.setdefault(p.id, []).append(r)
            if c is not None:
                self.coherent.setdefault(p.id, []).append(c)
            if win:
                res = 1.0 if win == side else 0.0
                if stage == "episode":
                    self.games.setdefault(p.id, []).append(res)
                else:
                    self.swiss[p.id] = self.swiss.get(p.id, 0.0) + res
            if hook:
                self.hook.setdefault(p.id, []).append(1.0 if hook == side else 0.0)
        self.log.append({"stage": stage, "A": a.id, "B": b.id, "winner": win,
                         "reasoning": (data.get("comparison") or {}).get("reasoning", ""), "raw": raw})

    @staticmethod
    def _rate(v: list[float]) -> float:
        return sum(v) / len(v) if v else 0.5

    @staticmethod
    def _majority(v: list[bool]) -> bool | None:
        return None if not v else sum(v) * 2 > len(v)

    def win_rate(self, pid: str) -> float:
        return self._rate(self.games.get(pid, []))

    def gate(self, pid: str) -> bool:
        """Passes the gatekeeper: tension NOT resolved inside the clip, and coherent."""
        return self._majority(self.resolved.get(pid, [])) is not True and \
            self._majority(self.coherent.get(pid, [])) is not False


def _texts(promos: list[Promo], index: LineIndex) -> dict[str, str]:
    return {p.id: excerpt(p, index) for p in promos}


def judge_episode(llm: LLM, promos: list[Promo], index: LineIndex, ledger: Ledger, rng_seed: int):
    """Round robin inside one episode (each pair once, random A/B order)."""
    rng = random.Random(rng_seed)
    txt = _texts(promos, index)
    for a, b in itertools.combinations(promos, 2):
        if rng.random() < 0.5:
            a, b = b, a
        try:
            data, raw = compare(llm, txt[a.id], a.total, txt[b.id], b.total)
        except Exception as e:  # noqa: BLE001  one failed comparison must not sink the run
            ledger.log.append({"stage": "episode", "A": a.id, "B": b.id, "winner": None, "error": str(e)[:300]})
            continue
        ledger.record(a, b, data, raw, "episode")


def champions(groups: dict[int, list[Promo]], ledger: Ledger) -> list[Promo]:
    out = []
    for _, g in sorted(groups.items()):
        if g:
            out.append(max(g, key=lambda p: (ledger.gate(p.id), ledger.win_rate(p.id),
                                              ledger._rate(ledger.hook.get(p.id, [])))))
    return out


def swiss(llm: LLM, champs: list[Promo], index: LineIndex, ledger: Ledger, workers: int = 4,
          rounds: int = SWISS_ROUNDS, log=print):
    """Swiss tournament among episode champions: each round pairs clips with similar points."""
    rng = random.Random(SEED)
    txt = _texts(champs, index)
    met: set[frozenset] = set()
    for p in champs:
        ledger.swiss.setdefault(p.id, 0.0)
    for rnd in range(1, rounds + 1):
        order = sorted(champs, key=lambda p: (-ledger.swiss[p.id], not ledger.gate(p.id),
                                              -ledger.win_rate(p.id), p.id))
        pairs, waiting = [], list(order)
        while len(waiting) > 1:
            a = waiting.pop(0)
            j = next((k for k, b in enumerate(waiting) if frozenset((a.id, b.id)) not in met), 0)
            b = waiting.pop(j)
            met.add(frozenset((a.id, b.id)))
            pairs.append((b, a) if rng.random() < 0.5 else (a, b))
        if waiting:                       # odd one out gets a bye (half a point)
            ledger.swiss[waiting[0].id] += 0.5

        def play(pair):
            a, b = pair
            try:
                return a, b, *compare(llm, txt[a.id], a.total, txt[b.id], b.total), ""
            except Exception as e:  # noqa: BLE001
                return a, b, None, "", str(e)[:300]
        with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
            for a, b, data, raw, err in pool.map(play, pairs):
                if err:
                    ledger.log.append({"stage": "swiss", "A": a.id, "B": b.id, "winner": None, "error": err})
                else:
                    ledger.record(a, b, data, raw, "swiss")
        log(f"  swiss round {rnd}/{rounds}: {len(pairs)} matches")


def order(promos: list[Promo], champs: list[Promo], ledger: Ledger) -> list[Promo]:
    """Champions by tournament result, then everyone else. Fills scores/reasons on each promo."""
    champ_ids = {p.id for p in champs}
    for p in promos:
        hook = ledger._rate(ledger.hook.get(p.id, []))
        p.scores = {"win_rate": round(ledger.win_rate(p.id), 2), "hook_win_rate": round(hook, 2)}
        p.approved = ledger.gate(p.id)
        if p.id in champ_ids:
            p.scores["swiss_points"] = ledger.swiss.get(p.id, 0.0)
        res, coh = ledger._majority(ledger.resolved.get(p.id, [])), ledger._majority(ledger.coherent.get(p.id, []))
        parts = []
        if p.id in champ_ids:
            parts.append(f"best clip of its episode; won {ledger.swiss.get(p.id, 0):g}/{SWISS_ROUNDS} "
                         "head-to-heads against other episodes' best")
        parts.append(f"won {ledger.win_rate(p.id):.0%} of comparisons within its episode")
        if res:
            parts.append("judge: tension is resolved inside the clip (weak cliffhanger)")
        if coh is False:
            parts.append("judge: confusing out of context")
        p.rank_reason = "; ".join(parts)
        p.final_score = round((ledger.swiss.get(p.id, 0.0) if p.id in champ_ids else 0.0)
                              + ledger.win_rate(p.id), 2)

    def key(p: Promo):
        champ = p.id in champ_ids
        return (not ledger.gate(p.id), not champ,
                -(ledger.swiss.get(p.id, 0.0) if champ else 0.0), -ledger.win_rate(p.id),
                -ledger._rate(ledger.hook.get(p.id, [])), p.episode)
    return sorted([p for p in promos if p.valid], key=key)


def write_log(ledger: Ledger, path) -> None:
    path.write_text(json.dumps(ledger.log, indent=1, ensure_ascii=False), encoding="utf-8")
