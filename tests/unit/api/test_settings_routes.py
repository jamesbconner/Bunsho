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
