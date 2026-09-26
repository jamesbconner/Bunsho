from typing import Any

import pytest
from fastapi.testclient import TestClient

NEXT = "/api/v1/reviews/next"
ANSWER = "/api/v1/reviews/answer"
STATS = "/api/v1/stats/summary"
SETTINGS = "/api/v1/settings"

Headers = dict[str, str]


def _body(card: dict[str, Any], grade: int = 3) -> dict[str, Any]:
    return {
        "item_id": card["item_id"],
        "direction": card["direction"],
        "grade": grade,
        "expected_last_review": card["expected_last_review"],
    }


@pytest.mark.parametrize(
    ("method", "url"),
    [("get", NEXT), ("post", ANSWER), ("get", STATS), ("get", SETTINGS), ("put", SETTINGS)],
)
def test_every_new_route_requires_a_token(review_client: TestClient, method: str, url: str) -> None:
    response = getattr(review_client, method)(url, **({} if method == "get" else {"json": {}}))
    assert response.status_code == 401
    assert isinstance(response.json()["detail"], str)


def test_next_returns_the_first_card_with_content_and_counts(
    review_client: TestClient, review_headers: Headers
) -> None:
    response = review_client.get(NEXT, headers=review_headers)
    assert response.status_code == 200
    body = response.json()
    card = body["card"]
    # Kana are shuffled, so either direction of the only kana (あ) can come first.
    assert card["item_type"] == "kana"
    assert card["direction"] in {"glyph_to_sound", "sound_to_glyph"}
    assert card["is_new"] is True
    assert card["state"] == 0
    assert card["expected_last_review"] is None
    assert card["kana"]["char"] == "あ"
    assert card["kanji"] is None
    assert card["vocab"] is None
    assert set(card["intervals"]) == {"again", "hard", "good", "easy"}
    assert body["next_due_at"] is None
    assert body["counts"] == {
        "due": {"kana": 0, "kanji": 0, "vocab": 0},
        "new_remaining": {"kana": 2, "kanji": 3, "vocab": 4},
    }


def test_answering_records_the_review_and_updates_the_counts(
    review_client: TestClient, review_headers: Headers
) -> None:
    card = review_client.get(NEXT, headers=review_headers).json()["card"]
    response = review_client.post(ANSWER, json=_body(card), headers=review_headers)
    assert response.status_code == 200
    assert response.json()["new_remaining"] == {"kana": 1, "kanji": 3, "vocab": 4}
    following = review_client.get(NEXT, headers=review_headers).json()["card"]
    assert (following["item_id"], following["direction"]) != (card["item_id"], card["direction"])


def test_answering_the_same_card_twice_is_a_conflict(
    review_client: TestClient, review_headers: Headers
) -> None:
    card = review_client.get(NEXT, headers=review_headers).json()["card"]
    body = _body(card)
    assert review_client.post(ANSWER, json=body, headers=review_headers).status_code == 200
    second = review_client.post(ANSWER, json=body, headers=review_headers)
    assert second.status_code == 409
    assert isinstance(second.json()["detail"], str)


def test_answering_an_unknown_item_is_a_404(
    review_client: TestClient, review_headers: Headers
) -> None:
    body = {
        "item_id": "vocab:nope:nope",
        "direction": "recognition",
        "grade": 3,
        "expected_last_review": None,
    }
    response = review_client.post(ANSWER, json=body, headers=review_headers)
    assert response.status_code == 404
    assert isinstance(response.json()["detail"], str)


@pytest.mark.parametrize(
    "change",
    [
        {"grade": 5},
        {"grade": 0},
        {"direction": "sideways"},
        {"duration_ms": -1},
        {"item_id": ""},
        {"expected_last_review": "2026-09-20T12:00:00"},  # no timezone
    ],
)
def test_an_invalid_answer_body_is_a_422(
    review_client: TestClient, review_headers: Headers, change: dict[str, Any]
) -> None:
    card = review_client.get(NEXT, headers=review_headers).json()["card"]
    response = review_client.post(ANSWER, json={**_body(card), **change}, headers=review_headers)
    assert response.status_code == 422
    assert isinstance(response.json()["detail"], list)


def test_a_missing_expected_last_review_is_a_422(
    review_client: TestClient, review_headers: Headers
) -> None:
    card = review_client.get(NEXT, headers=review_headers).json()["card"]
    body = _body(card)
    del body["expected_last_review"]
    assert review_client.post(ANSWER, json=body, headers=review_headers).status_code == 422


def test_content_that_is_not_built_answers_503(
    stub_client: TestClient, auth_headers: Headers
) -> None:
    for method, url in [("get", NEXT), ("get", STATS)]:
        response = getattr(stub_client, method)(url, headers=auth_headers)
        assert response.status_code == 503
        assert "content" in response.json()["detail"]


def test_stats_reflect_an_answer(review_client: TestClient, review_headers: Headers) -> None:
    card = review_client.get(NEXT, headers=review_headers).json()["card"]
    review_client.post(ANSWER, json=_body(card), headers=review_headers)
    body = review_client.get(STATS, headers=review_headers).json()
    assert body["reviewed_today"] == 1
    assert body["introduced_today"] == {"kana": 1, "kanji": 0, "vocab": 0}
    assert len(body["daily_reviews"]) == 30
    assert body["daily_reviews"][-1]["reviews"] == 1
    assert body["retention_30d"] is None
    assert set(body["by_type"]) == {"kana", "kanji", "vocab"}
    assert body["by_type"]["kana"]["total"] == 2
    assert {p["item_type"] for p in body["by_level"]} == {"kanji", "vocab"}
