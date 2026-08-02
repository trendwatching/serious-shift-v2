"""Small, dependency-free redaction helpers for values written to logs."""
from __future__ import annotations

import re

_URL_CREDENTIALS = re.compile(r"(https?://)([^/@\s]+)@", re.IGNORECASE)


def redact_secrets(value: object) -> str:
    """Remove userinfo from HTTP(S) URLs without hiding the destination host."""
    return _URL_CREDENTIALS.sub(r"\1[credentials]@", str(value))
