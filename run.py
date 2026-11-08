"""Command-line entry point.

Examples
  python run.py --input "path/to/show-scripts" --out outputs/gemini
  python run.py --input "path/to/show-scripts" --episodes 1-5          # quick test
  python run.py --input "path/to/show-scripts" --provider heuristic   # offline, no AI
  python run.py --input ... --provider openai --base-url https://your-gateway/v1 --model your-model
"""
from __future__ import annotations

import argparse

from dotenv import load_dotenv

from core.llm import LLM, PROVIDERS, QuotaExhausted
from core.pipeline import run


def parse_eps(spec: str | None) -> list[int] | None:
    if not spec:
        return None
    out: list[int] = []
    for part in spec.split(","):
        if "-" in part:
            a, b = part.split("-")
            out += list(range(int(a), int(b) + 1))
        else:
            out.append(int(part))
    return out


def main():
    load_dotenv()
    ap = argparse.ArgumentParser(description="Find the best 20-60s promos in a microdrama screenplay.")
    ap.add_argument("--input", required=True, help="folder with episode .txt screenplays")
    ap.add_argument("--out", default="outputs/run", help="output folder")
    ap.add_argument("--provider", help=f"{', '.join(PROVIDERS)} or 'heuristic' (default: LLM_PROVIDER in .env)")
    ap.add_argument("--model", help="model name (default: LLM_MODEL in .env or provider default)")
    ap.add_argument("--base-url", help="OpenAI-compatible base URL (for any custom API)")
    ap.add_argument("--judge-provider", help="use a different provider for the judge")
    ap.add_argument("--judge-model", help="use a different model for the judge")
    ap.add_argument("--judge-style", choices=["pairwise", "strict", "classic"], default=None,
                    help="pairwise = A/B comparisons + tournament (default); strict = 1-10 scores per clip; "
                         "classic = batched, lenient")
    ap.add_argument("--episodes", help="e.g. 1-5 or 1,3,7 (default: all)")
    ap.add_argument("--per-episode", type=int, default=4, help="candidates to ask for per episode")
    ap.add_argument("--workers", type=int, default=2, help="parallel LLM calls (keep low on free tiers)")
    ap.add_argument("--title", help="show title (default: from folder name)")
    a = ap.parse_args()

    import os
    provider = a.provider or os.getenv("LLM_PROVIDER", "gemini")
    if provider == "heuristic":
        finder_llm = judge_llm = None
    else:
        finder_llm = LLM.from_env("LLM", provider=provider, model=a.model, base_url=a.base_url)
        if a.judge_provider or a.judge_model or os.getenv("JUDGE_PROVIDER") or os.getenv("JUDGE_MODEL"):
            judge_llm = LLM.from_env("JUDGE", provider=a.judge_provider or os.getenv("JUDGE_PROVIDER") or provider,
                                     model=a.judge_model, temperature=0.2)
        else:
            judge_llm = finder_llm.with_temperature(0.2)

    try:
        run(a.input, a.out, finder_llm, judge_llm, episodes=parse_eps(a.episodes),
            per_episode=a.per_episode, workers=a.workers, title=a.title,
            judge_style=a.judge_style or os.getenv("JUDGE_STYLE", "pairwise"))
    except QuotaExhausted as e:
        print(f"\nSTOPPED: {e}")
        raise SystemExit(2)


if __name__ == "__main__":
    main()
