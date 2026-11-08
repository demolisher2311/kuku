"""Which AI judge agrees with the human reviewer? -> quality/judge_eval_<model>.md

Uses every clip the human rated blind (both review rounds), exactly as the human saw it.

Judges compared:
  classic   batched 1-10 scores (the first judge)
  strict    1-10 scores, analysis first, one call per clip
  pairwise  A/B: "which of these two clips is the better promo?" + fact checks

The fair common test is PAIRWISE ACCURACY: for every pair of clips where the human rated one
Good and the other Bad, does the judge prefer the Good one? Score judges prefer the higher total
(a tie counts as half). The pairwise judge sees each pair once, in random A/B order (seeded), so
we can also measure position bias (how often it picks whichever clip is shown first).

Usage:
  python quality/judge_eval.py --model gemini-3.5-flash-lite
  python quality/judge_eval.py --model gemini-3.5-flash-lite --also-cached openai:gpt-4.1-mini
      (adds results for an older model, read from the cache only: no API call, no key sent)
"""
from __future__ import annotations

import argparse
import itertools
import random
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv  # noqa: E402
from openpyxl import load_workbook  # noqa: E402

from core import prompts as P  # noqa: E402
from core.finder import _num, strict_scores, APPROVE_TOTAL, APPROVE_HOOK  # noqa: E402
from core.llm import LLM  # noqa: E402
from core.pairwise import _bool, _side  # noqa: E402

SHEETS = ["quality/review_sheet.xlsx", "quality/review_sheet_v2.xlsx"]
POINTS = {"good": 2, "ok": 1, "okay": 1, "bad": 0, "no": 0}
YES, NO = {"y", "yes", "lyes", "fine"}, {"n", "no"}
CRIT = [("hook", 6), ("cliffhanger", 7), ("standalone", 8)]   # human column index in sheet 1


def yn(v):
    s = str(v or "").strip().lower()
    return True if s in YES else False if s in NO else None


def load_clips() -> list[dict]:
    clips = []
    for path in SHEETS:
        if not Path(path).exists():
            continue
        wb = load_workbook(path, data_only=True)
        key = {r[0]: r for r in wb["key"].iter_rows(min_row=2, values_only=True) if r[0] is not None}
        for r in wb["1. Rate clips"].iter_rows(min_row=2, values_only=True):
            if r[0] is None or not r[5]:
                continue
            c = {"n": len(clips), "round": "v2" if path.endswith("_v2.xlsx") else "v1", "id": key[r[0]][3],
                 "group": key[r[0]][1], "seconds": float(r[3]), "script": r[4],
                 "points": POINTS.get(str(r[5]).strip().lower(), 0), "verdict": str(r[5]).strip().lower()}
            c.update({name: yn(r[col]) for name, col in CRIT})
            clips.append(c)
    return clips


# --------------------------------------------------------------------------- score judges
def classic(llm: LLM, c: dict) -> dict:
    data, _ = llm.json(P.JUDGE_SYSTEM, P.JUDGE_USER.format(
        clips=f"### CLIP id=c ({c['seconds']:.0f}s)\n{c['script']}"))
    s = (data.get("scores") or [{}])[0]
    return {k: _num(s.get(k)) for k in ("hook", "cliffhanger", "standalone")}


def strict(llm: LLM, c: dict) -> dict:
    data, _ = llm.json(P.STRICT_JUDGE_SYSTEM, P.STRICT_JUDGE_USER.format(seconds=c["seconds"], clip=c["script"]))
    return strict_scores(data)[0]


def safe(fn, llm, c):
    try:
        return fn(llm, c)
    except Exception:  # noqa: BLE001
        return None


# --------------------------------------------------------------------------- pairwise judge
def human_pairs(clips: list[dict], seed: int = 7) -> list[tuple[dict, dict, bool]]:
    """Every (Good, Bad) pair, shuffled into random A/B order. Third item: True if Good is A."""
    rng = random.Random(seed)
    out = []
    for g, b in itertools.product([c for c in clips if c["points"] == 2], [c for c in clips if c["points"] == 0]):
        out.append((g, b, True) if rng.random() < 0.5 else (b, g, False))
    return out


def pair_call(llm: LLM, a: dict, b: dict):
    try:
        data, _ = llm.json(P.PAIR_JUDGE_SYSTEM, P.PAIR_JUDGE_USER.format(
            a=a["script"], a_sec=a["seconds"], b=b["script"], b_sec=b["seconds"]))
        return data
    except Exception:  # noqa: BLE001
        return None


def pct(a: float, b: int) -> str:
    return f"{100 * a / b:.0f}% ({a:g}/{b})" if b else "n/a"


def evaluate(llm: LLM, clips: list[dict], pairs, workers: int, run_pairwise: bool) -> dict:
    with ThreadPoolExecutor(max_workers=workers) as pool:
        res = {"classic": list(pool.map(lambda c: safe(classic, llm, c), clips)),
               "strict": list(pool.map(lambda c: safe(strict, llm, c), clips))}
        res["pairwise"] = list(pool.map(lambda t: pair_call(llm, t[0], t[1]), pairs)) if run_pairwise else []
    return res


