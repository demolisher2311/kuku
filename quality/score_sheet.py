"""Score a filled review sheet -> quality/quality_report.md

Reports:
  1. Human ratings per group (ai_top / ai_low / baseline): is the AI better than rules,
     and do top-ranked promos beat low-ranked ones?
  2. Which promo rule fails most often (hook, cliffhanger, standalone, clean cut).
  3. How often the AI judge agrees with you (is the LLM-as-judge trustworthy?).
  4. Recall: did the tool find the promo YOU would have cut?
  5. Every clip you rated Bad, with your note (the failure list for the solution doc).

Usage:
  python quality/score_sheet.py --ai outputs/openai_gpt-4.1-mini_full --baseline outputs/heuristic
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

from openpyxl import load_workbook

CRITERIA = [("hook", 7, "judge_hook"), ("cliffhanger", 8, "judge_cliffhanger"),
            ("standalone", 9, "judge_standalone"), ("clean_cut", 10, "judge_clean_cut")]
POINTS = {"good": 2, "ok": 1, "bad": 0}
JUDGE_PASS = 7          # judge score >= 7 counts as "judge says yes"
MATCH = 0.5             # tool clip overlaps >= 50% of the shorter of the two -> "found it"


def to_sec(v) -> float | None:
    """Accept '01:12', '1:12.5', '72', 72, or an Excel time that ate '01:12' as 01h12m."""
    if v is None or v == "":
        return None
    if isinstance(v, dt.time):
        return v.hour * 60 + v.minute if v.second == 0 and v.hour < 10 else v.minute * 60 + v.second
    if isinstance(v, dt.datetime):
        return to_sec(v.time())
    if isinstance(v, (int, float)):
        return float(v) * 86400 if 0 < float(v) < 1 else float(v)   # Excel day-fraction or seconds
    s = str(v).strip()
    m = re.search(r"(\d{1,2}):(\d{1,2}(?:\.\d+)?)", s)   # also accepts pasted "Start: (00:45.20)"
    if m:
        return int(m.group(1)) * 60 + float(m.group(2))
    try:
        return float(s)
    except ValueError:
        return None


YES = {"y", "yes", "lyes", "fine", "true", "1"}
NO = {"n", "no", "false", "0"}
VERDICT = {"good": "good", "ok": "ok", "okay": "ok", "bad": "bad", "no": "bad"}


def yes(v) -> bool | None:
    """Y/N, plus words reviewers actually type. 'little', "don't know" -> None (not counted)."""
    s = str(v or "").strip().lower()
    return True if s in YES else False if s in NO else None


def pct(a: int, b: int) -> str:
    return f"{100 * a / b:.0f}% ({a}/{b})" if b else "n/a"


def best_match(promos: list[dict], ep: int, start: float, end: float) -> tuple[dict | None, float]:
    best, best_ov = None, 0.0
    for p in promos:
        ov = sum(max(0.0, min(s["end"], end) - max(s["start"], start))
                 for s in p["segments"] if s["episode"] == ep)
        frac = ov / max(1e-6, min(p["total_seconds"], end - start))
        if frac > best_ov:
            best, best_ov = p, frac
    return best, best_ov


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ai", required=True)
    ap.add_argument("--baseline", default="")
    ap.add_argument("--sheet", default="quality/review_sheet.xlsx")
    ap.add_argument("--out", default="quality/quality_report.md")
    a = ap.parse_args()

    wb = load_workbook(a.sheet, data_only=True)
    key = {r[0]: dict(zip([c.value for c in wb["key"][1]], r))
           for r in wb["key"].iter_rows(min_row=2, values_only=True) if r[0] is not None}
    rows = []
    for r in wb["1. Rate clips"].iter_rows(min_row=2, values_only=True):
        if r[0] is None or not r[5]:
            continue
        k = key[r[0]]
        rows.append({"clip": r[0], "group": k["group"], "id": k["id"], "rank": k["tool_rank"],
                     "segments": r[2], "length": r[3],
                     "verdict": VERDICT.get(str(r[5]).strip().lower(), str(r[5]).strip().lower()),
                     "notes": r[10] or "",
                     **{c: yes(r[col - 1]) for c, col, _ in CRITERIA},
                     **{jk: k[jk] for _, _, jk in CRITERIA}})

    out = ["# Quality check: human review", "",
           f"Blind review of {len(rows)} clips (source hidden while rating). Sheet: `{a.sheet}`.", ""]

    # 1. Ratings per group
    out += ["## 1. Human verdict by source", "",
            "| Group | Clips | Good | Good or OK | Avg points (Good=2, OK=1, Bad=0) |", "|---|---|---|---|---|"]
    for g, label in (("ai_top", "AI tool: top-ranked"), ("ai_low", "AI tool: bottom half"),
                     ("baseline", "Keyword baseline (no AI)")):
        rs = [r for r in rows if r["group"] == g]
        if not rs:
            continue
        good = sum(r["verdict"] == "good" for r in rs)
        ok = sum(r["verdict"] in ("good", "ok") for r in rs)
        avg = sum(POINTS.get(r["verdict"], 0) for r in rs) / len(rs)
        out.append(f"| {label} | {len(rs)} | {pct(good, len(rs))} | {pct(ok, len(rs))} | {avg:.2f} |")

    # 1b. Does clip length explain the verdict?
    out += ["", "### Verdict by clip length (all sources)", "",
            "| Length | Clips | Good | Avg points |", "|---|---|---|---|"]
    for lo, hi in ((20, 35), (35, 45), (45, 61)):
        rs = [r for r in rows if r["length"] is not None and lo <= float(r["length"]) < hi]
        if rs:
            avg = sum(POINTS.get(r["verdict"], 0) for r in rs) / len(rs)
            out.append(f"| {lo}-{min(hi, 60)}s | {len(rs)} | {pct(sum(r['verdict'] == 'good' for r in rs), len(rs))} | {avg:.2f} |")

    # 2. Criteria pass rates
    out += ["", "## 2. Which rule fails most (Y rate per criterion)", "",
            "| Criterion | AI top | AI low | Baseline |", "|---|---|---|---|"]
    for c, _, _ in CRITERIA:
        cells = []
        for g in ("ai_top", "ai_low", "baseline"):
            vals = [r[c] for r in rows if r["group"] == g and r[c] is not None]
            cells.append(pct(sum(vals), len(vals)))
        out.append(f"| {c} | " + " | ".join(cells) + " |")

    # 3. Judge agreement (AI clips only)
    out += ["", f"## 3. Does the AI judge agree with you? (judge 'yes' = score >= {JUDGE_PASS})", "",
            "| Criterion | Agreement | Judge said yes, you said no (judge too generous) |", "|---|---|---|"]
    for c, _, jk in CRITERIA:
        pairs = [(r[jk] is not None and r[jk] >= JUDGE_PASS, r[c]) for r in rows
                 if r["group"].startswith("ai") and r[c] is not None and r[jk] is not None]
        agree = sum(j == h for j, h in pairs)
        generous = sum(j and not h for j, h in pairs)
        out.append(f"| {c} | {pct(agree, len(pairs))} | {generous} |")

    # 4. Recall vs your own picks
    ai_promos = json.loads((Path(a.ai) / "promos_all.json").read_text(encoding="utf-8"))["ranked"]
    base_promos = (json.loads((Path(a.baseline) / "promos_all.json").read_text(encoding="utf-8"))["ranked"]
                   if a.baseline else [])
    picks = []
    for r in wb["2. Your picks"].iter_rows(min_row=2, values_only=True):
        if r[0] is None:
            continue
        s, e = to_sec(r[1]), to_sec(r[2])
        if s is not None and e is not None and e > s:
            picks.append((int(r[0]), s, e, r[3] or ""))
    if picks:
        out += ["", f"## 4. Recall: did the tool find your pick? (match = overlap >= {MATCH:.0%})", "",
                "| Episode | Your clip | AI best match | Overlap | AI rank | Baseline overlap |", "|---|---|---|---|---|---|"]
        found = 0
        for ep, s, e, hook in picks:
            p, ov = best_match(ai_promos, ep, s, e)
            _, bov = best_match(base_promos, ep, s, e) if base_promos else (None, 0.0)
            hit = ov >= MATCH
            found += hit
            out.append(f"| {ep} | {int(s // 60):02d}:{s % 60:04.1f}-{int(e // 60):02d}:{e % 60:04.1f} | "
                       f"{(p['id'] + ' ' + p['segments_label']) if p else '-'} | {ov:.0%}{' ✓' if hit else ''} | "
                       f"{p['rank'] if p else '-'} | {bov:.0%} |")
        out.append(f"\n**AI found {found}/{len(picks)} of your picks.**")

    # 5. Failure list
    bad = [r for r in rows if r["verdict"] == "bad"]
    if bad:
        out += ["", "## 5. Clips you rated Bad", ""]
        out += [f"- **{r['group']}** {r['id']} (tool rank {r['rank']}, {r['segments']}): {r['notes'] or '(no note)'}"
                for r in bad]

    Path(a.out).write_text("\n".join(out) + "\n", encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")   # Windows console is cp1252
    print("\n".join(out))
    print(f"\nSaved {a.out}")


if __name__ == "__main__":
    main()
