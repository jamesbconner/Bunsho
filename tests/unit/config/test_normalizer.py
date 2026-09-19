import pytest

from bunsho.config.normalizer import ConfigError, ConfigNormalizer


def test_sections_and_keys_are_case_insensitive() -> None:
    cfg = ConfigNormalizer({"Database": {"Host": "h"}, "DATABASE": {"PORT": "5"}})
    assert cfg.get_string("database", "host") == "h"
    assert cfg.get_int("Database", "port") == 5


def test_fallbacks_when_missing() -> None:
    cfg = ConfigNormalizer()
    assert cfg.get_string("a", "b", "x") == "x"
    assert cfg.get_int("a", "b", 7) == 7
    assert cfg.get_float("a", "b", 1.5) == 1.5
    assert cfg.get_bool("a", "b", True) is True
    assert not cfg.has_option("a", "b")


@pytest.mark.parametrize("raw", ["true", "YES", "1", "on"])
def test_get_bool_truthy(raw: str) -> None:
    assert ConfigNormalizer({"s": {"k": raw}}).get_bool("s", "k") is True


@pytest.mark.parametrize("raw", ["false", "No", "0", "off"])
def test_get_bool_falsy(raw: str) -> None:
    assert ConfigNormalizer({"s": {"k": raw}}).get_bool("s", "k", True) is False


def test_get_bool_accepts_real_bool_and_rejects_garbage() -> None:
    assert ConfigNormalizer({"s": {"k": True}}).get_bool("s", "k") is True
    with pytest.raises(ConfigError, match="not a valid boolean"):
        ConfigNormalizer({"s": {"k": "maybe"}}).get_bool("s", "k")


def test_invalid_numbers_raise_config_error() -> None:
    cfg = ConfigNormalizer({"s": {"i": "x", "f": "y"}})
    with pytest.raises(ConfigError, match="not a valid integer"):
        cfg.get_int("s", "i")
    with pytest.raises(ConfigError, match="not a valid float"):
        cfg.get_float("s", "f")


def test_merge_env_overrides_and_ignores_unrelated() -> None:
    cfg = ConfigNormalizer({"paths": {"data_dir": "file"}})
    merged = cfg.merge_env(
        {"BUNSHO_PATHS__DATA_DIR": "env", "OTHER": "x", "BUNSHO_BAD": "y", "BUNSHO___K": "z"}
    )
    assert merged.get_string("paths", "data_dir") == "env"
    assert cfg.get_string("paths", "data_dir") == "file"  # original untouched
    assert not merged.has_option("bad", "")
