"""Compare two runs (e.g. before / after a fix) -> quality/compare_report.md

1. Shape of the output: how many promos, how long, how many pass on the first try.
2. Where the clips you rated land in each run's ranking. Each rated clip is matched to the
   run's promo that overlaps it most (>= 50% of the shorter clip). This is a proxy: the new run
   cuts slightly different clips, so a fresh blind review is the real test.

Usage:
  python quality/compare_runs.py --old outputs/openai_gpt-4.1-mini_full --new outputs/openai_gpt-4.1-mini_v2 \
      --baseline outputs/heuristic
"""
from __future__ import annotations

import argparse
import json
import statistics as st
import sys
from pathlib import Path

from openpyxl import load_workbook

POINTS = {"good": 2, "ok": 1, "okay": 1, "bad": 0, "no": 0}
TOP = 20
MATCH = 0.5


def load(run: str) -> tuple[list[dict], dict]:
    d = json.loads((Path(run) / "promos_all.json").read_text(encoding="utf-8"))
    info = json.loads((Path(run) / "run_info.json").read_text(encoding="utf-8"))
    return [p for p in d["ranked"] if not p.get("duplicate_of")], info


def overlap(a: dict, b: dict) -> float:
    ov = sum(max(0.0, min(s["end"], t["end"]) - max(s["start"], t["start"]))
             for s in a["segments"] for t in b["segments"] if s["episode"] == t["episode"])
    return ov / max(1e-6, min(a["total_seconds"], b["total_seconds"]))


def pct(a: int, b: int) -> str:
    return f"{100 * a / b:.0f}% ({a}/{b})" if b else "n/a"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--old", required=True)
    ap.add_argument("--new", required=True)
    ap.add_argument("--baseline", default="outputs/heuristic")
    ap.add_argument("--rated-from", default="outputs/openai_gpt-4.1-mini_full",
                    help="run the AI clips on the review sheet were taken from")
    ap.add_argument("--sheet", default="quality/review_sheet.xlsx")
    ap.add_argument("--out", default="quality/compare_report.md")
    a = ap.parse_args()

    runs = {"before": load(a.old), "after": load(a.new)}
    out = [f"# Before vs after: `{a.old}` -> `{a.new}`", "",
           "## 1. Output shape (distinct promos, near-duplicates removed)", "",
           "| | Before | After |", "|---|---|---|"]

    def row(label, f):
        out.append(f"| {label} | {f(*runs['before'])} | {f(*runs['after'])} |")

    row("Valid candidates", lambda P, I: I["valid"])
    row("Distinct promos", lambda P, I: len(P))
    row("Valid on first try", lambda P, I: I.get("first_try_pass_rate", "-"))
    row("Median length", lambda P, I: f"{st.median(p['total_seconds'] for p in P):.1f}s")
    row("Under 35s", lambda P, I: pct(sum(p['total_seconds'] < 35 for p in P), len(P)))
    row("45s or longer", lambda P, I: pct(sum(p['total_seconds'] >= 45 for p in P), len(P)))
    row(f"Top {TOP}: 45s or longer", lambda P, I: pct(sum(p['total_seconds'] >= 45 for p in P[:TOP]), min(TOP, len(P))))
    row(f"Top {TOP}: under 35s", lambda P, I: pct(sum(p['total_seconds'] < 35 for p in P[:TOP]), min(TOP, len(P))))
    row("Finder LLM calls: new / served from cache", lambda P, I: f"{I['finder_usage']['calls']} / {I['finder_usage'].get('cached', 0)}")

    # 2. Rated clips -> rank in each run
    wb = load_workbook(a.sheet, data_only=True)
    key = {r[0]: r for r in wb["key"].iter_rows(min_row=2, values_only=True) if r[0] is not None}
    source_runs = {"ai": {p["id"]: p for p in json.loads((Path(a.rated_from) / "promos_all.json").read_text(encoding="utf-8"))["ranked"]},
                   "baseline": {p["id"]: p for p in json.loads((Path(a.baseline) / "promos_all.json").read_text(encoding="utf-8"))["ranked"]}}
    rated = []
    for r in wb["1. Rate clips"].iter_rows(min_row=2, values_only=True):
        if r[0] is None or not r[5]:
            continue
        k = key[r[0]]
        src = "baseline" if k[1] == "baseline" else "ai"
        rated.append((k[3], k[1], str(r[5]).strip().lower(), source_runs[src][k[3]]))

    out += ["", "## 2. Where the clips you rated land (proxy, matched by >= 50% overlap)", "",
            "| Rated clip | Group | Length | Your verdict | Rank before | Rank after |", "|---|---|---|---|---|---|"]
    tops = {"before": [], "after": []}
    for cid, group, verdict, clip in sorted(rated, key=lambda x: -POINTS.get(x[2], 0)):
        ranks = {}
        for name, (P, _) in runs.items():
            best = max(P, key=lambda p: overlap(clip, p), default=None)
            ok = best is not None and overlap(clip, best) >= MATCH
            ranks[name] = best["rank"] if ok else None
            if ok and best["rank"] <= TOP:
                tops[name].append(POINTS.get(verdict, 0))
        out.append(f"| {cid} | {group} | {clip['total_seconds']:.0f}s | {verdict} | "
                   f"{ranks['before'] or 'not found'} | {ranks['after'] or 'not found'} |")
    out += ["", f"Rated clips that land in the top {TOP}:", ""]
    for name in ("before", "after"):
        v = tops[name]
        avg = f"{sum(v) / len(v):.2f}" if v else "n/a"
        out.append(f"- **{name}**: {len(v)} clips, {v.count(2)} Good, {v.count(0)} Bad, avg points {avg}")

    Path(a.out).write_text("\n".join(out) + "\n", encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print("\n".join(out))
    print(f"\nSaved {a.out}")


if __name__ == "__main__":
    main()
