import json
from pathlib import Path

import pytest

from bunsho.api.openapi_snapshot import openapi_document, render_openapi_snapshot

SNAPSHOT = Path(__file__).resolve().parents[3] / "frontend" / "openapi.json"


def test_the_committed_snapshot_matches_the_app() -> None:
    assert SNAPSHOT.read_text(encoding="utf-8") == render_openapi_snapshot(), (
        "frontend/openapi.json is stale: run `uv run python scripts/export_openapi.py`, "
        "then `npm run gen:api` in frontend/, and commit both files"
    )


def test_the_rendering_is_deterministic_with_sorted_keys() -> None:
    first = render_openapi_snapshot()
    assert first == render_openapi_snapshot()
    assert first.endswith("}\n")
    document = json.loads(first)
    assert list(document) == sorted(document)
    assert list(document["paths"]) == sorted(document["paths"])


def test_the_document_describes_the_routes_the_frontend_uses() -> None:
    document = openapi_document()
    operations = {
        operation["operationId"]
        for methods in document["paths"].values()
        for operation in methods.values()
    }
    assert {
        "login",
        "refreshToken",
        "getContentSummary",
        "getConfigCheck",
        "startContentBuild",
        "getLatestContentBuild",
        "getContentBuild",
        "getNextReview",
        "answerReview",
    } <= operations
    schemas = document["components"]["schemas"]
    assert {"WsAuthMessage", "WsSnapshot", "WsEvent", "BuildStatusResponse"} <= set(schemas)


def test_building_the_document_touches_no_filesystem(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    render_openapi_snapshot()
    assert list(tmp_path.iterdir()) == []
