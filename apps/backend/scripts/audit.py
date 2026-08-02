#!/usr/bin/env python3
"""Run cargo-audit with only complete, unexpired repository waivers."""

from __future__ import annotations

import json
import subprocess
from datetime import date
from pathlib import Path


BACKEND = Path(__file__).resolve().parents[1]
WAIVERS = BACKEND.parents[1] / "security" / "audit-waivers.json"


def main() -> None:
    waivers = json.loads(WAIVERS.read_text())["rust"]
    today = date.today().isoformat()
    command = ["cargo", "audit"]

    for waiver in waivers:
        for field in ("id", "reason", "owner", "expires"):
            if not waiver.get(field):
                raise SystemExit(f"Rust audit waiver is missing {field}")
        if waiver["expires"] < today:
            raise SystemExit(
                f"{waiver['id']} waiver expired on {waiver['expires']}"
            )
        print(f"WAIVED {waiver['id']} until {waiver['expires']}")
        command.extend(("--ignore", waiver["id"]))

    subprocess.run(command, cwd=BACKEND, check=True)


if __name__ == "__main__":
    main()
