#!/usr/bin/env python3
"""Live smoke test: requires ERANK_COOKIE_FILE pointing at a logged-in export."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def main() -> int:
    from erank_mcp.config import DEFAULT_COOKIE_FILE, get_settings
    from erank_mcp.client import reset_client
    from erank_mcp.server import erank_session_status, erank_catalog_info

    settings = get_settings()
    cookie_path = settings.erank_cookie_file
    has_header = bool(settings.erank_cookie_header or os.environ.get("ERANK_COOKIE_HEADER"))
    if not has_header and (not cookie_path or not Path(cookie_path).exists()):
        print(
            "Add your cookie export as:\n"
            f"  {DEFAULT_COOKIE_FILE}\n"
            "(copy cookies.example.json → cookies.json and paste real values)\n"
            "Then re-run: .\\.venv\\Scripts\\python.exe scripts\\smoke_session.py"
        )
        return 2

    reset_client()
    status = erank_session_status()
    print(json.dumps(status, indent=2, default=str)[:4000])
    print("--- catalog ---")
    print(json.dumps(erank_catalog_info(), indent=2)[:1500])
    return 0 if status.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
