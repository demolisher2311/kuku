"""Build a BLIND human review sheet (Excel) to check promo quality.

Sheet 1 mixes, in random order and without saying where each clip came from:
  - ai_top   : the AI tool's top-ranked promos           -> are the best picks actually good?
  - ai_low   : random AI promos from the bottom half       -> does the ranking mean anything?
  - baseline : the keyword baseline's top promos (no AI)   -> is the AI better than simple rules?
Sheet 2 asks you to pick YOUR OWN best promo for a few episodes before looking at the tool's
output for them -> did the tool find what a human editor would pick (recall)?

Usage:
  python quality/make_sheet.py --ai outputs/openai_gpt-4.1-mini_full --baseline outputs/heuristic
Then fill quality/review_sheet.xlsx and run quality/score_sheet.py.
"""
from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation

HEAD = PatternFill("solid", fgColor="1F3A5F")
INPUT = PatternFill("solid", fgColor="FFF7D6")
WRAP_TOP = Alignment(wrap_text=True, vertical="top")
RECALL_EPISODES = [7, 16, 27, 38, 45]   # spread across the show; mix of loud and quiet episodes


def load(run_dir: str) -> list[dict]:
    d = json.loads((Path(run_dir) / "promos_all.json").read_text(encoding="utf-8"))
    return [p for p in d["ranked"] if not p.get("duplicate_of")]