def report(name: str, clips, pairs, res) -> list[str]:
    out = [f"## {name}", ""]
    # 1. pairwise accuracy on Good-vs-Bad pairs, all three judges
    out += ["| Judge | Picks the clip you rated Good (over the Bad one) | Failed calls |", "|---|---|---|"]
    for j in ("classic", "strict"):
        sc = res[j]
        acc, n, fail = 0.0, 0, 0
        for a, b, good_is_a in pairs:
            sa, sb = sc[a["n"]], sc[b["n"]]
            if sa is None or sb is None:
                fail += 1
                continue
            ta, tb = sum(sa.values()), sum(sb.values())
            n += 1
            acc += 0.5 if ta == tb else float((ta > tb) == good_is_a)
        out.append(f"| {j} (1-10 scores; tie = half) | {pct(acc, n)} | {fail} |")
    if res["pairwise"]:
        acc = n = fail = a_wins = 0
        for (a, b, good_is_a), d in zip(pairs, res["pairwise"]):
            w = _side((d or {}).get("winner"))
            if not w:
                fail += 1
                continue
            n += 1
            acc += (w == "A") == good_is_a
            a_wins += w == "A"
        out.append(f"| pairwise (A/B) | {pct(acc, n)} | {fail} |")
        out += ["", f"Position bias: the pairwise judge picked Clip A in {pct(a_wins, n)} of comparisons "
                f"(the Good clip was A in {pct(sum(g for *_, g in pairs), len(pairs))})."]

    # 2. per-criterion agreement with the human (score judges: >= 7 means yes)
    out += ["", "| Criterion | classic agrees | strict agrees | pairwise fact check agrees |", "|---|---|---|---|"]
    facts = {c["n"]: {"resolved": [], "coherent": []} for c in clips}
    for (a, b, _), d in zip(pairs, res["pairwise"]):
        for c, side in ((a, "A"), (b, "B")):
            f = (d or {}).get(f"clip_{side}") or {}
            r, co = _bool(f.get("is_tension_resolved_within_clip")), _bool(f.get("is_coherent_standalone"))
            if r is not None:
                facts[c["n"]]["resolved"].append(r)
            if co is not None:
                facts[c["n"]]["coherent"].append(co)
    maj = lambda v: None if not v else sum(v) * 2 > len(v)  # noqa: E731
    for crit, _ in CRIT:
        cells = []
        for j in ("classic", "strict"):
            ps = [(res[j][c["n"]][crit] >= 7, c[crit]) for c in clips if c[crit] is not None and res[j][c["n"]]]
            cells.append(pct(sum(x == y for x, y in ps), len(ps)))
        if crit == "cliffhanger" and res["pairwise"]:
            ps = [(maj(facts[c["n"]]["resolved"]) is False, c[crit]) for c in clips
                  if c[crit] is not None and facts[c["n"]]["resolved"]]
            cells.append(pct(sum(x == y for x, y in ps), len(ps)) + " (not resolved = cliffhanger)")
        elif crit == "standalone" and res["pairwise"]:
            ps = [(maj(facts[c["n"]]["coherent"]), c[crit]) for c in clips
                  if c[crit] is not None and facts[c["n"]]["coherent"]]
            cells.append(pct(sum(x == y for x, y in ps), len(ps)))
        else:
            cells.append("(compared via better_hook, not per clip)" if crit == "hook" else "n/a")
        out.append(f"| {crit} | " + " | ".join(cells) + " |")

    # 3. how much the score judges spread their scores (bunching at 9 = cannot separate clips)
    out += [""]
    for j in ("classic", "strict"):
        tot = [sum(s.values()) for s in res[j] if s]
        if tot:
            nine = sum(1 for s in res[j] if s and all(v >= 9 for v in s.values()))
            out.append(f"- {j}: totals range {min(tot):.0f}-{max(tot):.0f} of 30; {nine}/{len(tot)} clips got 9+ on everything")
    return out + [""]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", help="model for the live run (default: LLM_MODEL in .env)")
    ap.add_argument("--provider", help="provider (default: LLM_PROVIDER in .env)")
    ap.add_argument("--also-cached", default="", help="provider:model to add from the cache only")
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()
    load_dotenv(".env")

    clips = load_clips()
    pairs = human_pairs(clips)
    llm = LLM.from_env(provider=a.provider, model=a.model, temperature=0.2)
    sections = [(llm.name, evaluate(llm, clips, pairs, a.workers, run_pairwise=True), llm)]
    if a.also_cached:
        prov, model = a.also_cached.split(":", 1)
        old = LLM(provider=prov, model=model, api_key="not-used", temperature=0.2)
        old.cache_only = True
        sections.append((old.name + " (from cache; pairwise not run on this model)",
                         evaluate(old, clips, pairs, a.workers, run_pairwise=False), old))

    out = [f"# Judge vs human: {len(clips)} clips rated blind, {len(pairs)} Good-vs-Bad pairs", "",
           "Each judge sees exactly the clip script the human saw. Score judges: 'yes' = score >= 7.", ""]
    for name, res, _ in sections:
        out += report(name, clips, pairs, res)
    u = llm.usage
    out.append(f"API usage ({llm.name}): {u.get('calls', 0)} calls, {u.get('cached', 0)} cached, tokens in "
               f"{u.get('tokens_in', 0):,}, out {u.get('tokens_out', 0):,}, thinking {u.get('tokens_thinking', 0):,}")

    path = Path(f"quality/judge_eval_{llm.model}.md")
    path.write_text("\n".join(out) + "\n", encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print("\n".join(out))
    print(f"\nSaved {path}")


if __name__ == "__main__":
    main()
