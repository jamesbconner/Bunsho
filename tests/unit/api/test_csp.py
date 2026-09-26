import base64

import pytest

from bunsho.api.csp import (
    CSP_HEADER,
    CSP_REPORT_ONLY_HEADER,
    DEFAULT_POLICY,
    DOCS_PATHS,
    DOCS_POLICY,
    NONCE_SCOPE_KEY,
    generate_nonce,
    header_name,
    shell_policy,
)

NONCE = "dGVzdC1ub25jZS0xMjM0NQ=="


def test_the_shell_policy_is_exact() -> None:
    assert shell_policy(NONCE) == (
        "default-src 'none'; script-src 'self'; "
        f"style-src 'self' 'nonce-{NONCE}'; "
        "img-src 'self'; font-src 'self'; connect-src 'self'; "
        "base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
    )


def test_the_shell_policy_never_allows_inline_or_eval() -> None:
    policy = shell_policy(NONCE)
    assert "unsafe-inline" not in policy
    assert "unsafe-eval" not in policy


def test_the_default_policy_is_exact() -> None:
    assert DEFAULT_POLICY == "default-src 'none'; frame-ancestors 'none'"


def test_the_docs_policy_is_exact() -> None:
    assert DOCS_POLICY == (
        "default-src 'none'; "
        "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
        "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com; "
        "img-src 'self' data: https://fastapi.tiangolo.com; "
        "font-src https://fonts.gstatic.com; "
        "worker-src blob:; "
        "connect-src 'self'; "
        "frame-ancestors 'none'"
    )


def test_the_docs_paths_are_the_three_fastapi_pages() -> None:
    assert frozenset({"/docs", "/redoc", "/docs/oauth2-redirect"}) == DOCS_PATHS


@pytest.mark.parametrize("bad", ["", "a b", "x'; script-src *", "abc\n", "a-b_c", "=abc"])
def test_a_nonce_that_is_not_base64_is_refused(bad: str) -> None:
    with pytest.raises(ValueError, match="nonce"):
        shell_policy(bad)


def test_header_names() -> None:
    assert header_name(False) == CSP_HEADER == "Content-Security-Policy"
    assert header_name(True) == CSP_REPORT_ONLY_HEADER == "Content-Security-Policy-Report-Only"


def test_the_scope_key_is_namespaced() -> None:
    assert NONCE_SCOPE_KEY == "bunsho.csp_nonce"


def test_generated_nonces_are_16_random_bytes_of_valid_base64() -> None:
    nonce = generate_nonce()
    assert len(base64.b64decode(nonce, validate=True)) == 16
    assert shell_policy(nonce)  # accepted by the policy builder
    assert len({generate_nonce() for _ in range(50)}) == 50
