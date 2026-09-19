import logging
import threading
import time

import pytest
from fastapi.testclient import TestClient

from bunsho.config.service import ServiceConfig
from tests.base import StubOrchestrator

BUILD = "/api/v1/admin/content/build"


def _wait(client: TestClient, headers: dict[str, str], task_id: str, timeout: float = 10.0) -> dict:  # type: ignore[type-arg]
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        body = client.get(f"{BUILD}/{task_id}", headers=headers).json()
        if body["state"] != "running":
            return body  # type: ignore[no-any-return]
        time.sleep(0.02)
    raise AssertionError("build did not finish in time")


def test_config_check_reports_each_check(
    stub_client: TestClient, auth_headers: dict[str, str]
) -> None:
    body = stub_client.get("/api/v1/admin/config-check", headers=auth_headers).json()
    names = [check["name"] for check in body["checks"]]
    assert names == ["deck_present", "deck_checksum", "data_dir_writable", "jamdict_available"]
    assert body["ok"] is False  # the test environment has no deck


def test_real_build_finishes_and_makes_content_visible(
    stub_client: TestClient, auth_headers: dict[str, str]
) -> None:
    summary_url = "/api/v1/content/summary"
    assert stub_client.get(summary_url, headers=auth_headers).json() == {
        "built": False,
        "kana": 0,
        "kanji": 0,
        "vocab": 0,
        "meta": {},
    }
    started = stub_client.post(BUILD, json={}, headers=auth_headers)
    assert started.status_code == 202
    body = started.json()
    assert body["state"] == "running"
    assert body["dry_run"] is False
    finished = _wait(stub_client, auth_headers, body["task_id"])
    assert finished["state"] == "succeeded"
    assert finished["report"]["kana_count"] == 208
    assert finished["progress"]["stage"] == "write"
    assert stub_client.get(summary_url, headers=auth_headers).json()["built"] is True
    latest = stub_client.get(BUILD, headers=auth_headers).json()
    assert latest["task_id"] == body["task_id"]


def test_dry_run_builds_nothing(stub_client: TestClient, auth_headers: dict[str, str]) -> None:
    started = stub_client.post(BUILD, json={"dry_run": True}, headers=auth_headers).json()
    finished = _wait(stub_client, auth_headers, started["task_id"])
    assert finished["state"] == "succeeded"
    assert finished["dry_run"] is True
    summary = stub_client.get("/api/v1/content/summary", headers=auth_headers).json()
    assert summary["built"] is False


def test_second_build_while_one_runs_gets_409(
    stub_client: TestClient, auth_headers: dict[str, str], stub: StubOrchestrator
) -> None:
    stub.gate = threading.Event()
    first = stub_client.post(BUILD, json={}, headers=auth_headers).json()
    conflict = stub_client.post(BUILD, json={}, headers=auth_headers)
    assert conflict.status_code == 409
    assert first["task_id"] in conflict.json()["detail"]
    stub.gate.set()
    assert _wait(stub_client, auth_headers, first["task_id"])["state"] == "succeeded"


def test_failed_build_is_reported(
    stub_client: TestClient, auth_headers: dict[str, str], stub: StubOrchestrator
) -> None:
    stub.error = RuntimeError("deck exploded")
    started = stub_client.post(BUILD, json={}, headers=auth_headers).json()
    finished = _wait(stub_client, auth_headers, started["task_id"])
    assert finished["state"] == "failed"
    assert finished["error"] == "RuntimeError: deck exploded"
    assert finished["report"] is None


def test_unknown_build_and_no_builds_yet_are_404(
    stub_client: TestClient, auth_headers: dict[str, str]
) -> None:
    assert stub_client.get(f"{BUILD}/nope", headers=auth_headers).status_code == 404
    assert stub_client.get(BUILD, headers=auth_headers).status_code == 404


@pytest.mark.parametrize("damage", ["delete", "corrupt"])
def test_unreadable_content_db_summarises_as_not_built(
    stub_client: TestClient,
    auth_headers: dict[str, str],
    service_config: ServiceConfig,
    caplog: pytest.LogCaptureFixture,
    damage: str,
) -> None:
    started = stub_client.post(BUILD, json={}, headers=auth_headers).json()
    assert _wait(stub_client, auth_headers, started["task_id"])["state"] == "succeeded"
    summary_url = "/api/v1/content/summary"
    assert stub_client.get(summary_url, headers=auth_headers).json()["built"] is True
    db_path = service_config.app.content_db_path
    if damage == "delete":
        db_path.unlink()
    else:
        db_path.write_bytes(b"this is not a sqlite database" * 100)
    with caplog.at_level(logging.WARNING, logger="bunsho"):
        response = stub_client.get(summary_url, headers=auth_headers)
    assert response.status_code == 200
    assert response.json() == {"built": False, "kana": 0, "kanji": 0, "vocab": 0, "meta": {}}
    assert str(db_path) not in response.text
    assert "sqlite" not in response.text.lower()
    assert any("content_summary_unreadable" in record.getMessage() for record in caplog.records)
