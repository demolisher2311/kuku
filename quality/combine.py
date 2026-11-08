"""Combine both blind review rounds -> quality/quality_summary.md

Round 1 (review_sheet.xlsx) rated the v1 run; round 2 (review_sheet_v2.xlsx) rated the v2 run
(35s minimum, bonus for 45s+). Baseline clips from both rounds are pooled, so the AI's top 10 is
always compared against the baseline's top 13, never against weaker baseline picks.

Usage:  python quality/combine.py
"""
from __future__ import annotations

import sys
from pathlib import Path

from openpyxl import load_workbook

POINTS = {"good": 2, "ok": 1, "okay": 1, "bad": 0, "no": 0}
YES = {"y", "yes", "lyes", "fine"}
NO = {"n", "no"}
ROUNDS = [("v1", "quality/review_sheet.xlsx"), ("v2", "quality/review_sheet_v2.xlsx")]
CRIT = [("hook", 6, 6), ("cliffhanger", 7, 7), ("standalone", 8, 8)]   # (name, sheet col idx, key col idx)


def rows(path: str) -> list[dict]:
    wb = load_workbook(path, data_only=True)
    key = {r[0]: r for r in wb["key"].iter_rows(min_row=2, values_only=True) if r[0] is not None}
    out = []
    for r in wb["1. Rate clips"].iter_rows(min_row=2, values_only=True):
        if r[0] is None or not r[5]:
            continue
        k = key[r[0]]
        d = {"group": k[1], "id": k[3], "verdict": str(r[5]).strip().lower(), "length": float(r[3])}
        for name, col, kcol in CRIT:
            v = str(r[col] or "").strip().lower()
            d[name] = True if v in YES else False if v in NO else None
            d["judge_" + name] = k[kcol]
        out.append(d)
    return out


def summary(rs: list[dict]) -> str:
    n = len(rs)
    good = sum(r["verdict"] == "good" for r in rs)
    gok = sum(r["verdict"] in ("good", "ok", "okay") for r in rs)
    bad = sum(POINTS.get(r["verdict"], 0) == 0 for r in rs)
    avg = sum(POINTS.get(r["verdict"], 0) for r in rs) / n
    hook = [r["hook"] for r in rs if r["hook"] is not None]
    cliff = [r["cliffhanger"] for r in rs if r["cliffhanger"] is not None]
    return (f"| {n} | {100 * good / n:.0f}% | {100 * gok / n:.0f}% | {bad} | {avg:.2f} | "
            f"{100 * sum(hook) / max(1, len(hook)):.0f}% | {100 * sum(cliff) / max(1, len(cliff)):.0f}% |")


def main():
    data = {name: rows(path) for name, path in ROUNDS if Path(path).exists()}
    v1, v2 = data.get("v1", []), data.get("v2", [])
    groups = [
        ("AI v1, top 10", [r for r in v1 if r["group"] == "ai_top"]),
        ("AI v1, bottom half (5)", [r for r in v1 if r["group"] == "ai_low"]),
        ("AI v2 (35s min, 45s+ bonus), top 10", [r for r in v2 if r["group"] == "ai_top"]),
        ("Keyword baseline, top 13 (both rounds)", [r for r in v1 + v2 if r["group"] == "baseline"]),
    ]
    out = ["# Quality summary: two blind review rounds (1 reviewer)", "",
           "| Set | Clips | Good | Good or OK | Bad | Avg points | Hook Y | Cliffhanger Y |",
           "|---|---|---|---|---|---|---|---|"]
    out += [f"| {label} " + summary(rs) for label, rs in groups if rs]

    ai = [r for r in v1 + v2 if r["group"].startswith("ai")]
    out += ["", "## AI judge vs human, all AI clips from both rounds (judge 'yes' = score >= 7)", "",
            "| Criterion | Judge said yes | Human said yes | Agreement | Judge yes, human no |",
            "|---|---|---|---|---|"]
    for name, _, _ in CRIT:
        pairs = [(r["judge_" + name] >= 7, r[name]) for r in ai
                 if r[name] is not None and r["judge_" + name] is not None]
        n = len(pairs)
        out.append(f"| {name} | {sum(j for j, _ in pairs)}/{n} | {sum(h for _, h in pairs)}/{n} | "
                   f"{100 * sum(j == h for j, h in pairs) / n:.0f}% | {sum(j and not h for j, h in pairs)} |")

    bad_ai = [r for r in ai if POINTS.get(r["verdict"], 0) == 0]
    out += ["", "## AI clips rated Bad", ""]
    out += [f"- {r['id']} ({r['length']:.0f}s): human hook {'Y' if r['hook'] else 'N'}, cliffhanger "
            f"{'Y' if r['cliffhanger'] else 'N'}; judge gave hook {r['judge_hook']}, cliffhanger "
            f"{r['judge_cliffhanger']}" for r in bad_ai]

    Path("quality/quality_summary.md").write_text("\n".join(out) + "\n", encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print("\n".join(out))


if __name__ == "__main__":
    main()
