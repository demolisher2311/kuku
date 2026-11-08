"""Promo data model + the code validator.

The LLM only names line ids. This module turns them into real timestamps (snapped
to camera-shot boundaries so an editor can cut cleanly) and checks every rule from
the brief with plain code: 20-60s, hook in the first 3 seconds, ends on the cliffhanger.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict

from .parser import Episode, Line, fmt_time

# The brief allows 20-60s. Our blind human review found clips under 35s were rated Good only
# 1 time in 8, so we enforce a stricter house minimum (still inside the brief's range).
BRIEF_MIN = 20.0
MIN_LEN, MAX_LEN = 35.0, 60.0
HOOK_WINDOW = 3.0        # hook must start within 3s of the clip start
CLIFF_TAIL = 4.0         # at most ~4s (a reaction shot) after the cliffhanger line ends
SNAP = 2.0               # snap to a camera-shot boundary if it is this close
MAX_SEGMENTS = 3


@dataclass
class Segment:
    episode: int
    start_line: str
    end_line: str
    start: float
    end: float

    @property
    def length(self) -> float:
        return self.end - self.start

    def label(self) -> str:
        return f"E{self.episode:02d} {fmt_time(self.start)}-{fmt_time(self.end)}"


@dataclass
class Promo:
    id: str
    source: str                    # which model / "heuristic"
    title: str = ""
    segments: list[Segment] = field(default_factory=list)
    hook_line: str = ""
    hook: str = ""
    cliffhanger_line: str = ""
    cliffhanger: str = ""
    why: str = ""
    standalone_note: str = ""
    spoiler_level: str = "none"
    confidence: int = 3
    stage: str = "first"           # first | autofix | repair1 | repair2 (how it became valid)
    repaired: bool = False
    errors: list[str] = field(default_factory=list)
    scores: dict = field(default_factory=dict)
    judge_verdict: str = ""
    judge_confusing: str = ""
    approved: bool | None = None   # strict judge only: total >= 22 and hook >= 7
    final_score: float = 0.0
    rank: int = 0
    duplicate_of: str = ""
    rank_reason: str = ""

    @property
    def valid(self) -> bool:
        return not self.errors

    @property
    def episode(self) -> int:
        return self.segments[0].episode if self.segments else 0

    @property
    def total(self) -> float:
        return round(sum(s.length for s in self.segments), 2)

    def episodes_label(self) -> str:
        eps = sorted({s.episode for s in self.segments})
        return ", ".join(str(e) for e in eps)

    def segments_label(self) -> str:
        return " + ".join(s.label() for s in self.segments)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["total_seconds"] = self.total
        d["valid"] = self.valid
        return d

    def raw_for_llm(self) -> dict:
        """The candidate as the LLM originally described it (for repair prompts)."""
        return {"title": self.title,
                "segments": [{"start_line": s.start_line, "end_line": s.end_line} for s in self.segments],
                "hook_line": self.hook_line, "hook": self.hook,
                "cliffhanger_line": self.cliffhanger_line, "cliffhanger": self.cliffhanger,
                "why": self.why, "standalone_note": self.standalone_note,
                "spoiler_level": self.spoiler_level, "confidence": self.confidence}


class LineIndex:
    """Global lookup: line id -> (episode, line)."""

    def __init__(self, episodes: list[Episode]):
        self.eps = {e.number: e for e in episodes}
        self.lines: dict[str, Line] = {}
        for e in episodes:
            self.lines.update(e.by_id())

    def get(self, line_id: str) -> Line | None:
        return self.lines.get(str(line_id).strip())


def _snap_start(ep: Episode, ln: Line) -> float:
    """Start of the camera shot that contains this line (if close), else the line start."""
    containing = [c for c in ep.camera_shots() if c.start <= ln.start <= c.end]
    if containing:
        shot = max(containing, key=lambda c: c.start)   # the shot on screen at that moment
        if ln.start - shot.start <= SNAP:
            return shot.start
    return ln.start


def _content_end(ep: Episode, first: Line, last: Line) -> float:
    rng = ep.lines[first.idx:last.idx + 1]
    return max([l.end for l in rng if l.kind != "camera"] + [last.end])


def _snap_end(ep: Episode, first: Line, last: Line) -> float:
    content_end = _content_end(ep, first, last)
    for c in ep.camera_shots():
        if c.start < content_end <= c.end and c.end - content_end <= SNAP:
            content_end = c.end
            break
    return min(content_end, ep.duration)


def build_promo(raw: dict, pid: str, source: str, index: LineIndex) -> Promo:
    """Turn an LLM/heuristic candidate into a Promo and validate it. Errors -> promo.errors."""
    p = Promo(id=pid, source=source,
              title=str(raw.get("title", "")).strip(),
              hook_line=str(raw.get("hook_line", "")).strip(),
              hook=str(raw.get("hook", "")).strip(),
              cliffhanger_line=str(raw.get("cliffhanger_line", "")).strip(),
              cliffhanger=str(raw.get("cliffhanger", "")).strip(),
              why=str(raw.get("why", "")).strip(),
              standalone_note=str(raw.get("standalone_note", "")).strip(),
              spoiler_level=str(raw.get("spoiler_level", "none")).strip().lower() or "none")
    try:
        p.confidence = int(raw.get("confidence", 3))
    except (TypeError, ValueError):
        p.confidence = 3
    errs = p.errors

    raw_segs = raw.get("segments") or []
    if not raw_segs:
        errs.append("no segments")
        return p
    if len(raw_segs) > MAX_SEGMENTS:
        errs.append(f"{len(raw_segs)} segments (max {MAX_SEGMENTS})")

    for s in raw_segs:
        a, b = index.get(s.get("start_line", "")), index.get(s.get("end_line", ""))
        if not a or not b:
            errs.append(f"unknown line id in segment {s}")
            continue
        if a.episode != b.episode:
            errs.append(f"segment {a.id}..{b.id} spans two episodes; split it into two segments")
            continue
        if a.idx > b.idx:
            a, b = b, a
        ep = index.eps[a.episode]
        p.segments.append(Segment(ep.number, a.id, b.id, _snap_start(ep, a), _snap_end(ep, a, b)))
    if not p.segments:
        return p

    # Merge touching segments from the same episode (an editor would not cut there)
    merged: list[Segment] = [p.segments[0]]
    for s in p.segments[1:]:
        prev = merged[-1]
        if s.episode == prev.episode and 0 <= s.start - prev.end < 0.5:
            merged[-1] = Segment(s.episode, prev.start_line, s.end_line, prev.start, s.end)
        else:
            merged.append(s)
    p.segments = merged

    for prev, cur in zip(p.segments, p.segments[1:]):
        if (cur.episode, cur.start) < (prev.episode, prev.start):
            errs.append(f"segments out of story order ({prev.label()} then {cur.label()})")
        elif cur.episode == prev.episode and cur.start < prev.end - 0.05:
            errs.append(f"segments overlap ({prev.label()} and {cur.label()})")

    first, last = p.segments[0], p.segments[-1]
    if MAX_LEN < p.total <= MAX_LEN + 3:
        # Slightly long: drop the snap-to-shot padding before rejecting (cut on the line, not the shot)
        a, b = index.get(first.start_line), index.get(last.end_line)
        first.start = a.start
        last.end = _content_end(index.eps[last.episode], index.get(last.start_line), b)

    total = p.total
    if total < MIN_LEN:
        errs.append(f"too short: {total:.1f}s (need {MIN_LEN:.0f}-{MAX_LEN:.0f}s). " + _length_options(p, index, True))
    if total > MAX_LEN:
        errs.append(f"too long: {total:.1f}s (need {MIN_LEN:.0f}-{MAX_LEN:.0f}s). " + _length_options(p, index, False))
    h = index.get(p.hook_line)
    if not h:
        errs.append(f"hook_line '{p.hook_line}' not found")
    elif h.episode != first.episode or not (first.start - 0.05 <= h.start <= first.end):
        errs.append(f"hook_line {h.id} is not inside the first segment")
    elif h.start - first.start > HOOK_WINDOW:
        errs.append(f"hook starts {h.start - first.start:.1f}s into the clip (must be <= {HOOK_WINDOW:.0f}s); "
                    f"start the first segment at or just before {h.id}")

    c = index.get(p.cliffhanger_line)
    if not c:
        errs.append(f"cliffhanger_line '{p.cliffhanger_line}' not found")
    elif c.episode != last.episode or not (last.start <= c.start <= last.end + 0.05):
        errs.append(f"cliffhanger_line {c.id} is not inside the last segment")
    elif last.end - c.end > CLIFF_TAIL:
        errs.append(f"clip runs {last.end - c.end:.1f}s past the cliffhanger (max {CLIFF_TAIL:.0f}s); "
                    f"end the last segment at {c.id}")
    return p


def _pick(lines: list[Line], k: int = 8) -> list[Line]:
    """Up to k options spread evenly, preferring dialogue."""
    pref = [l for l in lines if l.kind == "dialogue"] or lines
    if len(pref) <= k:
        return pref
    step = len(pref) / k
    return [pref[int(i * step)] for i in range(k)]


def _fmt_opt(l: Line, clip_len: float) -> str:
    return f'{l.id} (clip ~{clip_len:.0f}s) "{l.text[:45]}"'


def _length_options(p: Promo, index: LineIndex, too_short: bool) -> str:
    """Pre-computed line ids that would give a valid length, so the model picks instead of doing math."""
    first, last = p.segments[0], p.segments[-1]
    other_than_last = p.total - last.length
    ep_last = index.eps[last.episode]
    lo, hi = last.start + (MIN_LEN - other_than_last) + 3, last.start + (MAX_LEN - other_than_last) - 3
    end_opts = _pick([l for l in ep_last.lines if l.kind != "camera" and lo <= l.end <= hi])
    ends = "; ".join(_fmt_opt(l, other_than_last + l.end - last.start) for l in end_opts)
    if too_short:
        return (f"Keep the start and move the last segment's end_line / cliffhanger_line later. Options: {ends}"
                if ends else "No valid end in this episode: add a second segment or drop it.")
    other_than_first = p.total - first.length
    ep_first = index.eps[first.episode]
    lo2, hi2 = first.end - (MAX_LEN - other_than_first) + 3, first.end - (MIN_LEN - other_than_first) - 3
    start_opts = _pick([l for l in ep_first.lines if l.kind != "camera" and lo2 <= l.start <= hi2])
    starts = "; ".join(_fmt_opt(l, other_than_first + first.end - l.start) for l in start_opts)
    msg = []
    if ends:
        msg.append(f"Either keep the hook and end earlier, end_line/cliffhanger_line options: {ends}")
    if starts:
        msg.append(f"or keep the ending and start later (new hook_line = new start_line), options: {starts}")
    msg.append("or cut out the middle by splitting into 2 segments")
    return " ".join(msg)


def overlap_seconds(a: Promo, b: Promo) -> float:
    tot = 0.0
    for s in a.segments:
        for t in b.segments:
            if s.episode == t.episode:
                tot += max(0.0, min(s.end, t.end) - max(s.start, t.start))
    return tot


def excerpt(p: Promo, index: LineIndex, with_ids: bool = False) -> str:
    """The promo as a script: what is on screen / said, timed from the clip start."""
    out, cum = [], 0.0
    for k, s in enumerate(p.segments):
        if k:
            out.append(f"--- CUT to Episode {s.episode} ---")
        ep = index.eps[s.episode]
        offset = s.start - cum
        for ln in ep.lines:
            if s.start - 0.01 <= ln.start < s.end:
                out.append(ln.render(with_id=with_ids, offset=offset))
        cum += s.length
    return "\n".join(out)
