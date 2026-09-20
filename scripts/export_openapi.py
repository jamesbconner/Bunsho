"""Write the API's OpenAPI document to frontend/openapi.json (the frontend's type source).

Usage: ``uv run python scripts/export_openapi.py``. Then run ``npm run gen:api`` in ``frontend/``.
"""

from __future__ import annotations

import sys
from pathlib import Path

from bunsho.api.openapi_snapshot import render_openapi_snapshot

SNAPSHOT = Path(__file__).resolve().parent.parent / "frontend" / "openapi.json"


def main() -> int:
    """Write the snapshot and report where."""
    SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
    SNAPSHOT.write_text(render_openapi_snapshot(), encoding="utf-8", newline="\n")
    sys.stderr.write(f"wrote {SNAPSHOT}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
