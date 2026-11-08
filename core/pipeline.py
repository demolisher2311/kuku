"""End-to-end run: parse -> bible -> find (+repair) -> judge -> rank -> write outputs."""
from __future__ import annotations

import csv
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable

from . import finder, heuristic, pairwise
from .llm import LLM, QuotaExhausted, quota_exhausted
from .parser import Episode, load_show, guess_title
from .promo import LineIndex, Promo, excerpt
from .rank import rank, dedupe_and_number


def run(input_dir: str, out_dir: str, finder_llm: LLM | None, judge_llm: LLM | None = None,
        episodes: list[int] | None = None, per_episode: int = 4, workers: int = 2,
        title: str | None = None, log: Callable[[str], None] = print,
        judge_style: str = "pairwise") -> list[Promo]:
    """judge_style: 'pairwise' (A/B comparisons + tournament), 'strict' (one call per clip, analysis
    first) or 'classic' (batched per episode)."""
    t0 = time.time()
    out = Path(out_dir)
    (out / "raw").mkdir(parents=True, exist_ok=True)
    judge_llm = judge_llm or finder_llm

    all_eps = load_show(input_dir)
    if not all_eps:
        raise SystemExit(f"No screenplay .txt files found in {input_dir}")
    title = title or guess_title(input_dir)
    index = LineIndex(all_eps)
    by_num = {e.number: e for e in all_eps}
    targets = [e for e in all_eps if not episodes or e.number in episodes]
    mode = finder_llm.name if finder_llm else "heuristic (offline, no AI)"
    log(f"Show: {title} | {len(all_eps)} episodes parsed | running on {len(targets)} | finder: {mode}")

    # 1) Series bible (one call) so the finder knows who "LADY IN GOLD GOWN" is
    bible = finder.build_bible(finder_llm, all_eps, title)
    (out / "bible.json").write_text(json.dumps(bible, indent=2, ensure_ascii=False), encoding="utf-8")
    btxt = finder.bible_text(bible)

    # 2) Candidates per episode (parallel), validated + repaired in code
    promos: list[Promo] = []

    def work(ep: Episode) -> list[Promo]:
        if finder_llm is None:
            return heuristic.find_promos(ep, index, n=min(per_episode, 3))
        found, raw = finder.find_promos(finder_llm, ep, by_num.get(ep.number - 1), by_num.get(ep.number + 1),
                                        btxt, index, n=per_episode)
        (out / "raw" / f"ep{ep.number:02d}_find.json").write_text(
            json.dumps(raw, indent=1, ensure_ascii=False), encoding="utf-8")
        return found

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futs = {pool.submit(work, ep): ep for ep in targets}
        for k, f in enumerate(as_completed(futs), 1):
            ep = futs[f]
            try:
                got = f.result()
            except Exception as e:  # noqa: BLE001
                log(f"  ep {ep.number}: FAILED ({e})")
                continue
            ok = sum(p.valid for p in got)
            log(f"  [{k}/{len(targets)}] ep {ep.number}: {ok} valid / {len(got)} candidates")
            promos.extend(got)

    # 3) Judge valid candidates as a cold viewer (batched per episode)
    valid = [p for p in promos if p.valid]
    log(f"Judging {len(valid)} valid promos...")
    groups: dict[int, list[Promo]] = {}
    for p in valid:
        groups.setdefault(p.episode, []).append(p)

    ledger = pairwise.Ledger()

    def judge_group(ep_num: int, group: list[Promo]):
        if judge_llm is not None and judge_style == "pairwise":
            pairwise.judge_episode(judge_llm, group, index, ledger, rng_seed=ep_num)
            return
        if judge_llm is None:
            for p in group:
                heuristic.judge(p, index)
            return
        judge = finder.judge_strict if judge_style == "strict" else finder.judge_promos
        raw = judge(judge_llm, group, index)
        (out / "raw" / f"ep{ep_num:02d}_judge.json").write_text(raw, encoding="utf-8")

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futs = [pool.submit(judge_group, n, g) for n, g in sorted(groups.items())]
        for f in as_completed(futs):
            try:
                f.result()
            except Exception as e:  # noqa: BLE001
                log(f"  judge failed for a batch: {e}")

    # 4) Rank + write
    _stop_if_quota_gone()
    failed_judge_calls = 0
    if judge_llm is not None and judge_style == "pairwise":
        champs = pairwise.champions(groups, ledger)
        log(f"Swiss tournament between {len(champs)} episode champions...")
        pairwise.swiss(judge_llm, champs, index, ledger, workers=workers, log=log)
        pairwise.write_log(ledger, out / "raw" / "pairwise_judge.json")
        _stop_if_quota_gone()
        ranked = dedupe_and_number(pairwise.order(promos, champs, ledger))
        failed_judge_calls = sum(1 for e in ledger.log if e.get("error"))
        if failed_judge_calls:
            log(f"  WARNING: {failed_judge_calls} of {len(ledger.log)} comparisons failed; "
                "re-run the same command to retry them (finished ones come from the cache)")
    else:
        ranked = rank(promos)
    rejected = [p for p in promos if not p.valid]
    write_outputs(out, ranked, rejected, index, title, failed_judge_calls)
    info = {
        "show": title, "episodes_parsed": len(all_eps), "episodes_run": [e.number for e in targets],
        "finder": mode, "judge": judge_llm.name if judge_llm else "heuristic",
        "judge_style": judge_style if judge_llm else "heuristic",
        "candidates": len(promos), "valid": len(valid), "rejected": len(rejected),
        "valid_by_stage": {s: sum(p.valid and p.stage == s for p in promos)
                           for s in ("first", "autofix", "repair1", "repair2")},
        "first_try_pass_rate": f"{sum(p.stage == 'first' and p.valid for p in promos)}/"
                               f"{sum(p.stage == 'first' for p in promos)}",
        "seconds": round(time.time() - t0, 1),
        "failed_judge_calls": failed_judge_calls,
    }
    for name, llm in (("finder_usage", finder_llm), ("judge_usage", judge_llm)):
        if llm:
            u = dict(llm.usage)
            u["approx_input_tokens"] = u["in_chars"] // 4
            u["approx_output_tokens"] = u["out_chars"] // 4
            info[name] = u
            if judge_llm is finder_llm:
                break
    (out / "run_info.json").write_text(json.dumps(info, indent=2), encoding="utf-8")
    log(f"Done in {info['seconds']}s: {len(valid)} valid promos ({len(rejected)} rejected) -> {out}")
    return ranked


