from fastapi.testclient import TestClient

from bunsho.api.app import create_app
from bunsho.config.service import ServiceConfig
from bunsho.models.content import JlptLevel
from tests.base import PASSWORD, make_kana, make_kanji, make_vocab, write_content

SUMMARY = "/api/v1/content/summary"


def test_the_summary_types_leveled_and_unleveled_kanji(service_config: ServiceConfig) -> None:
    write_content(
        service_config.app.content_db_path,
        kana=[make_kana("あ", "a")],
        kanji=[
            make_kanji("日", JlptLevel.N5),
            make_kanji("曜", JlptLevel.N4),
            make_kanji("犬", None),
        ],
        vocab=[make_vocab("日本", "にほん"), make_vocab("学生", "がくせい", JlptLevel.N4)],
    )
    with TestClient(create_app(service_config)) as client:
        token = client.post(
            "/api/v1/auth/login", json={"username": "james", "password": PASSWORD}
        ).json()["access_token"]
        body = client.get(SUMMARY, headers={"Authorization": f"Bearer {token}"}).json()
    assert body["built"] is True
    assert (body["kana"], body["kanji"], body["vocab"]) == (1, 3, 2)  # kanji counts every row
    assert body["unleveled_kanji"] == 1
    assert body["kanji_by_level"] == {"N5": 1, "N4": 1, "N3": 0, "N2": 0, "N1": 0}
    assert body["vocab_by_level"] == {"N5": 1, "N4": 1, "N3": 0, "N2": 0, "N1": 0}
