from fastapi.testclient import TestClient

from bunsho.models.review_settings import ReviewSettings

SETTINGS = "/api/v1/settings"
Headers = dict[str, str]


def test_settings_default_to_the_documented_values(
    review_client: TestClient, review_headers: Headers
) -> None:
    response = review_client.get(SETTINGS, headers=review_headers)
    assert response.status_code == 200
    assert response.json() == ReviewSettings().model_dump(mode="json")


def test_a_saved_settings_document_is_returned_by_later_reads(
    review_client: TestClient, review_headers: Headers
) -> None:
    document = ReviewSettings().model_dump(mode="json")
    document.update(
        new_card_policy="pinned_levels", active_levels=["N4", "N5"], target_retention=0.85
    )
    document["new_limits"] = {"kana": 0, "kanji": 5, "vocab": 10}
    saved = review_client.put(SETTINGS, json=document, headers=review_headers)
    assert saved.status_code == 200
    assert saved.json() == document
    assert review_client.get(SETTINGS, headers=review_headers).json() == document


def test_invalid_settings_are_rejected_and_nothing_is_saved(
    review_client: TestClient, review_headers: Headers
) -> None:
    good = ReviewSettings(target_retention=0.85).model_dump(mode="json")
    assert review_client.put(SETTINGS, json=good, headers=review_headers).status_code == 200
    bad = {**good, "target_retention": 1.5, "rollover_hour": 30}
    response = review_client.put(SETTINGS, json=bad, headers=review_headers)
    assert response.status_code == 422
    assert isinstance(response.json()["detail"], list)
    assert len(response.json()["detail"]) == 2  # every problem is reported together
    assert review_client.get(SETTINGS, headers=review_headers).json() == good


def test_unknown_settings_fields_are_rejected(
    review_client: TestClient, review_headers: Headers
) -> None:
    body = {**ReviewSettings().model_dump(mode="json"), "surprise": True}
    assert review_client.put(SETTINGS, json=body, headers=review_headers).status_code == 422


def test_a_partial_document_takes_defaults_for_the_rest(
    review_client: TestClient, review_headers: Headers
) -> None:
    review_client.put(SETTINGS, json={"target_retention": 0.8}, headers=review_headers)
    assert review_client.get(SETTINGS, headers=review_headers).json() == {
        **ReviewSettings().model_dump(mode="json"),
        "target_retention": 0.8,
    }


def test_the_type_switches_and_kana_gate_round_trip(
    review_client: TestClient, review_headers: Headers
) -> None:
    document = ReviewSettings().model_dump(mode="json")
    document["type_enabled"] = {"kana": True, "kanji": False, "vocab": True}
    document["kana_gate"] = {"kanji": False, "vocab": True, "threshold": 0.9}
    saved = review_client.put(SETTINGS, json=document, headers=review_headers)
    assert saved.status_code == 200
    assert saved.json() == document
    assert review_client.get(SETTINGS, headers=review_headers).json() == document


def test_a_gate_with_kana_disabled_is_rejected_at_the_gate_field(
    review_client: TestClient, review_headers: Headers
) -> None:
    good = ReviewSettings().model_dump(mode="json")
    assert review_client.put(SETTINGS, json=good, headers=review_headers).status_code == 200
    bad = {
        **good,
        "type_enabled": {"kana": False, "kanji": True, "vocab": True},
        "kana_gate": {"kanji": True, "vocab": False, "threshold": 0.8},
    }
    response = review_client.put(SETTINGS, json=bad, headers=review_headers)
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert [error["loc"] for error in detail] == [["body", "kana_gate"]]
    assert detail[0]["msg"].startswith("Turn kana on")
    assert review_client.get(SETTINGS, headers=review_headers).json() == good
