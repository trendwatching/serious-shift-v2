"""One image out of Gemini, with the same retry ladder the .mjs uses."""
from __future__ import annotations

import base64
import os
import random
import time
from typing import Any

import requests

MODEL = os.environ.get('SS_ART_MODEL', 'gemini-3.1-flash-image')
API_BASE = 'https://generativelanguage.googleapis.com/v1beta/models'

#: USD per generated image at the 1K tier, standard (not batch). Used for
#: reporting and for the runaway ceiling — never to decide whether to generate.
COST_PER_IMAGE = 0.067

MAX_ATTEMPTS = 6
CONNECT_TIMEOUT = 10
READ_TIMEOUT = 180


class GeminiError(RuntimeError):
    """A generation that did not produce an image. Always caught by the caller."""


def api_key() -> str:
    return os.environ.get('GEMINI_API_KEY', '')


def _retry_after(response) -> float | None:
    try:
        return float(response.headers.get('retry-after', ''))
    except (TypeError, ValueError):
        return None


def generate_image(prompt: str, aspect: str, *, model: str = '') -> bytes:
    """JPEG/PNG bytes for one prompt. Raises GeminiError on anything else.

    Retries 429 and 5xx up to MAX_ATTEMPTS, honouring Retry-After and otherwise
    backing off exponentially with jitter. A 4xx that is not 429 is not retried:
    it means the request is wrong, and asking again more slowly will not fix it.
    """
    key = api_key()
    if not key:
        raise GeminiError('GEMINI_API_KEY is not set')
    used_model = model or MODEL
    url = f'{API_BASE}/{used_model}:generateContent'
    # Annotated: inferred as dict[str, Collection[Collection[str]]], which some
    # mypy/types-requests combinations reject against requests' JsonType.
    payload: dict[str, Any] = {
        'contents': [{'parts': [{'text': prompt}]}],
        'generationConfig': {
            'responseModalities': ['IMAGE'],
            'imageConfig': {'aspectRatio': aspect, 'imageSize': '1K'},
        },
    }

    last = ''
    for attempt in range(MAX_ATTEMPTS):
        try:
            response = requests.post(
                url, json=payload, headers={'x-goog-api-key': key},
                timeout=(CONNECT_TIMEOUT, READ_TIMEOUT))
        except requests.RequestException as exc:
            last = f'{type(exc).__name__}: {exc}'
        else:
            if response.status_code == 200:
                return _image_bytes(response.json())
            last = f'HTTP {response.status_code}: {response.text[:200]}'
            if response.status_code != 429 and response.status_code < 500:
                raise GeminiError(last)
            wait = _retry_after(response)
        if attempt == MAX_ATTEMPTS - 1:
            break
        delay = locals().get('wait') or (2 ** attempt) + random.random()  # noqa: S311
        time.sleep(min(float(delay), 60.0))
    raise GeminiError(f'gave up after {MAX_ATTEMPTS} attempts — {last}')


def _image_bytes(body: dict) -> bytes:
    """Pull the inline image out of a response, or say why there isn't one."""
    for candidate in body.get('candidates') or []:
        for part in (candidate.get('content') or {}).get('parts') or []:
            inline = part.get('inlineData') or part.get('inline_data')
            if inline and inline.get('data'):
                return base64.b64decode(inline['data'])
        reason = candidate.get('finishReason') or candidate.get('finish_reason')
        if reason:
            raise GeminiError(f'no image in response (finishReason={reason})')
    raise GeminiError('no image in response')
