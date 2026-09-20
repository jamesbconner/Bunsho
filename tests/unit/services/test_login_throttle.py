import pytest

from bunsho.services.login_throttle import LoginThrottle


class _Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_allows_until_the_failure_limit_is_reached() -> None:
    clock = _Clock()
    throttle = LoginThrottle(max_failures=3, window_seconds=60, clock=clock)
    for _ in range(2):
        throttle.record_failure("10.0.0.1")
        assert throttle.retry_after("10.0.0.1") is None
    throttle.record_failure("10.0.0.1")
    assert throttle.retry_after("10.0.0.1") == pytest.approx(60.0)


def test_wait_shrinks_and_expires_with_the_window() -> None:
    clock = _Clock()
    throttle = LoginThrottle(max_failures=2, window_seconds=60, clock=clock)
    throttle.record_failure("k")
    throttle.record_failure("k")
    clock.now += 45
    assert throttle.retry_after("k") == pytest.approx(15.0)
    clock.now += 16
    assert throttle.retry_after("k") is None


def test_keys_are_independent_and_reset_clears() -> None:
    clock = _Clock()
    throttle = LoginThrottle(max_failures=1, window_seconds=60, clock=clock)
    throttle.record_failure("a")
    assert throttle.retry_after("a") is not None
    assert throttle.retry_after("b") is None
    throttle.reset("a")
    assert throttle.retry_after("a") is None
    throttle.reset("never-seen")  # must not raise
