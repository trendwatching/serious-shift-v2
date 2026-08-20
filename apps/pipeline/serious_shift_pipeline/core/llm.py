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
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from .config import EXTRACTION_MODEL

# Above this the SDK refuses a non-streaming request that could outlive its
# 10-minute ceiling. Below it, skip streaming: a plain create() is what the
# Batch API accepts, and it is one less moving part.
_STREAM_ABOVE_MAX_TOKENS = 16_000

#: At or below this many requests, skip the Batch API and just call.
#:
#: Batching trades latency for half price, which is plainly right for 44 shifts
#: and plainly wrong for one. The retry ladders submit whatever came back short
#: — often a single shift — and each of those submissions joins the queue on its
#: own terms. Measured on the 18 Aug 2026 publication run, four batches in one
#: session took 2m39s, 5m19s, 22m36s and 33m51s with no relationship to size,
#: and a FINAL one-request retry sat in_progress for 58 minutes. The discount it
#: was protecting was under a cent. A three-attempt ladder can therefore spend
#: hours of wall-clock to save small change, which is most of what made that
#: run take all evening.
#:
#: Three, not one: the same reasoning covers the tail of a ladder, and three
#: concurrent calls still return in about the time of the slowest one.
SYNC_AT_OR_BELOW = 3

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
    how results are matched back to inputs.

    `tools` carries SERVER tools (web_search / web_fetch) — the API executes
    them inside one request, so there is no client-side agent loop to run.
    Tool-bearing requests are sync-only: the research pass is iterative and
    interactive by nature, and the Batch API contract here stays simple.
    `documents` are content blocks (e.g. citation-enabled document blocks)
    prepended to the user turn. `betas` routes the call through the beta
    client surface (web_fetch requires its beta header)."""
    user: str
    system: list[dict] | None = None
    model: str | None = None
    max_tokens: int = 4096
    custom_id: str | None = None
    tools: list[dict] | None = None
    documents: list[dict] | None = None
    betas: list[str] | None = None
    metadata: dict = field(default_factory=dict)  # caller's own bookkeeping

    def params(self) -> dict:
        content: str | list[dict] = self.user
        if self.documents:
            content = [*self.documents, {"type": "text", "text": self.user}]
        p = {
            "model": self.model or EXTRACTION_MODEL,
            "max_tokens": self.max_tokens,
            "messages": [{"role": "user", "content": content}],
        }
        if self.system:
            p["system"] = self.system
        if self.tools:
            p["tools"] = self.tools
        return p


def _text(msg) -> str:
    return "".join(b.text for b in msg.content if b.type == "text")


def msg_text(msg) -> str:
    """Concatenated text blocks of a raw message (public counterpart of _text,
    for callers of call_raw that also read tool-result blocks)."""
    return _text(msg)


def _usage(msg, *, batch: bool = False) -> dict:
    """Normalised usage. Carries the model so cost is priced correctly, and the
    cache counters so a cache that silently isn't working shows up. Server
    tool use (web search requests) is billed per use, so it rides along too."""
    u = msg.usage
    server_tools = getattr(u, "server_tool_use", None)
    return {
        "model": msg.model,
        "input_tokens": u.input_tokens,
        "output_tokens": u.output_tokens,
        "cache_read_input_tokens": getattr(u, "cache_read_input_tokens", 0) or 0,
        "cache_creation_input_tokens": getattr(u, "cache_creation_input_tokens", 0) or 0,
        "web_search_requests": getattr(server_tools, "web_search_requests", 0) or 0,
        "batch": batch,
    }


#: How many pause_turn continuations one logical call may make. Long
#: server-tool research turns legitimately pause several times; a turn that
#: pauses more than this is runaway.
MAX_TURN_SEGMENTS = 6


def merge_usages(usages: list[dict]) -> dict:
    """One usage dict for a multi-segment (pause_turn-continued) call: token
    and search counters sum; identity fields come from the last segment."""
    merged = dict(usages[-1])
    for key in ("input_tokens", "output_tokens", "cache_read_input_tokens",
                "cache_creation_input_tokens", "web_search_requests"):
        merged[key] = sum((u.get(key) or 0) for u in usages)
    return merged


def _one_call(surface, p: dict, max_tokens: int):
    if max_tokens > _STREAM_ABOVE_MAX_TOKENS:
        with surface.stream(**p) as stream:
            return stream.get_final_message()
    return surface.create(**p)


def call_raw(req: Req):
    """Send one request now; return (message, usage) with content blocks
    intact — for callers that read more than the text (citations, tool
    results). Beta-flagged requests go through the beta surface.

    A long server-tool turn can stop with `pause_turn`; the API contract is to
    resend the conversation with the paused assistant message appended, and it
    continues. This loops that up to MAX_TURN_SEGMENTS times and returns a
    message whose `content` is every segment's blocks in order (tool results
    from early segments matter to callers) with usage summed across segments.
    """
    p = req.params()
    surface = client().beta.messages if req.betas else client().messages
    if req.betas:
        p["betas"] = req.betas

    contents: list = []
    usages: list[dict] = []
    msg = None
    for _segment in range(MAX_TURN_SEGMENTS):
        msg = _one_call(surface, p, req.max_tokens)
        usages.append(_usage(msg))
        contents.extend(msg.content)
        if getattr(msg, "stop_reason", None) != "pause_turn":
            break
        p = dict(p)
        p["messages"] = [*p["messages"],
                         {"role": "assistant", "content": msg.content}]

    assert msg is not None  # MAX_TURN_SEGMENTS >= 1, so the loop ran
    if len(usages) == 1:
        return msg, usages[0]
    from types import SimpleNamespace
    merged = SimpleNamespace(content=contents, model=msg.model,
                             stop_reason=getattr(msg, "stop_reason", None))
    return merged, merge_usages(usages)


def call(req: Req) -> tuple[str, dict]:
    """Send one request now. Returns (text, usage)."""
    msg, usage = call_raw(req)
    return _text(msg), usage



def _call_small(reqs: list[Req]) -> dict[str, tuple[str | None, dict]]:
    """The `call_batch` contract, served by direct calls — see SYNC_AT_OR_BELOW.

    Failures are returned, not raised, because that is what callers of
    call_batch already handle: one bad input must not lose the others. Usage is
    NOT marked `batch`, so the cost report shows what these actually cost.
    """
    print(f'    {len(reqs)} request(s) — calling directly, '
          f'the batch queue is not worth the wait', flush=True)

    def one(req: Req) -> tuple[str | None, dict]:
        try:
            return call(req)
        except Exception as exc:  # noqa: BLE001 — mirrors the batch path
            return (None, {'error': type(exc).__name__, 'detail': str(exc)[:200]})

    with ThreadPoolExecutor(max_workers=len(reqs)) as pool:
        results = list(pool.map(one, reqs))
    return {str(req.custom_id): result for req, result in zip(reqs, results)}


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
    tooled = [i for i, r in enumerate(reqs) if r.tools or r.betas]
    if tooled:
        raise ValueError(
            f"call_batch does not take tool/beta requests (at {tooled[:5]}) — "
            "server-tool research calls are sync-only, use call()/call_raw()")
    missing = [i for i, r in enumerate(reqs) if not r.custom_id]
    if missing:
        raise ValueError(f"call_batch needs custom_id on every Req (missing at {missing[:5]})")
    dupes = len(reqs) - len({r.custom_id for r in reqs})
    if dupes:
        raise ValueError(f"call_batch needs unique custom_ids ({dupes} duplicate(s))")
    # After the contract checks, never before: results are keyed by custom_id
    # whichever path serves them, so a caller that got away with a missing or
    # duplicated id on a two-request submission would lose a result silently
    # and only fail once the map grew past the threshold.
    if len(reqs) <= SYNC_AT_OR_BELOW:
        return _call_small(reqs)

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
