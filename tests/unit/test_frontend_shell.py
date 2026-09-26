from pathlib import Path

import pytest

from bunsho.frontend_shell import (
    CSP_NONCE_PLACEHOLDER,
    StaleShellError,
    read_shell,
    shell_problem,
)

CURRENT = f'<html><head><meta name="csp-nonce" content="{CSP_NONCE_PLACEHOLDER}" /></head></html>'


def _dist(tmp_path: Path, html: str | bytes | None) -> Path:
    dist = tmp_path / "dist"
    dist.mkdir()
    if isinstance(html, bytes):
        (dist / "index.html").write_bytes(html)
    elif html is not None:
        (dist / "index.html").write_text(html, encoding="utf-8")
    return dist


def test_the_placeholder_is_the_documented_literal() -> None:
    assert CSP_NONCE_PLACEHOLDER == "__CSP_NONCE__"


def test_read_shell_returns_a_current_build(tmp_path: Path) -> None:
    assert read_shell(_dist(tmp_path, CURRENT)) == CURRENT


def test_read_shell_returns_none_without_an_index(tmp_path: Path) -> None:
    assert read_shell(_dist(tmp_path, None)) is None


def test_read_shell_rejects_a_build_without_the_placeholder(tmp_path: Path) -> None:
    with pytest.raises(StaleShellError, match="npm run build"):
        read_shell(_dist(tmp_path, "<html><body>old</body></html>"))


def test_a_stale_shell_error_is_a_value_error(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="placeholder"):
        read_shell(_dist(tmp_path, "<html></html>"))


def test_shell_problem_is_none_for_a_current_build(tmp_path: Path) -> None:
    assert shell_problem(_dist(tmp_path, CURRENT)) is None


def test_shell_problem_is_none_without_an_index(tmp_path: Path) -> None:
    assert shell_problem(_dist(tmp_path, None)) is None


def test_shell_problem_names_the_file_and_the_fix_for_a_stale_build(tmp_path: Path) -> None:
    problem = shell_problem(_dist(tmp_path, "<html></html>"))
    assert problem is not None
    assert "index.html" in problem
    assert CSP_NONCE_PLACEHOLDER in problem
    assert "npm run build" in problem


def test_shell_problem_reports_an_unreadable_index_instead_of_raising(tmp_path: Path) -> None:
    problem = shell_problem(_dist(tmp_path, b"\xff\xfe\x00 not utf-8"))
    assert problem is not None
    assert "index.html" in problem
