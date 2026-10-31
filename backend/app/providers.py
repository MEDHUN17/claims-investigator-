"""AI provider chain (policy v2): Gemini REST with ROLE-BASED model chains and optional Groq fallback.

- Key(s) go ONLY in the `x-goog-api-key` header; never logged, echoed or put in a URL. Several keys are supported
  (GEMINI_API_KEY, GEMINI_API_KEY_2 ... _9): a 429 rotates to the next key before anything else.
- Roles: `reader` (extraction; cheap lite models first) and `planner` (reasoning; stronger models first).
- Per-(model,key) minimum spacing between calls (default 4 s). On 429: honour Retry-After (cap 12 s) ONCE, then move on.
- Circuit breaker: 20 s after a 429, 90 s after a timeout / 503 / other failure.
- Content-hash cache on disk (backend/storage/_cache); cached results are labelled cached=True.
- Every call returns (obj, usage) with provider, model, tokens, latency, cached.
- Failure is loud: ProviderUnavailable is raised and the pipeline degrades visibly.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import threading
import time
from pathlib import Path
from typing import Any, Callable, Optional

import httpx

GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
DEFAULT_READER_MODELS = "gemini-3.5-flash-lite,gemini-3.1-flash-lite,gemini-3-flash-preview,gemini-3.5-flash"
DEFAULT_PLANNER_MODELS = "gemini-3.6-flash,gemini-3.5-flash,gemini-3-flash-preview,gemini-3.8-flash"
DEFAULT_MODELS = DEFAULT_PLANNER_MODELS  # legacy name
ATTEMPT_TIMEOUT = 25.0
BREAKER_SECONDS = 90.0        # timeouts, 503, other failures
BREAKER_429_SECONDS = 20.0    # rate limited: the quota window is short
RETRY_AFTER_CAP = 12.0
DEFAULT_MIN_SPACING = 4.0
ROLES = ("reader", "planner")
PROMPT_VERSION = "verity-1"
BACKEND_DIR = Path(__file__).resolve().parent.parent
CACHE_DIR = BACKEND_DIR / "storage" / "_cache"


class ProviderUnavailable(Exception):
    """No provider could produce a valid answer (no key, all down, or output unusable)."""


class ProviderOutputInvalid(ProviderUnavailable):
    """A provider answered but the output failed JSON/schema validation even after one repair retry."""


# ---------- part helpers (Gemini wire format) ----------
def text_part(text: str) -> dict:
    return {"text": text}


def inline_part(data: bytes, mime: str) -> dict:
    return {"inlineData": {"mimeType": mime, "data": base64.b64encode(data).decode("ascii")}}


def _sleep(seconds: float) -> None:  # indirection so tests can run without real waiting
    if seconds > 0:
        time.sleep(seconds)


def _load_dotenv_once() -> None:
    env = BACKEND_DIR / ".env"
    if not env.exists():
        return
    try:
        from dotenv import dotenv_values
        for k, v in dotenv_values(env).items():
            if v is not None and k not in os.environ:
                os.environ[k] = v
    except Exception:  # dotenv problems must never leak values
        pass


def _scrub(msg: str) -> str:
    """Remove anything that could look like a key from an error string."""
    msg = re.sub(r"AIza[0-9A-Za-z_\-]{20,}", "[redacted]", msg)
    msg = re.sub(r"gsk_[0-9A-Za-z]{20,}", "[redacted]", msg)
    return msg[:300]


def _parse_json_text(text: str) -> Any:
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z]*\s*", "", t)
        t = re.sub(r"\s*```$", "", t)
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        # salvage the outermost object/array
        for open_c, close_c in (("{", "}"), ("[", "]")):
            i, j = t.find(open_c), t.rfind(close_c)
            if i != -1 and j > i:
                try:
                    return json.loads(t[i:j + 1])
                except json.JSONDecodeError:
                    continue
        raise


class _ModelState:
    def __init__(self, provider: str, model: str):
        self.provider, self.model = provider, model
        self.broken_until = 0.0
        self.last_error: Optional[str] = None
        self.last_latency_ms: Optional[int] = None
        self.last_ok: Optional[bool] = None
        self.key_idx = 0                       # which Gemini key this model currently uses
        self.next_ok: dict[int, float] = {}    # key index -> earliest next call start (min spacing)
        self.roles: set[str] = set()


def _split(csv: str) -> list[str]:
    return [m.strip() for m in (csv or "").split(",") if m.strip()]


class ProviderChain:
    def __init__(self, gemini_key, models: Optional[list[str]] = None, groq_key: Optional[str] = None,
                 groq_model: str = "qwen/qwen3.8-27b", cache: bool = True, client: Optional[httpx.Client] = None,
                 reader_models: Optional[list[str]] = None, planner_models: Optional[list[str]] = None,
                 min_spacing: Optional[float] = None):
        keys = [gemini_key] if isinstance(gemini_key, str) else list(gemini_key or [])
        self._gkeys = [k for k in keys if k]
        self._gkey = self._gkeys[0] if self._gkeys else None  # legacy attribute (never logged)
        self._groq_key = groq_key
        base = list(models or [])
        reader_models = list(reader_models if reader_models is not None else base)
        planner_models = list(planner_models if planner_models is not None else base)
        if min_spacing is None:
            try:
                min_spacing = float(os.environ.get("GEMINI_MIN_SPACING_SECONDS", DEFAULT_MIN_SPACING))
            except ValueError:
                min_spacing = DEFAULT_MIN_SPACING
        self.min_spacing = max(0.0, min_spacing)
        self._by_model: dict[tuple[str, str], _ModelState] = {}
        self.chains: dict[str, list[_ModelState]] = {"reader": [], "planner": []}
        for role, ms in (("reader", reader_models), ("planner", planner_models)):
            if self._gkeys:
                for m in ms:
                    self.chains[role].append(self._state("gemini", m, role))
            if groq_key:
                self.chains[role].append(self._state("groq", groq_model, role))
        self.states: list[_ModelState] = list(self._by_model.values())
        self.cache_enabled = cache
        self._client = client or httpx.Client(timeout=ATTEMPT_TIMEOUT)
        self._lock = threading.Lock()
        self.calls: list[dict] = []  # usage records, newest last (also surfaced to pipeline)

    def _state(self, provider: str, model: str, role: str) -> _ModelState:
        st = self._by_model.get((provider, model))
        if st is None:
            st = self._by_model[(provider, model)] = _ModelState(provider, model)
        st.roles.add(role)
        return st

    @classmethod
    def from_env(cls) -> "ProviderChain":
        _load_dotenv_once()
        legacy = os.environ.get("GEMINI_MODELS")  # old single list: applies to both roles unless a role list is set
        reader = _split(os.environ.get("GEMINI_READER_MODELS") or legacy or DEFAULT_READER_MODELS)
        planner = _split(os.environ.get("GEMINI_PLANNER_MODELS") or legacy or DEFAULT_PLANNER_MODELS)
        keys = [os.environ.get("GEMINI_API_KEY") or ""] + [os.environ.get(f"GEMINI_API_KEY_{i}") or "" for i in range(2, 10)]
        keys += _split(os.environ.get("GEMINI_API_KEYS", ""))
        seen, uniq = set(), []
        for k in keys:
            if k and k not in seen:
                seen.add(k)
                uniq.append(k)
        return cls(uniq, planner, os.environ.get("GROQ_API_KEY") or None, os.environ.get("GROQ_MODEL") or "qwen/qwen3.8-27b",
                   reader_models=reader, planner_models=planner)

    # ---------- health ----------
    def health(self) -> dict:
        if not self.states:
            return {"configured": False, "providers": [], "message": "AI not configured (no GEMINI_API_KEY / GROQ_API_KEY)"}
        now = time.time()
        provs = []
        for s in self.states:
            healthy = now >= s.broken_until and s.last_ok is not False
            provs.append({"name": s.provider, "model": s.model, "healthy": healthy, "role": "+".join(r for r in ROLES if r in s.roles),
                          "last_error": s.last_error or "", "last_latency_ms": s.last_latency_ms})
        any_ok = any(p["healthy"] for p in provs)
        return {"configured": True, "providers": provs, "keys": len(self._gkeys),
                "message": "AI available" if any_ok else "AI unavailable: every provider/model recently failed (circuit open)"}

    # ---------- cache ----------
    def _cache_path(self, key: str) -> Path:
        return CACHE_DIR / f"{key}.json"

    def _make_key(self, system: str, parts: list[dict], schema, temperature: float, cache_key: Optional[str]) -> str:
        h = hashlib.sha256()
        h.update(PROMPT_VERSION.encode())
        h.update((cache_key or "").encode())
        h.update(system.encode())
        for p in parts:
            if "text" in p:
                h.update(b"T" + p["text"].encode())
            elif "inlineData" in p:
                h.update(b"I" + hashlib.sha256(p["inlineData"]["data"].encode()).digest())
        h.update(json.dumps(schema, sort_keys=True).encode() if schema else b"-")
        h.update(str(temperature).encode())
        return h.hexdigest()

    # ---------- main entry ----------
    def generate_json(self, system: str, parts: list[dict], schema: Optional[dict] = None, temperature: float = 0,
                      max_tokens: int = 4096, cache_key: Optional[str] = None,
                      validate: Optional[Callable[[Any], Any]] = None, timeout: Optional[float] = None,
                      role: str = "planner") -> tuple[Any, dict]:
        """Return (obj, usage). `validate` (optional) raises on a schema violation -> one repair retry.
        `role` picks the model chain: "reader" (extraction, lite models first) or "planner"."""
        chain = self.chains.get(role) or self.chains["planner"]
        if not chain:
            raise ProviderUnavailable("AI not configured (no provider key)")
        key = self._make_key(system, parts, schema, temperature, cache_key)
        if self.cache_enabled:
            try:
                p = self._cache_path(key)
                if p.exists():
                    rec = json.loads(p.read_text(encoding="utf-8"))
                    obj = rec["obj"]
                    if validate:
                        obj = validate(obj)
                    usage = dict(rec["usage"], cached=True, latency_ms=0, role=role, fallbacks=[])
                    self._record(usage)
                    return obj, usage
            except Exception:
                pass  # corrupt cache entry: ignore and call the model

        errors: list[str] = []
        now = time.time()
        candidates = [s for s in chain if now >= s.broken_until]
        if not candidates:
            raise ProviderUnavailable("all providers/models are in circuit-breaker cooldown: " +
                                      "; ".join(f"{s.model}: {s.last_error}" for s in chain))
        t_start = time.time()
        budget = 2.0 * (timeout or ATTEMPT_TIMEOUT)  # total wall-clock for one logical call across all fallbacks (a saturated quota must not stall a case for minutes)
        for i, st in enumerate(candidates):
            left = budget - (time.time() - t_start)
            if i > 0 and left <= 3:
                errors.append(f"time budget of {budget:.0f}s exhausted before {st.model}")
                break
            try:
                obj, usage = self._call_with_repair(st, system, parts, schema, temperature, max_tokens, validate,
                                                    min(timeout or ATTEMPT_TIMEOUT, max(left, 5.0)), more=i < len(candidates) - 1)
            except ProviderUnavailable as e:
                errors.append(f"{st.model}: {e}")
                continue
            if self.cache_enabled:
                try:
                    CACHE_DIR.mkdir(parents=True, exist_ok=True)
                    self._cache_path(key).write_text(json.dumps({"obj": obj, "usage": usage}), encoding="utf-8")
                except Exception:
                    pass
            usage = dict(usage, role=role, fallbacks=errors[:6])
            self._record(usage)
            return obj, dict(usage, cached=False)
        raise ProviderUnavailable("; ".join(errors)[:600])

    def _record(self, usage: dict) -> None:
        with self._lock:
            self.calls.append(usage)

    def _call_with_repair(self, st, system, parts, schema, temperature, max_tokens, validate, timeout=None, more=False):
        total_in = total_out = 0
        t0 = time.time()
        sys_prompt = system
        cur_parts = parts
        last_err = "no output"
        budget = max_tokens
        for attempt in range(2):  # original + one repair
            text, tin, tout, finish = self._raw_call(st, sys_prompt, cur_parts, temperature, budget, timeout, more)
            total_in += tin
            total_out += tout
            try:
                if finish in ("MAX_TOKENS", "length"):
                    raise ValueError("output truncated (hit max tokens)")
                if not text.strip():
                    raise ValueError("empty output")
                obj = _parse_json_text(text)
                if validate:
                    obj = validate(obj)
                usage = {"provider": st.provider, "model": st.model, "tokens_in": total_in, "tokens_out": total_out,
                         "latency_ms": int((time.time() - t0) * 1000), "cached": False}
                st.last_ok = True
                st.last_error = None
                st.last_latency_ms = usage["latency_ms"]
                return obj, usage
            except Exception as e:  # parse / validation failure -> repair retry
                last_err = _scrub(f"{type(e).__name__}: {e}")
                if "truncated" in last_err:
                    budget = min(budget * 2, 16000)  # truncation: retry with a bigger output budget
                if attempt == 0:
                    cur_parts = list(parts) + [text_part(
                        "REPAIR: your previous answer was rejected (" + last_err + "). Return ONLY one complete valid "
                        "JSON object matching the required shape. Keep every string short; no markdown fences.")]
        st.last_ok = False
        st.last_error = last_err
        raise ProviderOutputInvalid(f"output invalid after repair retry ({last_err})")

    # ---------- transport ----------
    def _raw_call(self, st: _ModelState, system, parts, temperature, max_tokens, timeout=None, more=False) -> tuple[str, int, int, str]:
        if st.provider == "gemini":
            return self._gemini(st, system, parts, temperature, max_tokens, timeout, more)
        return self._groq(st, system, parts, temperature, max_tokens, timeout)

    def _fail(self, st: _ModelState, msg: str, seconds: float = BREAKER_SECONDS) -> None:
        st.broken_until = time.time() + seconds
        st.last_ok = False
        st.last_error = _scrub(msg)

    def _space(self, st: _ModelState, kidx: int) -> None:
        """Reserve the next call slot for (model, key) and sleep until it opens (min spacing between calls)."""
        if self.min_spacing <= 0:
            return
        with self._lock:
            now = time.time()
            start = max(now, st.next_ok.get(kidx, 0.0))
            st.next_ok[kidx] = start + self.min_spacing
        _sleep(start - now)

    @staticmethod
    def _retry_after(r) -> float:
        raw = r.headers.get("retry-after")
        if raw is None:
            m = re.search(r'"retryDelay"\s*:\s*"([\d.]+)s"', r.text or "")
            raw = m.group(1) if m else "2"
        try:
            return min(max(float(raw), 0.0), RETRY_AFTER_CAP)
        except ValueError:
            return 2.0

    def _gemini(self, st, system, parts, temperature, max_tokens, timeout=None, more=False):
        tmo = timeout or ATTEMPT_TIMEOUT
        url = f"{GEMINI_BASE}/{st.model}:generateContent"
        level = os.environ.get("GEMINI_THINKING_LEVEL", "low")
        n_keys = max(1, len(self._gkeys))
        rotations, waited, thinking_retry = 0, False, False
        for _ in range(2 * n_keys + 4):  # bounded: thinking fallback + key rotations + one Retry-After wait
            kidx = st.key_idx % n_keys
            headers = {"x-goog-api-key": (self._gkeys[kidx] if self._gkeys else ""), "content-type": "application/json"}
            gen = {"responseMimeType": "application/json", "temperature": temperature, "maxOutputTokens": max_tokens}
            if level != "off" and getattr(st, "thinking_ok", True):
                gen["thinkingConfig"] = {"thinkingLevel": level}  # keeps latency inside the attempt budget
            body = {"systemInstruction": {"parts": [{"text": system}]}, "contents": [{"role": "user", "parts": parts}], "generationConfig": gen}
            self._space(st, kidx)
            t0 = time.time()
            try:
                r = self._client.post(url, json=body, headers=headers, timeout=tmo)
            except httpx.TimeoutException:
                self._fail(st, f"timeout after {tmo:.0f}s")
                raise ProviderUnavailable(f"timeout after {tmo:.0f}s")
            except httpx.HTTPError as e:
                self._fail(st, f"transport error {type(e).__name__}")
                raise ProviderUnavailable(f"transport error {type(e).__name__}")
            if r.status_code == 400 and "thinking" in r.text.lower() and "thinkingConfig" in gen and not thinking_retry:
                st.thinking_ok = False  # this model does not accept the field: retry once without it, no breaker trip
                thinking_retry = True
                continue
            if r.status_code == 429:
                if rotations < n_keys - 1:  # another key (other project) may still have quota: no waiting
                    rotations += 1
                    st.key_idx = (kidx + 1) % n_keys
                    continue
                if not waited and not more:  # another model is still untried: go there now instead of sleeping (waiting only on the last resort)
                    waited = True
                    _sleep(self._retry_after(r))
                    continue
                self._fail(st, "HTTP 429 (rate limited) after Retry-After", BREAKER_429_SECONDS)
                raise ProviderUnavailable("HTTP 429")
            if r.status_code != 200:
                self._fail(st, f"HTTP {r.status_code}: {_scrub(r.text)}")  # 503 and friends: move on, breaker 90 s
                raise ProviderUnavailable(f"HTTP {r.status_code}")
            try:
                j = r.json()
                cand = (j.get("candidates") or [{}])[0]
                txt = "".join(p.get("text", "") for p in (cand.get("content", {}).get("parts") or []) if not p.get("thought"))
                um = j.get("usageMetadata", {})
                st.last_latency_ms = int((time.time() - t0) * 1000)
                return txt, int(um.get("promptTokenCount", 0)), int(um.get("candidatesTokenCount", 0)) + int(um.get("thoughtsTokenCount", 0)), cand.get("finishReason", "")
            except Exception:
                self._fail(st, "bad response shape")
                raise ProviderUnavailable("bad response shape")
        self._fail(st, "HTTP 429 after retries", BREAKER_429_SECONDS)
        raise ProviderUnavailable("HTTP 429 after retries")

    def _groq(self, st, system, parts, temperature, max_tokens, timeout=None):
        content: list[dict] = []
        n_img = 0
        for p in parts:
            if "text" in p:
                content.append({"type": "text", "text": p["text"]})
            elif "inlineData" in p and p["inlineData"]["mimeType"].startswith("image/") and n_img < 3:
                n_img += 1
                content.append({"type": "image_url", "image_url": {"url": f"data:{p['inlineData']['mimeType']};base64,{p['inlineData']['data']}"}})
        body = {"model": st.model, "temperature": temperature, "max_tokens": max_tokens,
                "response_format": {"type": "json_object"},
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": content}]}
        t0 = time.time()
        try:
            r = self._client.post("https://api.groq.com/openai/v1/chat/completions", json=body,
                                  headers={"authorization": f"Bearer {self._groq_key}"}, timeout=ATTEMPT_TIMEOUT)
        except httpx.HTTPError as e:
            self._fail(st, f"transport error {type(e).__name__}")
            raise ProviderUnavailable(f"transport error {type(e).__name__}")
        if r.status_code != 200:
            self._fail(st, f"HTTP {r.status_code}")
            raise ProviderUnavailable(f"HTTP {r.status_code}")
        j = r.json()
        ch = (j.get("choices") or [{}])[0]
        um = j.get("usage", {})
        st.last_latency_ms = int((time.time() - t0) * 1000)
        return ch.get("message", {}).get("content", "") or "", int(um.get("prompt_tokens", 0)), int(um.get("completion_tokens", 0)), ch.get("finish_reason", "")
