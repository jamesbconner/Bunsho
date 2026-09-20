"""Integration tests must fail, not skip, when the CI environment variable is set."""

import pytest

pytest_plugins = ["pytester"]

_TEST_FILE = """
import pytest

@pytest.mark.integration
def test_needs_the_deck():
    pytest.skip("deck not available")

def test_plain_skip_is_left_alone():
    pytest.skip("not an integration test")
"""


def _project(pytester: pytest.Pytester) -> None:
    pytester.makeini("[pytest]\nmarkers =\n    integration: cross-boundary test\n")
    pytester.makeconftest("from tests.conftest import pytest_runtest_makereport  # noqa: F401\n")
    pytester.makepyfile(test_sample=_TEST_FILE)


def test_a_skipped_integration_test_fails_under_ci(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CI", "true")
    _project(pytester)
    result = pytester.runpytest()
    result.assert_outcomes(failed=1, skipped=1)
    result.stdout.fnmatch_lines(["*skipped under CI*deck not available*"])


def test_a_skipped_integration_test_stays_skipped_locally(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("CI", raising=False)
    _project(pytester)
    pytester.runpytest().assert_outcomes(skipped=2)


_SETUP_SKIPS_FILE = """
import pytest

pytestmark = pytest.mark.integration

@pytest.fixture(scope="module")
def deck():
    pytest.skip("fixture: deck missing")

def test_fixture_skip_first(deck):
    pass

def test_fixture_skip_second(deck):
    pass

@pytest.mark.skipif(True, reason="marker: jamdict missing")
def test_skipif_marker():
    pass

@pytest.mark.xfail(reason="known bug")
def test_xfail_is_not_a_skip():
    assert False
"""


def test_setup_skips_and_module_marks_are_covered_under_ci(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CI", "1")
    pytester.makeini("[pytest]\nmarkers =\n    integration: cross-boundary test\n")
    pytester.makeconftest("from tests.conftest import pytest_runtest_makereport  # noqa: F401\n")
    pytester.makepyfile(test_setup=_SETUP_SKIPS_FILE)
    result = pytester.runpytest()
    result.assert_outcomes(errors=3, xfailed=1)
    result.stdout.fnmatch_lines(["*skipped under CI*fixture: deck missing*"])
    result.stdout.fnmatch_lines(["*skipped under CI*marker: jamdict missing*"])
