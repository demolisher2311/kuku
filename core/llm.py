"""One tiny adapter for every LLM provider, so the model is a config change.

Supported providers (all over plain HTTPS with `requests`, no SDK lock-in):
  gemini      Google AI Studio (free tier)        key: https://aistudio.google.com/apikey
  groq        Groq (free tier, OpenAI-compatible) key: https://console.groq.com/keys
  openrouter  OpenRouter (has free models)
  openai      OpenAI, or ANY OpenAI-compatible API (set LLM_BASE_URL, e.g. Kuku's own gateway)
  anthropic   Anthropic Messages API
  ollama      Local model via Ollama (no key)

Responses are cached on disk (keyed by provider+model+prompt) so re-runs are free
and a crashed run resumes where it stopped.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

import requests

DEFAULT_MODELS = {
    "gemini": "gemini-3.5-flash-lite",
    "groq": "llama-3.3-70b-versatile",
    "openrouter": "meta-llama/llama-3.3-70b-instruct:free",
    "openai": "gpt-4.1-mini",
    "anthropic": "claude-haiku-5-5",
    "ollama": "llama3.1",
}
DEFAULT_BASE_URLS = {
    "groq": "https://api.groq.com/openai/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "openai": "https://api.openai.com/v1",
    "ollama": "http://localhost:11434/v1",
}
KEY_ENV = {"gemini": "GEMINI_API_KEY", "groq": "GROQ_API_KEY", "openrouter": "OPENROUTER_API_KEY",
           "openai": "OPENAI_API_KEY", "anthropic": "ANTHROPIC_API_KEY"}
PROVIDERS = list(DEFAULT_MODELS)


class LLMError(RuntimeError):
    pass


class QuotaExhausted(LLMError):
    """The provider's DAILY quota is used up: retrying is pointless until it resets."""


_DEAD: dict[str, str] = {}   # model name -> quota message; later calls fail fast, no HTTP request


def quota_exhausted() -> dict[str, str]:
    return dict(_DEAD)


def _quota_info(r) -> tuple[str, float | None]:
    """From a 429 body: (daily quota id or '', suggested retry delay in seconds)."""
    try:
        details = r.json().get("error", {}).get("details", [])
    except ValueError:
        return "", None
    daily, delay = "", None
    for d in details:
        for v in d.get("violations", []) or []:
            if "PerDay" in str(v.get("quotaId", "")):
                daily = f"{v.get('quotaId')} = {v.get('quotaValue')}"
        m = re.fullmatch(r"(\d+(?:\.\d+)?)s", str(d.get("retryDelay", "")))
        if m:
            delay = float(m.group(1))
    return daily, delay


class _Retryable(Exception):
    def __init__(self, msg, retry_after=None):
        super().__init__(msg)
        self.retry_after = retry_after