def _stop_if_quota_gone():
    """Never write a ranking built on a judge that could not run."""
    dead = quota_exhausted()
    if dead:
        raise QuotaExhausted(next(iter(dead.values())))


def write_outputs(out: Path, ranked: list[Promo], rejected: list[Promo], index: LineIndex, title: str,
                  failed_judge_calls: int = 0):
    # Full machine-readable dump (ranked + rejected with reasons)
    def full(p: Promo) -> dict:
        d = p.to_dict()
        d["segments_label"] = p.segments_label()
        d["script"] = excerpt(p, index) if p.segments else ""
        return d
    (out / "promos_all.json").write_text(json.dumps(
        {"show": title, "ranked": [full(p) for p in ranked], "rejected": [full(p) for p in rejected]},
        indent=1, ensure_ascii=False), encoding="utf-8")

    cols = ["rank", "id", "title", "episodes", "segments", "total_seconds", "hook", "cliffhanger", "why",
            "final_score", "hook_score", "cliffhanger_score", "standalone_score", "intensity_score",
            "clean_cut_score", "spoiler_level", "judge_verdict", "judge_confusing", "rank_reason",
            "duplicate_of", "stage", "source", "approved"]
    with open(out / "promos_ranked.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for p in ranked:
            s = p.scores
            w.writerow([p.rank, p.id, p.title, p.episodes_label(), p.segments_label(), p.total, p.hook,
                        p.cliffhanger, p.why, p.final_score, s.get("hook"), s.get("cliffhanger"),
                        s.get("standalone"), s.get("intensity"), s.get("clean_cut"), p.spoiler_level,
                        p.judge_verdict, p.judge_confusing, p.rank_reason, p.duplicate_of, p.stage, p.source, p.approved])

    # Human-readable report
    md = [f"# Promo candidates: {title}", "",
          f"{sum(not p.duplicate_of for p in ranked)} distinct promos "
          f"(+{sum(bool(p.duplicate_of) for p in ranked)} near-duplicates, {len(rejected)} rejected by the validator).", ""]
    if failed_judge_calls:
        md += [f"> **Warning:** {failed_judge_calls} judge comparisons failed, so this order is incomplete. "
               "Re-run the same command to finish them.", ""]
    for p in ranked:
        dup = f" _(near-duplicate of {p.duplicate_of})_" if p.duplicate_of else ""
        sc = ", ".join(f"{k} {v:.0f}" for k, v in p.scores.items())
        md += [f"## #{p.rank} {p.title} ({p.id}){dup}",
               f"- **Segments:** {p.segments_label()} (**{p.total:.1f}s**)",
               f"- **Hook (first 3s):** {p.hook}",
               f"- **Cliffhanger:** {p.cliffhanger}",
               f"- **Why it works:** {p.why}",
               f"- **Score {p.final_score}** ({sc}); spoiler: {p.spoiler_level}",
               f"- **Rank reason:** {p.rank_reason}",
               f"- **Cold-viewer judge:** {p.judge_verdict}"
               + (f" Confusing: {p.judge_confusing}" if p.judge_confusing else ""),
               "", "<details><summary>Script of the clip</summary>", "", "```",
               excerpt(p, index), "```", "</details>", ""]
    if rejected:
        md += ["# Rejected by the validator", ""]
        md += [f"- {p.id} \"{p.title}\": {'; '.join(p.errors)}" for p in rejected]
    (out / "promos_ranked.md").write_text("\n".join(md), encoding="utf-8")
