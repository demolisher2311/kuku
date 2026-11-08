"""Streamlit UI: upload a show's screenplays, pick a model, get ranked promos.

Run locally:  streamlit run app.py
"""
from __future__ import annotations

import io
import json
import os
import tempfile
import zipfile
from pathlib import Path

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from core.llm import DEFAULT_MODELS, LLM, PROVIDERS
from core.pipeline import run

load_dotenv()
st.set_page_config(page_title="Promo Finder", page_icon="🎬", layout="wide")
st.title("🎬 Promo Finder")
st.caption("Reads a microdrama screenplay and finds the best 20-60s promos: hook in the first 3s, "
           "ends on a cliffhanger, makes sense to a cold viewer.")

# ----------------------------------------------------------------- sidebar: model
with st.sidebar:
    st.header("Model")
    options = PROVIDERS + ["heuristic"]
    default_p = os.getenv("LLM_PROVIDER", "gemini")
    provider = st.selectbox("Provider", options, index=options.index(default_p) if default_p in options else 0,
                            help="'heuristic' = offline keyword baseline, no AI, no key")
    model = api_key = base_url = ""
    if provider != "heuristic":
        model = st.text_input("Model", os.getenv("LLM_MODEL") if provider == default_p and os.getenv("LLM_MODEL")
                              else DEFAULT_MODELS.get(provider, ""))
        api_key = st.text_input("API key", type="password",
                                help="Left empty -> uses LLM_API_KEY from .env. Never stored.")
        base_url = st.text_input("Base URL (optional)", help="Any OpenAI-compatible endpoint")
    judge_style = st.selectbox("Judge", ["pairwise", "strict", "classic"],
                               help="pairwise: compares clips two at a time, then a tournament between episodes. "
                                    "strict: 1-10 scores per clip. classic: one batched call per episode (cheapest).")
    st.header("Run")
    ep_spec = st.text_input("Episodes", "", help="e.g. 1-5 or 1,3,7. Empty = all")
    per_ep = st.slider("Candidates per episode", 2, 6, 4)
    workers = st.slider("Parallel calls", 1, 6, 2, help="Keep low on free tiers (rate limits)")

# ----------------------------------------------------------------- input
tab_run, tab_load = st.tabs(["Run on a show", "Open previous results"])


def show_results(data: dict, key: str):
    ranked = data.get("ranked", [])
    rejected = data.get("rejected", [])
    if not ranked:
        st.warning("No valid promos.")
        return
    hide_dups = st.checkbox("Hide near-duplicates", True, key=f"{key}_dups")
    rows = [p for p in ranked if not (hide_dups and p.get("duplicate_of"))]
    df = pd.DataFrame([{
        "rank": p["rank"], "id": p["id"], "title": p["title"], "segments": p.get("segments_label", ""),
        "sec": p["total_seconds"], "score": p["final_score"],
        "hook": p["scores"].get("hook"), "cliff": p["scores"].get("cliffhanger"),
        "standalone": p["scores"].get("standalone"), "spoiler": p["spoiler_level"],
        "hook text": p["hook"], "cliffhanger text": p["cliffhanger"],
    } for p in rows])
    st.subheader(f"{len(rows)} promos, ranked")
    st.dataframe(df, use_container_width=True, hide_index=True)

    if len(rows) < 2:
        top_n = len(rows)
    else:
        top_n = st.slider("Show details for top", 1, min(30, len(rows)), min(10, len(rows)), key=f"{key}_top")
    for p in rows[:top_n]:
        with st.expander(f"#{p['rank']}  {p['title']}  ·  {p.get('segments_label', '')}  ·  "
                         f"{p['total_seconds']:.0f}s  ·  score {p['final_score']}"):
            c1, c2 = st.columns(2)
            c1.markdown(f"**Hook (first 3s):** {p['hook']}\n\n**Cliffhanger:** {p['cliffhanger']}\n\n"
                        f"**Why it works:** {p['why']}")
            c2.markdown(f"**Why this rank:** {p['rank_reason']}\n\n**Cold-viewer judge:** {p['judge_verdict']}"
                        + (f"\n\n**Might confuse:** {p['judge_confusing']}" if p.get("judge_confusing") else ""))
            st.code(p.get("script", ""), language=None)
    if rejected:
        with st.expander(f"{len(rejected)} candidates rejected by the validator"):
            for p in rejected:
                st.write(f"- **{p['id']}** {p['title']}: {'; '.join(p['errors'])}")


with tab_run:
    st.write("Upload the episode `.txt` screenplays (select all of them) or one `.zip` of the folder.")
    files = st.file_uploader("Screenplays", type=["txt", "zip"], accept_multiple_files=True)
    go = st.button("Find promos", type="primary", disabled=not files)
    if go and files:
        work = Path(tempfile.mkdtemp(prefix="promo_"))
        src = work / "scripts"
        src.mkdir()
        for f in files:
            if f.name.lower().endswith(".zip"):
                with zipfile.ZipFile(io.BytesIO(f.getvalue())) as z:
                    for m in z.namelist():
                        if m.lower().endswith(".txt") and not m.startswith("__MACOSX"):
                            (src / Path(m).name).write_bytes(z.read(m))
            else:
                (src / f.name).write_bytes(f.getvalue())

        eps = None
        if ep_spec.strip():
            from run import parse_eps
            eps = parse_eps(ep_spec.strip())
        llm = None
        if provider != "heuristic":
            llm = LLM.from_env("LLM", provider=provider, model=model or None, api_key=api_key or None,
                               base_url=base_url or None)
        logs: list[str] = []
        with st.status("Running...", expanded=True) as status:
            box = st.empty()

            def log(msg: str):
                logs.append(msg)
                box.code("\n".join(logs[-25:]), language=None)
            try:
                run(str(src), str(work / "out"), llm, llm.with_temperature(0.2) if llm else None,
                    episodes=eps, per_episode=per_ep, workers=workers, log=log, judge_style=judge_style)
                status.update(label="Done", state="complete")
            except Exception as e:  # noqa: BLE001
                status.update(label="Failed", state="error")
                st.error(str(e))
        out = work / "out"
        if (out / "promos_all.json").exists():
            st.session_state["result"] = json.loads((out / "promos_all.json").read_text(encoding="utf-8"))
            st.session_state["files"] = {n: (out / n).read_bytes()
                                         for n in ("promos_ranked.csv", "promos_ranked.md", "promos_all.json")}
    if "result" in st.session_state:
        cols = st.columns(3)
        for c, (name, data) in zip(cols, st.session_state.get("files", {}).items()):
            c.download_button(f"Download {name}", data, file_name=name)
        show_results(st.session_state["result"], "run")

with tab_load:
    runs = sorted(Path("outputs").glob("*/promos_all.json")) if Path("outputs").exists() else []
    if not runs:
        st.info("No previous runs in ./outputs (run `python run.py ...` first).")
    else:
        pick = st.selectbox("Run", runs, format_func=lambda p: p.parent.name)
        info = pick.parent / "run_info.json"
        if info.exists():
            st.json(json.loads(info.read_text(encoding="utf-8")), expanded=False)
        show_results(json.loads(pick.read_text(encoding="utf-8")), "load")