@dataclass
class LLM:
    provider: str = "gemini"
    model: str = ""
    api_key: str = ""
    base_url: str = ""
    temperature: float = 0.4
    cache_dir: str = ".cache/llm"
    max_retries: int = 6
    usage: dict = field(default_factory=lambda: {"calls": 0, "cached": 0, "in_chars": 0, "out_chars": 0})

    def __post_init__(self):
        self.model = self.model or DEFAULT_MODELS.get(self.provider, "")
        self.base_url = self.base_url or DEFAULT_BASE_URLS.get(self.provider, "")
        self.api_key = self.api_key or os.getenv(KEY_ENV.get(self.provider, "_none_"), "")
        self._lock = threading.Lock()
        self._unsupported: set[str] = set()

    @classmethod
    def from_env(cls, prefix: str = "LLM", **overrides) -> "LLM":
        """Build from env vars: LLM_PROVIDER / LLM_MODEL / LLM_API_KEY / LLM_BASE_URL.
        prefix="JUDGE" configures a separate judge model (falls back to LLM_*)."""
        provider = (overrides.get("provider") or os.getenv(f"{prefix}_PROVIDER")
                    or os.getenv("LLM_PROVIDER") or "gemini")
        same_as_main = provider == (os.getenv("LLM_PROVIDER") or "gemini")

        def pick(name):
            v = overrides.get(name.lower()) or os.getenv(f"{prefix}_{name}")
            if not v and same_as_main:          # only inherit LLM_* settings for the same provider
                v = os.getenv(f"LLM_{name}")
            return v or ""
        llm = cls(provider=provider, model=pick("MODEL"), api_key=pick("API_KEY"), base_url=pick("BASE_URL"))
        if overrides.get("temperature") is not None:
            llm.temperature = overrides["temperature"]
        return llm

    def with_temperature(self, t: float) -> "LLM":
        """Same model and key, different temperature, its own usage counter."""
        return LLM(self.provider, self.model, self.api_key, self.base_url, t, self.cache_dir, self.max_retries)

    @property
    def name(self) -> str:
        return f"{self.provider}:{self.model}"

    # ------------------------------------------------------------------ public
    def json(self, system: str, user: str) -> tuple[dict, str]:
        """Ask for a JSON object. Returns (parsed_json, raw_text)."""
        raw = self.complete(system, user, want_json=True)
        try:
            return parse_json(raw), raw
        except ValueError:
            fix = self.complete(system, user + "\n\nYour previous reply was not valid JSON. "
                                "Reply again with ONLY the JSON object, no prose, no code fences.",
                                want_json=True)
            return parse_json(fix), fix

    def complete(self, system: str, user: str, want_json: bool = False) -> str:
        key = hashlib.sha256(json.dumps([self.provider, self.model, self.temperature, system, user,
                                         want_json]).encode()).hexdigest()[:32]
        cpath = Path(self.cache_dir) / f"{key}.json"
        if cpath.exists():
            with self._lock:
                self.usage["cached"] += 1
            return json.loads(cpath.read_text(encoding="utf-8"))["text"]
        if getattr(self, "cache_only", False):
            raise LLMError(f"{self.name}: not in cache (cache-only mode, no API call made)")
        if self.name in _DEAD:
            raise QuotaExhausted(_DEAD[self.name])

        text = self._with_retries(lambda: self._call(system, user, want_json))
        with self._lock:
            self.usage["calls"] += 1
            self.usage["in_chars"] += len(system) + len(user)
            self.usage["out_chars"] += len(text)
        cpath.parent.mkdir(parents=True, exist_ok=True)
        cpath.write_text(json.dumps({"model": self.name, "text": text}), encoding="utf-8")
        return text

    # ----------------------------------------------------------------- private
    def _with_retries(self, fn):
        delay = 5.0
        for _ in range(self.max_retries):
            try:
                return fn()
            except _Retryable as e:
                wait = e.retry_after or delay
                print(f"    [{self.name}] {e} -> retrying in {wait:.0f}s", flush=True)
                time.sleep(wait)
                delay = min(delay * 2, 90)
        raise LLMError(f"{self.name}: gave up after {self.max_retries} retries")

    def _call(self, system: str, user: str, want_json: bool) -> str:
        if self.provider == "gemini":
            return self._gemini(system, user, want_json)
        if self.provider == "anthropic":
            return self._anthropic(system, user)
        if self.base_url:
            return self._openai_compatible(system, user, want_json)
        raise LLMError(f"Unknown provider '{self.provider}' (set LLM_BASE_URL for OpenAI-compatible APIs)")

    def _post(self, url, headers, payload):
        try:
            r = requests.post(url, headers=headers, json=payload, timeout=240)
        except requests.RequestException as e:
            raise _Retryable(f"network error: {e}")
        if r.status_code == 429:
            daily, delay = _quota_info(r)
            if daily:
                when = f" It resets in about {delay / 60:.0f} min." if delay else ""
                msg = (f"{self.name}: daily quota used up ({daily}).{when} Every finished call is cached, "
                       "so re-running the same command later resumes where this stopped.")
                _DEAD[self.name] = msg
                raise QuotaExhausted(msg)
            ra = r.headers.get("retry-after", "")
            raise _Retryable("HTTP 429", float(ra) if re.fullmatch(r"\d+(\.\d+)?", ra) else delay)
        if r.status_code in (500, 502, 503, 504):
            raise _Retryable(f"HTTP {r.status_code}")
        if r.status_code >= 400:
            raise LLMError(f"{self.name} HTTP {r.status_code}: {r.text[:400]}")
        return r.json()

    def _gemini(self, system, user, want_json):
        if not self.api_key:
            raise LLMError("No Gemini key. Put LLM_API_KEY in .env (free at https://aistudio.google.com/apikey).")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        cfg = {"temperature": self.temperature}
        if want_json:
            cfg["responseMimeType"] = "application/json"
        data = self._post(url, {"x-goog-api-key": self.api_key, "Content-Type": "application/json"}, {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": cfg,
        })
        um = data.get("usageMetadata", {}) or {}
        self._tokens(um.get("promptTokenCount", 0), um.get("candidatesTokenCount", 0),
                     um.get("thoughtsTokenCount", 0))
        try:
            parts = data["candidates"][0]["content"]["parts"]
            return "".join(p.get("text", "") for p in parts if not p.get("thought"))
        except (KeyError, IndexError):
            raise LLMError(f"Gemini returned no text: {json.dumps(data)[:400]}")

    def _tokens(self, tin: int, tout: int, think: int = 0):
        """Real token counts reported by the API (thinking tokens are billed as output)."""
        with self._lock:
            for k, v in (("tokens_in", tin), ("tokens_out", tout), ("tokens_thinking", think)):
                self.usage[k] = self.usage.get(k, 0) + int(v or 0)

    def _openai_compatible(self, system, user, want_json):
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        payload = {"model": self.model,
                   "messages": [{"role": "system", "content": system},
                                {"role": "user", "content": user}]}
        if "temperature" not in self._unsupported:
            payload["temperature"] = self.temperature
        if want_json and self.provider != "ollama" and "response_format" not in self._unsupported:
            payload["response_format"] = {"type": "json_object"}
        url = self.base_url.rstrip("/") + "/chat/completions"
        try:
            data = self._post(url, headers, payload)
        except LLMError as e:
            # Some models (e.g. reasoning models) reject temperature / JSON mode: drop it and retry once.
            msg = str(e).lower()
            dropped = [p for p in ("temperature", "response_format") if p in payload and p in msg]
            if not dropped:
                raise
            for p in dropped:
                self._unsupported.add(p)
                payload.pop(p)
            data = self._post(url, headers, payload)
        u = data.get("usage", {}) or {}
        self._tokens(u.get("prompt_tokens", 0), u.get("completion_tokens", 0),
                     (u.get("completion_tokens_details") or {}).get("reasoning_tokens", 0))
        return data["choices"][0]["message"]["content"] or ""

    def _anthropic(self, system, user):
        base = self.base_url or "https://api.anthropic.com"
        data = self._post(base.rstrip("/") + "/v1/messages",
                          {"x-api-key": self.api_key, "anthropic-version": "2023-06-01",
                           "content-type": "application/json"},
                          {"model": self.model, "max_tokens": 8000, "temperature": self.temperature,
                           "system": system, "messages": [{"role": "user", "content": user}]})
        return "".join(b.get("text", "") for b in data.get("content", []))


def parse_json(text: str) -> dict:
    """Tolerant JSON extraction: strips code fences / leading prose."""
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.S)
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        pass
    start, end = t.find("{"), t.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(t[start:end + 1])
        except json.JSONDecodeError:
            pass
    raise ValueError("Model did not return valid JSON")
