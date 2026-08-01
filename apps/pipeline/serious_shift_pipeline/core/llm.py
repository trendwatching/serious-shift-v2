"""
Anthropic client + robust JSON parsing, shared by the extraction/generation steps.

Two ways to call Claude:

  call(req)         one request, synchronously.
  call_batch(reqs)  many requests through the Batch API — **half price**, at the
                    cost of latency (minutes to hours). The weekly cron is
                    entirely latency-insensitive, so every bulk phase uses it.

Requests are values (`Req`) rather than positional arguments, so the same object
can go down either path unchanged.

Retries are left to the SDK, which already retries 429/5xx with exponential
backoff. The hand-rolled loop this replaced ran *on top* of that (4-6 attempts,
flat 5s sleep, no jitter) over a bare `except Exception` — so a malformed prompt
was billed several times before failing.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field

from .config import EXTRACTION_MODEL

# Above this the SDK refuses a non-streaming request that could outlive its
# 10-minute ceiling. Below it, skip streaming: a plain create() is what the
# Batch API accepts, and it is one less moving part.
_STREAM_ABOVE_MAX_TOKENS = 16_000

_client = None


def client():
    """Lazily construct the Anthropic client (imported here so importing this
    module doesn't require the SDK to be installed — only calling it does)."""
    global _client
    if _client is None:
        from anthropic import Anthropic
        _client = Anthropic()  # reads ANTHROPIC_API_KEY from the environment
    return _client


@dataclass
class Req:
    """One Claude request. `custom_id` is required on the batch path, where it is
    how results are matched back to inputs."""
    user: str
    system: list[dict] | None = None
    model: str | None = None
    max_tokens: int = 4096
    custom_id: str | None = None
    metadata: dict = field(default_factory=dict)  # caller's own bookkeeping

    def params(self) -> dict:
        p = {
            "model": self.model or EXTRACTION_MODEL,
            "max_tokens": self.max_tokens,
            "messages": [{"role": "user", "content": self.user}],
        }
        if self.system:
            p["system"] = self.system
        return p


def _text(msg) -> str:
    return "".join(b.text for b in msg.content if b.type == "text")


def _usage(msg, *, batch: bool = False) -> dict:
    """Normalised usage. Carries the model so cost is priced correctly, and the
    cache counters so a cache that silently isn't working shows up."""
    u = msg.usage
    return {
        "model": msg.model,
        "input_tokens": u.input_tokens,
        "output_tokens": u.output_tokens,
        "cache_read_input_tokens": getattr(u, "cache_read_input_tokens", 0) or 0,
        "cache_creation_input_tokens": getattr(u, "cache_creation_input_tokens", 0) or 0,
        "batch": batch,
    }


def call(req: Req) -> tuple[str, dict]:
    """Send one request now. Returns (text, usage)."""
    p = req.params()
    if req.max_tokens > _STREAM_ABOVE_MAX_TOKENS:
        with client().messages.stream(**p) as stream:
            msg = stream.get_final_message()
    else:
        msg = client().messages.create(**p)
    return _text(msg), _usage(msg)


def call_batch(
    reqs: list[Req],
    *,
    poll_seconds: int = 30,
    timeout_seconds: int = 20 * 3600,
) -> dict[str, tuple[str | None, dict]]:
    """Send many requests through the Batch API at half price.

    Returns {custom_id: (text, usage)}. A failed request has text None and an
    "error" key in its usage dict, so callers filter rather than crash — one bad
    input must not lose the whole batch.
    """
    if not reqs:
        return {}
    missing = [i for i, r in enumerate(reqs) if not r.custom_id]
    if missing:
        raise ValueError(f"call_batch needs custom_id on every Req (missing at {missing[:5]})")
    dupes = len(reqs) - len({r.custom_id for r in reqs})
    if dupes:
        raise ValueError(f"call_batch needs unique custom_ids ({dupes} duplicate(s))")

    from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
    from anthropic.types.messages.batch_create_params import Request

    batch = client().messages.batches.create(
        requests=[
            # custom_id is validated non-None just above; str() narrows for
            # the type checker without changing behaviour.
            Request(custom_id=str(r.custom_id),
                    params=MessageCreateParamsNonStreaming(**r.params()))  # type: ignore[typeddict-item]
            for r in reqs
        ]
    )
    print(f"    batch {batch.id}: {len(reqs)} requests submitted", flush=True)

    deadline = time.monotonic() + timeout_seconds
    while True:
        status = client().messages.batches.retrieve(batch.id)
        if status.processing_status == "ended":
            break
        if time.monotonic() > deadline:
            raise TimeoutError(
                f"batch {batch.id} still {status.processing_status} after "
                f"{timeout_seconds}s ({len(reqs)} requests)")
        time.sleep(poll_seconds)

    out: dict[str, tuple[str | None, dict]] = {}
    for res in client().messages.batches.results(batch.id):
        if res.result.type == "succeeded":
            msg = res.result.message
            out[res.custom_id] = (_text(msg), _usage(msg, batch=True))
        else:
            out[res.custom_id] = (None, {"error": res.result.type, "batch": True})
    return out


def _extract_json_block(text: str):
    """Outermost balanced {...}/[...] substring, or None (string/escape aware)."""
    start = next((i for i, ch in enumerate(text) if ch in "{["), None)
    if start is None:
        return None
    open_ch = text[start]
    close_ch = "}" if open_ch == "{" else "]"
    depth = 0
    in_str = esc = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == open_ch:
            depth += 1
        elif ch == close_ch:
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    return None


def parse_model_json(response: str):
    """Parse JSON from a model response: strip code fences, then salvage the
    outermost JSON value if wrapped in prose. Raises ValueError on failure."""
    text = response.strip()
    if "```json" in text:
        text = text.split("```json", 1)[1].split("```", 1)[0]
    elif "```" in text:
        text = text.split("```", 1)[1].split("```", 1)[0]
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        block = _extract_json_block(text)
        if block is not None:
            try:
                return json.loads(block)
            except json.JSONDecodeError:
                pass
        raise ValueError(f"Could not parse JSON from model response: {text[:200]!r}")
