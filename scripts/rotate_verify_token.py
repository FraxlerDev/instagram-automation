#!/usr/bin/env python3
"""Generate and save a webhook verify token without printing it."""

from __future__ import annotations

import secrets
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = PROJECT_ROOT / ".env"
KEY = "WEBHOOK_VERIFY_TOKEN"


def main() -> int:
    if not ENV_PATH.exists():
        raise SystemExit(".env does not exist; copy .env.example first")
    lines = ENV_PATH.read_text(encoding="utf-8").splitlines()
    replacement = f"{KEY}={secrets.token_urlsafe(32)}"
    updated: list[str] = []
    found = False
    for line in lines:
        if line.startswith(f"{KEY}="):
            updated.append(replacement)
            found = True
        else:
            updated.append(line)
    if not found:
        updated.append(replacement)
    ENV_PATH.write_text("\n".join(updated) + "\n", encoding="utf-8")
    print("WEBHOOK_VERIFY_TOKEN safely generated and saved to .env")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
