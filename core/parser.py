"""Parse Kuku screenplay .txt files into structured, timestamped lines.

Pure code, no AI: timestamps come straight from the script, so they can never
be hallucinated. Every line gets a stable id like "E01-L023" that the LLM uses
to point at moments; we map ids back to timestamps ourselves.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

TIME_RE = r"(\d{1,2}):(\d{2}(?:\.\d+)?)"
BLOCK_HEAD_RE = re.compile(r"^\*\*(.+?):?\*\*\s*$")
START_END_RE = re.compile(rf"^Start:\s*\({TIME_RE}\)\s*\|\s*End:\s*\({TIME_RE}\)", re.I)
SCENE_RE = re.compile(r"^SCENE\s+(\d+)", re.I)
SCENE_HEADING_RE = re.compile(r"^Scene heading:\s*(.+)$", re.I)
EP_NUM_RE = re.compile(r"^EPISODE NUMBER:\s*Episode\s*(\d+)", re.I)
LOGLINE_RE = re.compile(r"^EPISODE LOGLINE:\s*(.+)$", re.I)
CONTINUITY_RE = re.compile(r"^CONTINUITY NOTES:\s*(.+)$", re.I)


def to_seconds(mm: str, ss: str) -> float:
    return int(mm) * 60 + float(ss)


def fmt_time(sec: float) -> str:
    m, s = divmod(max(sec, 0.0), 60)
    return f"{int(m):02d}:{s:05.2f}"


@dataclass
class Line:
    id: str            # e.g. "E01-L023"
    episode: int
    idx: int           # position within the episode
    scene: int
    kind: str          # camera | action | dialogue | sfx
    start: float       # seconds from episode start
    end: float
    text: str
    speaker: str = ""  # dialogue only
    tone: str = ""     # e.g. "Cold, Commanding" / "Off-screen"

    def render(self, with_id: bool = True, offset: float | None = None) -> str:
        """One-line representation for prompts. offset -> times relative to promo start."""
        if offset is None:
            t = f"{fmt_time(self.start)}-{fmt_time(self.end)}"
        else:
            t = f"+{self.start - offset:04.1f}s"
        head = f"[{self.id} {t}]" if with_id else f"[{t}]"
        if self.kind == "dialogue":
            tone = f" ({self.tone})" if self.tone else ""
            return f"{head} {self.speaker}{tone}: {self.text}"
        tag = {"camera": "CAM", "action": "ACTION", "sfx": "SFX"}.get(self.kind, self.kind.upper())
        return f"{head} {tag}: {self.text}"


@dataclass
class Episode:
    number: int
    logline: str
    continuity: str
    duration: float
    lines: list[Line] = field(default_factory=list)
    scenes: dict[int, str] = field(default_factory=dict)
    source: str = ""

    def by_id(self) -> dict[str, Line]:
        return {ln.id: ln for ln in self.lines}

    def camera_shots(self) -> list[Line]:
        return [ln for ln in self.lines if ln.kind == "camera"]


def _classify(head: str) -> tuple[str, str, str]:
    """Map a **HEADER:** label to (kind, speaker, tone)."""
    h = head.strip().rstrip(":").strip()
    up = h.upper()
    if up == "CAMERA":
        return "camera", "", ""
    if up == "ACTION":
        return "action", "", ""
    if up.startswith("SOUND"):
        return "sfx", "", ""
    # Dialogue: "LADY ANNE (Confused, Breathless)" or "X (O.S.) (Firm)"
    tones = re.findall(r"\(([^)]*)\)", h)
    speaker = re.sub(r"\([^)]*\)", "", h).strip()
    return "dialogue", speaker, ", ".join(t.strip() for t in tones if t.strip())


def parse_text(text: str, source: str = "", fallback_number: int = 0) -> Episode:
    rows = text.splitlines()
    number, logline, continuity = fallback_number, "", ""
    lines: list[Line] = []
    scenes: dict[int, str] = {}
    scene = 0
    i = 0
    while i < len(rows):
        row = rows[i].strip()
        if m := EP_NUM_RE.match(row):
            number = int(m.group(1))
        elif m := LOGLINE_RE.match(row):
            logline = m.group(1).strip()
        elif m := CONTINUITY_RE.match(row):
            continuity = m.group(1).strip()
        elif m := SCENE_RE.match(row):
            scene = int(m.group(1))
        elif m := SCENE_HEADING_RE.match(row):
            scenes[scene] = m.group(1).strip()
        elif m := BLOCK_HEAD_RE.match(row):
            kind, speaker, tone = _classify(m.group(1))
            # Next non-empty row should be the Start/End timing
            j = i + 1
            while j < len(rows) and not rows[j].strip():
                j += 1
            tm = START_END_RE.match(rows[j].strip()) if j < len(rows) else None
            if tm:
                start = to_seconds(tm.group(1), tm.group(2))
                end = to_seconds(tm.group(3), tm.group(4))
                # Body: following rows until blank line or next header
                body = []
                k = j + 1
                while k < len(rows) and rows[k].strip() and not BLOCK_HEAD_RE.match(rows[k].strip()):
                    body.append(rows[k].strip())
                    k += 1
                txt = " ".join(body).strip()
                if kind == "dialogue":
                    txt = txt.strip('"“”')
                lines.append(Line(id="", episode=0, idx=len(lines), scene=scene, kind=kind,
                                  start=start, end=max(end, start), text=txt,
                                  speaker=speaker, tone=tone))
                i = k
                continue
        i += 1

    # Stable order by start time (the script is already ~ordered; keep ties stable)
    lines.sort(key=lambda l: (l.start, l.idx))
    for n, ln in enumerate(lines):
        ln.idx = n
        ln.episode = number
        ln.id = f"E{number:02d}-L{n:03d}"
    duration = max((l.end for l in lines), default=0.0)
    return Episode(number=number, logline=logline, continuity=continuity,
                   duration=duration, lines=lines, scenes=scenes, source=source)


def parse_file(path: str | Path) -> Episode:
    p = Path(path)
    m = re.search(r"episode-(\d+)", p.name, re.I)
    fallback = int(m.group(1)) if m else 0
    return parse_text(p.read_text(encoding="utf-8", errors="replace"), source=p.name,
                      fallback_number=fallback)


def load_show(folder: str | Path) -> list[Episode]:
    """Load every episode .txt in a folder (searches subfolders too)."""
    files = sorted(Path(folder).rglob("*.txt"))
    eps = [parse_file(f) for f in files]
    eps = [e for e in eps if e.lines]
    eps.sort(key=lambda e: e.number)
    return eps


def guess_title(folder: str | Path) -> str:
    """Show title from the folder name, e.g. '<Title>-scripts (2)' -> '<Title>'."""
    p = Path(folder)
    subdirs = [d for d in p.iterdir() if d.is_dir()] if p.is_dir() else []
    name = subdirs[0].name if len(subdirs) == 1 else p.name
    return re.sub(r"-scripts.*$", "", name).strip()


if __name__ == "__main__":
    import sys
    eps = load_show(sys.argv[1])
    total = sum(len(e.lines) for e in eps)
    print(f"{len(eps)} episodes, {total} lines")
    for e in eps[:3]:
        print(e.number, f"{e.duration:.1f}s", len(e.lines), "lines |", e.logline[:80])
        for ln in e.lines[:4]:
            print("   ", ln.render()[:140])