def header(ws, cols: list[tuple[str, int]]):
    for i, (name, width) in enumerate(cols, 1):
        c = ws.cell(row=1, column=i, value=name)
        c.font, c.fill, c.alignment = Font(bold=True, color="FFFFFF"), HEAD, WRAP_TOP
        ws.column_dimensions[c.column_letter].width = width
    ws.freeze_panes = "A2"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ai", required=True, help="AI run folder (has promos_all.json)")
    ap.add_argument("--baseline", required=True, help="heuristic run folder")
    ap.add_argument("--out", default="quality/review_sheet.xlsx")
    ap.add_argument("--n-top", type=int, default=10)
    ap.add_argument("--n-low", type=int, default=5)
    ap.add_argument("--n-base", type=int, default=8)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--exclude-sheet", default="",
                    help="earlier review sheet: baseline clips already rated there are left out")
    ap.add_argument("--no-picks", action="store_true", help="leave out the 'your picks' sheet")
    a = ap.parse_args()
    rng = random.Random(a.seed)

    ai, base = load(a.ai), load(a.baseline)
    # Never show the recall episodes in sheet 1, so sheet 2 stays unbiased
    ai = [p for p in ai if not ({s["episode"] for s in p["segments"]} & set(RECALL_EPISODES))]
    base = [p for p in base if not ({s["episode"] for s in p["segments"]} & set(RECALL_EPISODES))]
    if a.exclude_sheet:
        from openpyxl import load_workbook
        done = {r[3] for r in load_workbook(a.exclude_sheet)["key"].iter_rows(min_row=2, values_only=True)
                if r[0] is not None and r[1] == "baseline"}
        base = [p for p in base if p["id"] not in done]
    half = len(ai) // 2
    pool = ([("ai_top", p) for p in ai[:a.n_top]]
            + [("ai_low", p) for p in rng.sample(ai[half:], max(0, min(a.n_low, len(ai) - half)))]
            + [("baseline", p) for p in base[:a.n_base]])
    rng.shuffle(pool)

    wb = Workbook()
    # ------------------------------------------------------------- instructions
    ws = wb.active
    ws.title = "Instructions"
    ws.column_dimensions["A"].width = 110
    text = [
        "PROMO QUALITY CHECK (blind)",
        "",
        "Sheet '1. Rate clips': each row is one promo clip, written as a script (what is on screen + what is said,",
        "timed from the start of the clip). Clips come from different sources and are shuffled; you are NOT told which.",
        "Imagine you are scrolling TikTok and have never seen this show. Fill the yellow cells:",
        "  Verdict: Good = would post it today | OK = usable with small changes | Bad = would not post",
        "  Hook in 3s?   Y if the first ~3 seconds would make you stop scrolling",
        "  Cliffhanger?  Y if it ends unresolved and you need to know what happens next",
        "  Makes sense?  Y if you understand who these people are and what is at stake, with no context",
        "  Clean cut?    Y if it starts and ends at sensible moments (not mid-sentence / mid-action)",
        "  Notes: why, especially for Bad. One line is enough.",
        "",
        "Sheet '2. Your picks': BEFORE opening the tool's results for these episodes, read each episode script",
        "and write down the single best promo YOU would cut: start and end time (mm:ss, e.g. 01:12), the hook",
        "and the cliffhanger. The scorer checks whether the tool found your pick.",
        "",
        "Do not open the hidden 'key' sheet until you are done. Then run:",
        f"  python quality/score_sheet.py --ai {a.ai} --baseline {a.baseline} --sheet {a.out}",
        "",
        "Time needed: about 25 min for sheet 1, 15 min for sheet 2.",
    ]
    if a.no_picks:
        text = [t for t in text if "2. Your picks" not in t and "and write down the single" not in t
                and "and the cliffhanger. The scorer" not in t]
        text[-1] = "Time needed: about 15 min."
    for i, t in enumerate(text, 1):
        ws.cell(row=i, column=1, value=t).font = Font(bold=(i == 1), size=14 if i == 1 else 11)

    # ------------------------------------------------------------- sheet 1
    s1 = wb.create_sheet("1. Rate clips")
    cols = [("Clip #", 7), ("Episode", 9), ("Timestamps in episode", 24), ("Length (s)", 9),
            ("Clip script", 90), ("Verdict", 10), ("Hook in 3s?", 9), ("Cliffhanger?", 11),
            ("Makes sense?", 11), ("Clean cut?", 9), ("Notes", 40)]
    header(s1, cols)
    verdict = DataValidation(type="list", formula1='"Good,OK,Bad"', allow_blank=True)
    yn = DataValidation(type="list", formula1='"Y,N"', allow_blank=True)
    s1.add_data_validation(verdict)
    s1.add_data_validation(yn)
    for r, (_, p) in enumerate(pool, 2):
        eps = ", ".join(sorted({str(s["episode"]) for s in p["segments"]}))
        vals = [r - 1, eps, p["segments_label"], round(p["total_seconds"], 1), p["script"]]
        for c, v in enumerate(vals, 1):
            s1.cell(row=r, column=c, value=v).alignment = WRAP_TOP
        for c in range(6, 12):
            cell = s1.cell(row=r, column=c)
            cell.fill, cell.alignment = INPUT, WRAP_TOP
        verdict.add(f"F{r}")
        yn.add(f"G{r}:J{r}")
        s1.row_dimensions[r].height = min(409, 15 * (p["script"].count("\n") + 2))

    # ------------------------------------------------------------- sheet 2
    s2 = wb.create_sheet("2. Your picks")
    if a.no_picks:
        s2.sheet_state = "hidden"   # kept (empty) so score_sheet.py reads every sheet the same way
    header(s2, [("Episode", 9), ("Your start (mm:ss)", 14), ("Your end (mm:ss)", 14),
                ("Your hook (first 3s)", 40), ("Your cliffhanger", 40), ("Notes", 40)])
    for r, ep in enumerate(RECALL_EPISODES, 2):
        s2.cell(row=r, column=1, value=ep)
        for c in range(2, 7):
            cell = s2.cell(row=r, column=c)
            cell.fill, cell.alignment = INPUT, WRAP_TOP
            if c in (2, 3):
                cell.number_format = "@"   # keep "01:12" as text, not an Excel time

    # ------------------------------------------------------------- hidden key
    key = wb.create_sheet("key")
    kcols = ["clip", "group", "source", "id", "tool_rank", "final_score", "judge_hook",
             "judge_cliffhanger", "judge_standalone", "judge_clean_cut"]
    key.append(kcols)
    for i, (group, p) in enumerate(pool, 1):
        sc = p.get("scores", {})
        key.append([i, group, p["source"], p["id"], p["rank"], p["final_score"], sc.get("hook"),
                    sc.get("cliffhanger"), sc.get("standalone"), sc.get("clean_cut")])
    key.sheet_state = "hidden"

    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    wb.save(a.out)
    counts = {g: sum(1 for x, _ in pool if x == g) for g in ("ai_top", "ai_low", "baseline")}
    print(f"Wrote {a.out}: {len(pool)} clips {counts}; your-pick episodes {RECALL_EPISODES}")


if __name__ == "__main__":
    main()
