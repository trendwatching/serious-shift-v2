"""
Anthropic client + robust JSON parsing, shared by the extraction/generation steps.

Replaces the legacy hand-rolled `urllib` calls (which disabled TLS verification)
with the official SDK, which handles auth (ANTHROPIC_API_KEY), retries on
transient errors, and TLS correctly.
"""
from __future__ import annotations

import json
import time

from .config import EXTRACTION_MODEL

_client = None


def client():
    """Lazily construct the Anthropic client (imported here so importing this
    module doesn't require the SDK to be installed — only calling it does)."""
    global _client
    if _client is None:
        from anthropic import Anthropic
        _client = Anthropic()  # reads ANTHROPIC_API_KEY from the environment
    return _client


def call_claude(prompt: str, *, model: str | None = None, max_tokens: int = 8192,
                retries: int = 2) -> tuple[str, dict]:
    """Return (text, usage). usage = {input_tokens, output_tokens}.

    Always streams: with large max_tokens (the map/keynote generators use up to
    32k) the SDK refuses a non-streaming request that could exceed its 10-minute
    ceiling. Streaming removes that limit and yields the same final message.
    """
    last: Exception | None = None
    for attempt in range(retries):
        try:
            with client().messages.stream(
                model=model or EXTRACTION_MODEL,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
            ) as stream:
                parts = [chunk for chunk in stream.text_stream]
                final = stream.get_final_message()
            usage = {"input_tokens": final.usage.input_tokens,
                     "output_tokens": final.usage.output_tokens}
            return "".join(parts), usage
        except Exception as e:  # noqa: BLE001 — transient API errors, retried below
            last = e
            if attempt < retries - 1:
                time.sleep(5)
    raise last  # type: ignore[misc]


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
