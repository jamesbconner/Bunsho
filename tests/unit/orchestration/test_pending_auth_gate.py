import pytest

from bunsho.orchestration.pending_auth_gate import MAX_PENDING_AUTH, PendingAuthGate


def test_the_default_limit_is_the_module_constant() -> None:
    gate = PendingAuthGate()
    admitted = sum(gate.try_enter() for _ in range(MAX_PENDING_AUTH + 5))
    assert admitted == MAX_PENDING_AUTH


def test_it_admits_up_to_the_limit_and_refuses_beyond_it() -> None:
    gate = PendingAuthGate(limit=2)
    assert [gate.try_enter() for _ in range(4)] == [True, True, False, False]
    assert gate.pending == 2


def test_leaving_frees_a_slot() -> None:
    gate = PendingAuthGate(limit=1)
    assert gate.try_enter()
    assert not gate.try_enter()
    gate.leave()
    assert gate.pending == 0
    assert gate.try_enter()


def test_a_refused_entry_does_not_take_a_slot() -> None:
    gate = PendingAuthGate(limit=1)
    assert gate.try_enter()
    assert not gate.try_enter()
    gate.leave()
    assert gate.pending == 0


def test_leaving_when_nothing_is_pending_is_harmless() -> None:
    gate = PendingAuthGate(limit=1)
    gate.leave()
    assert gate.pending == 0
    assert gate.try_enter()
    assert not gate.try_enter()


@pytest.mark.parametrize("limit", [0, -1])
def test_a_limit_below_one_is_rejected(limit: int) -> None:
    with pytest.raises(ValueError, match="limit"):
        PendingAuthGate(limit=limit)
