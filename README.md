# Promo Finder

Reads a microdrama screenplay (one `.txt` per episode) and finds the best **promo cuts** (35–60 s,
inside the brief's 20–60 s). Each promo opens on a hook within 3 seconds, ends on a cliffhanger, and
makes sense to a viewer who has never seen the show. For every promo you get the episode, the start
and end timestamp of each segment, the hook, the cliffhanger, a one-line reason, and a rank.

Built for the Kuku AI Generalist assignment, Problem 1 ("Find the Promos").

## How it works

```
screenplays ─► 1. PARSE (code) ─► 2. BIBLE (1 LLM call) ─► 3. FIND (LLM, per episode)
                                                                   │          ▲
                                                                   ▼          │ fails: code autofix,
                                                          4. VALIDATE (code) ─┘ then up to 2 LLM repairs
                                                                   │
   7. RANKED PROMOS ◄─ 6. RANK + DEDUPE (code) ◄─ 5. JUDGE (LLM: A/B pairs + Swiss tournament)
```

The model only proposes and compares; code enforces every rule and does the ranking.

| Step | Who | What |
|---|---|---|
| 1. Parse | code | Every camera shot, action and line of dialogue becomes a line with an id (`E03-L042`) and exact timestamps. |
| 2. Bible | LLM | One call over all loglines: who is who (e.g. which unnamed character in a scene is which named one) and which twists are spoilers. |
| 3. Find | LLM | Per episode (plus the first 60 s of the next one, for cross-episode cuts): 3–5 candidates. **The model names line ids only, never timestamps**, so timings can't be invented. |
| 4. Validate | code | Converts ids to timestamps snapped to camera-shot cuts, then checks the rules: 35–60 s, hook within the first 3 s, ends at most 4 s after the cliffhanger, at most 3 segments in story order. Failures are fixed by code where possible, else go back to the model (up to 2 rounds) with the exact error and pre-computed valid options. |
| 5. Judge | LLM | **Pairwise (default).** Sees only the clip scripts (no story context, no finder pitch). Within each episode every pair of clips is compared once, in random A/B order: which is the better promo, plus two fact checks (*is the tension resolved inside the clip? is it coherent on its own?*). Each episode's best clip then plays a 5-round Swiss tournament against the other episodes' best. `--judge-style strict` (1–10 scores per clip) and `classic` (batched, cheapest) are still available. |
| 6. Rank | code | Clips that pass both fact checks come first (episode champions by tournament points, then the rest by win rate); near-duplicates (>35% shared seconds) go to the bottom. |

An offline **`heuristic`** mode (keyword rules, no AI) runs with no key and is the baseline the AI
version has to beat.

## Results and quality

Full run on the 50-episode test show with `gemini-3.5-flash-lite` (free tier): 417 candidates,
167 valid, **85 distinct promos**, all 356 judge comparisons succeeded.

How I checked it (scripts in `quality/`, reports in `quality/*.md`):

- **Blind human review**, 2 rounds, 38 clips. `make_sheet.py` builds a sheet mixing AI picks and
  keyword-baseline picks with the source hidden; `score_sheet.py` scores it; `combine.py` pools the
  rounds into `quality_summary.md`. AI top-10 clips averaged 1.20 of 2 points, the baseline 1.38;
  the gap is weak hooks. Clips under 35 s were rarely rated Good, hence the 35 s floor.
- **Judge vs human** (`judge_eval.py`): on 136 pairs where the reviewer rated one clip Good and one
  Bad, the pairwise A/B judge picks the Good one 76% of the time, against 71% for 1–10 scores and
  64–69% for the strict per-clip judge (which gave 9+ on everything to 20 of 38 clips with
  gpt-4.1-mini). That is why pairwise is the default.
- **Comparing runs** (`compare_runs.py`): output shape and where human-rated clips land in two runs.

Known weaknesses: hooks are still the main gap; the judge picks the first-shown clip 58% of the
time inside episodes (order is randomised, so this is noise, not favouritism); the same scene cut
from two neighbouring episodes is not caught as a duplicate; the evidence is one reviewer.

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate          # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env          # macOS/Linux: cp .env.example .env
```

Then paste a key into `LLM_API_KEY` in `.env`. A free Gemini key: https://aistudio.google.com/apikey.

## Run

```bash
# quick test on 3 episodes
python run.py --input "path/to/Show-scripts" --episodes 1-3 --out outputs/test

# full show
python run.py --input "path/to/Show-scripts" --out outputs/full

# offline baseline, no AI, no key
python run.py --input "path/to/Show-scripts" --provider heuristic --out outputs/heuristic

# any other model, e.g. an OpenAI-compatible endpoint
python run.py --input ... --provider openai --base-url https://their-api/v1 --model their-model

# web UI
streamlit run app.py
```

**Free-tier limits.** A full 50-episode show takes about 490 LLM calls (~132 finder, 356 judge),
about 1.4M tokens in and 0.3M out. Gemini's free tier allows ~18 calls a minute and 500 a day per
model, so one full show uses almost a whole day's quota. If the daily quota runs out, the run stops at
once with a clear message and writes no ranking. Every finished call is cached in `.cache/`, so
re-running the same command later resumes where it stopped, and an unchanged re-run costs nothing.

## Outputs (`outputs/<run>/`)

| File | What |
|---|---|
| `promos_ranked.csv` | One row per promo: rank, segments with timestamps, hook, cliffhanger, why, scores |
| `promos_ranked.md` | Readable report, including the script of each clip |
| `promos_all.json` | Everything, including rejected candidates and why they failed |
| `bible.json` | The series bible the finder used |
| `raw/` | Unedited model responses: every find and repair, and every judge comparison (`pairwise_judge.json`) |
| `run_info.json` | Models used, counts, calls, tokens, and `failed_judge_calls` |

## Swapping the model

All model access goes through `core/llm.py`, so swapping is a config change (`.env` or CLI flags):
Gemini, Groq, OpenRouter, OpenAI, Anthropic, Ollama, or **any OpenAI-compatible endpoint** via
`--base-url`. The finder and the judge can be different models (`--judge-provider`, `--judge-model`).

## Confidentiality

The screenplays are Kuku's confidential content. `.gitignore` excludes the scripts, `data/`,
`outputs/`, the review sheets and `.env`, and no script text is in this repository. Share outputs
only through access-controlled links, and never publish them.
