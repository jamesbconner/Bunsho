import re
from collections.abc import Iterator
from typing import Any

from fastapi.testclient import TestClient

PUBLIC = {
    ("get", "/api/v1/health"),
    ("post", "/api/v1/auth/login"),
    ("post", "/api/v1/auth/refresh"),
}
HTTP_METHODS = {"get", "post", "put", "patch", "delete"}


def _schema(client: TestClient) -> dict[str, Any]:
    return client.get("/openapi.json").json()  # type: ignore[no-any-return]


def _operations(schema: dict[str, Any]) -> Iterator[tuple[str, str, dict[str, Any]]]:
    for path, item in schema["paths"].items():
        for method, operation in item.items():
            if method in HTTP_METHODS:
                yield method, path, operation


def test_every_operation_has_a_unique_explicit_camel_case_id(client: TestClient) -> None:
    ids = [operation["operationId"] for _, _, operation in _operations(_schema(client))]
    assert len(ids) >= 13
    assert len(ids) == len(set(ids))
    for operation_id in ids:
        # FastAPI's generated ids look like get_health_api_v1_health_get.
        assert re.fullmatch(r"[a-z][A-Za-z0-9]*", operation_id), operation_id


def test_every_protected_operation_documents_401(client: TestClient) -> None:
    for method, path, operation in _operations(_schema(client)):
        if (method, path) not in PUBLIC:
            assert "401" in operation["responses"], f"{method} {path}"


def test_documented_errors_use_the_error_model_with_a_string_detail(client: TestClient) -> None:
    schema = _schema(client)
    assert schema["components"]["schemas"]["ErrorResponse"]["properties"]["detail"]["type"] == (
        "string"
    )
    for method, path, operation in _operations(schema):
        for code in ("401", "404", "409", "429", "503"):
            response = operation["responses"].get(code)
            if response is None or (method, path) == ("get", "/api/v1/health"):
                continue
            ref = response["content"]["application/json"]["schema"]["$ref"]
            assert ref.endswith("/ErrorResponse"), f"{method} {path} {code}"


def test_the_expected_status_codes_are_documented(client: TestClient) -> None:
    operations = {
        operation["operationId"]: set(operation["responses"])
        for _, _, operation in _operations(_schema(client))
    }
    assert {"401", "429"} <= operations["login"]
    assert {"401", "404", "409", "503"} <= operations["answerReview"]
    assert {"401", "503"} <= operations["getNextReview"]
    assert {"401", "503"} <= operations["getStatsSummary"]
    assert {"401", "409"} <= operations["startContentBuild"]
    assert {"401", "404"} <= operations["getContentBuild"]
    assert {"200", "503"} <= operations["getHealth"]
    assert "422" in operations["answerReview"]


def test_websocket_messages_are_published_in_the_components(client: TestClient) -> None:
    schemas = _schema(client)["components"]["schemas"]
    for name in ("WsAuthMessage", "WsReady", "WsSnapshot", "WsEvent"):
        assert name in schemas, name
    assert schemas["WsAuthMessage"]["properties"]["type"]["const"] == "auth"
    # References inside the message schemas resolve within the same document.
    snapshot_task = schemas["WsSnapshot"]["properties"]["task"]
    assert snapshot_task["$ref"] == "#/components/schemas/BuildStatusResponse"
    assert "BuildStatusResponse" in schemas


def test_the_schema_is_generated_once(client: TestClient) -> None:
    assert _schema(client) == _schema(client)


def test_response_models_mark_defaulted_fields_required(client: TestClient) -> None:
    schemas = _schema(client)["components"]["schemas"]
    assert {"kana", "kanji", "vocab"} <= set(schemas["TypeCounts"]["required"])
    assert {
        "built",
        "kana",
        "kanji",
        "vocab",
        "unleveled_kanji",
        "kanji_by_level",
        "vocab_by_level",
        "meta",
    } <= set(schemas["ContentSummaryResponse"]["required"])

    # ReviewSettings is both the PUT body and a response, so FastAPI splits it in two.
    settings_fields = {
        "new_card_policy",
        "new_limits",
        "target_retention",
        "rollover_hour",
        "active_levels",
        "mastery_threshold",
    }
    response_schema = schemas["ReviewSettings-Output"]
    request_schema = schemas["ReviewSettings-Input"]
    assert settings_fields <= set(response_schema["required"])
    assert not set(request_schema.get("required", []))  # a partial PUT still validates
    assert {"kana", "kanji", "vocab"} <= set(schemas["NewLimits-Output"]["required"])
    assert not set(schemas["NewLimits-Input"].get("required", []))


def test_expected_last_review_is_documented_as_an_opaque_token(client: TestClient) -> None:
    schemas = _schema(client)["components"]["schemas"]
    for model in ("AnswerRequest", "CardView"):
        description = schemas[model]["properties"]["expected_last_review"]["description"]
        assert "opaque" in description, model
