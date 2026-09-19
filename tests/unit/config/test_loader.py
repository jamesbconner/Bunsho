from pathlib import Path

from bunsho.config.loader import load_config


def test_precedence_file_then_dotenv_then_environ(tmp_path: Path) -> None:
    toml = tmp_path / "config.toml"
    toml.write_text('[Paths]\nData_Dir = "from-toml"\nResources_Dir = "toml-res"\n')
    dotenv = tmp_path / ".env"
    dotenv.write_text("BUNSHO_PATHS__DATA_DIR=from-dotenv\nBUNSHO_LOGGING__LEVEL=debug\n")
    cfg = load_config(
        config_file=toml,
        env_file=dotenv,
        environ={"BUNSHO_LOGGING__LEVEL": "warning"},
    )
    assert cfg.get_string("paths", "data_dir") == "from-dotenv"
    assert cfg.get_string("paths", "resources_dir") == "toml-res"
    assert cfg.get_string("logging", "level") == "warning"


def test_defaults_to_process_environment(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("BUNSHO_PATHS__DATA_DIR", "from-os")
    assert load_config().get_string("paths", "data_dir") == "from-os"
