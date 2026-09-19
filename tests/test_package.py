from importlib import metadata

import bunsho


def test_names_and_version() -> None:
    assert bunsho.APP_NAME == "Bunshō"
    assert bunsho.APP_SLUG == "bunsho"
    assert bunsho.__version__ == metadata.version("bunsho")
