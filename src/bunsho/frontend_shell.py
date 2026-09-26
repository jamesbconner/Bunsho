"""The built web UI's ``index.html`` and the nonce placeholder it must contain.

A neutral module: both the config validation and the API's static layer import it, so the
config layer never has to import from the API layer.
"""

from __future__ import annotations

from pathlib import Path

CSP_NONCE_PLACEHOLDER = "__CSP_NONCE__"
"""Written into ``frontend/index.html``; the server swaps it for a fresh nonce on every request."""

INDEX_FILE = "index.html"


class StaleShellError(ValueError):
    """``index.html`` has no nonce placeholder: it comes from an older build of the UI."""


def read_shell(frontend_dir: Path) -> str | None:
    """Return the text of ``frontend_dir/index.html``.

    Args:
        frontend_dir: The folder with the built UI.

    Returns:
        The file's text, or ``None`` when the folder has no ``index.html``.

    Raises:
        StaleShellError: The file has no ``CSP_NONCE_PLACEHOLDER``.
        OSError: The file cannot be read.
        UnicodeDecodeError: The file is not UTF-8.
    """
    index = frontend_dir / INDEX_FILE
    if not index.is_file():
        return None
    text = index.read_text(encoding="utf-8")
    if CSP_NONCE_PLACEHOLDER not in text:
        raise StaleShellError(
            f"{index} does not contain the {CSP_NONCE_PLACEHOLDER} placeholder, so it comes from "
            "an older build of the UI; rebuild it with 'npm run build' in frontend/"
        )
    return text


def shell_problem(frontend_dir: Path) -> str | None:
    """Describe what is wrong with the built shell for config validation.

    Args:
        frontend_dir: The folder with the built UI.

    Returns:
        A message, or ``None`` when the shell is fine or there is no ``index.html`` to check.
    """
    try:
        read_shell(frontend_dir)
    except StaleShellError as exc:
        return str(exc)
    except (OSError, UnicodeDecodeError) as exc:
        return f"{frontend_dir / INDEX_FILE} cannot be read ({type(exc).__name__})"
    return None
