# Per-Type Enable Switches and a Kana Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A learner can switch each of kana, kanji and vocabulary off for new cards, and can make kanji and vocabulary wait until enough kana is learned, all from the Settings page.

**Architecture:** Two small objects (`type_enabled`, `kana_gate`) join the `ReviewSettings` document. A pure service, `type_availability`, turns settings plus the kana catalog and card states into "may this type introduce new cards, and if not why". `ReviewSessionOrchestrator._plan` asks it once and gives a blocked type no new cards; policies, the scheduler and due reviews are untouched. The Settings form gains the switches and one threshold field, and the frontend's 422 error mapping switches from last-name keys to dotted paths so `kana`/`kanji`/`vocab` stop colliding.

**Tech Stack:** Python 3.13, pydantic v2, FastAPI, pytest; React 19, Mantine 9, TypeScript, Vitest, msw; `openapi-typescript` for generated types.

**Spec:** `docs/superpowers/specs/2026-09-23-bunsho-type-gating-design.md` (issue #20). Read it first.

**Spec clarifications** (small refinements the plan makes; the spec's behaviour is otherwise unchanged):
- `Availability` carries a third defaulted field, `kana_share: float | None`, so the debug log line can show the share the gate compared. The spec's two fields are unchanged.
- The spec says the gate switches are disabled while kana is off. The plan disables only a gate switch that is **off** (it cannot be turned on without kana); one that is already **on** stays operable so the learner can turn it off. Otherwise a gate switched on and then kana switched off would be a dead end.
- The spec says the threshold input is shown only while a gate is on. The plan also shows it when it has a validation error, so an invalid value hidden by turning the gates off cannot make Save fail silently.

**Branch:** implement on `feat/plan-type-gating`, created from `origin/main` once the docs PR (spec + plan) is merged; if it is not merged yet, branch from `docs/plan-type-gating`.

## Global Constraints

- Defaults must keep today's behaviour exactly: `type_enabled` all `true`; `kana_gate` `kanji=false`, `vocab=false`, `threshold=0.80`. A stored settings document without the new keys must load unchanged. No database migration.
- Settings shape is objects like `NewLimits`: `type_enabled: {kana, kanji, vocab}` (booleans) and `kana_gate: {kanji, vocab, threshold}`; both with `extra="forbid"` and `json_schema_serialization_defaults_required=True`. `type_enabled` is declared **before** `kana_gate` in `ReviewSettings`.
- The kana share is Review-state kana cards over **all** kana cards (both directions, hiragana and katakana together). Only `SchedState.REVIEW` counts. An empty kana catalog leaves the gate open. Threshold comparison is `share >= threshold`.
- The gate is live, not latched: no persisted state. A disabled type or closed gate only stops **new** cards; due reviews are never affected. Kana is never gated.
- A gate switched on while kana is disabled is rejected with a 422 whose `loc` is `["body", "kana_gate"]` and message `Turn kana on, or turn off the kana gate: kanji and vocabulary cannot wait for kana that is never introduced.` (a `PydanticCustomError`, so there is no "Value error, " prefix). All three types disabled is allowed (reviews-only mode).
- The gate does not depend on `new_card_policy` or `mastery_threshold`.
- Version 1.0.0 → 1.1.0 across `pyproject.toml`, `src/bunsho/__init__.py`, `uv.lock`, `frontend/package.json`, `frontend/package-lock.json`, the OpenAPI snapshot, and `CHANGELOG.md`. No tag, no release.
- Python: ruff line length 100, Google-style docstrings on public items, `mypy --strict` on `src`, coverage floor 90, no new dependencies. Frontend: strict TypeScript, Prettier, ESLint, no new dependencies. Latest versions only; add nothing.
- Commits: conventional commits, stage explicit paths only, subject then the trailer as its own paragraph: `git commit -m "<subject>" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"`. Never stage `.gitignore`, `.github/`, `.python-version`, `.superpowers/`, `.env.example`.
- Windows/Git Bash: `unset VIRTUAL_ENV` before any `uv` command; quote the `Bunshō` path; `PYTHONIOENCODING=utf-8` when printing Japanese; add an import in the same edit as its first use (a formatter hook can drop unused imports); after writing files check `git diff --stat` for stray CRLF and run `npm run format` in `frontend/` for TypeScript. One `test_main.py` test may fail locally if a real `.env` sits in the repo root; CI has none, so ignore it only if it is that test.
- Working directory for commands is the repo root `D:/Documents/Code/Bunshō` unless a step says `cd frontend`.

## Review Focus

Failure modes the spec implies that no headline test names; each has a test in the owning task.

1. **An old stored settings document** (no `type_enabled`/`kana_gate`) must load and behave as before. Task 1, `test_a_document_saved_before_the_type_switches_existed_loads_with_todays_behaviour`.
2. **A missing kana deck** (empty kana catalog) with a gate on must not block kanji/vocab forever. Task 2, `test_an_empty_kana_catalog_leaves_the_gate_open`.
3. **A cleared or invalid threshold field that is hidden** (gates turned off after clearing it) must not make Save silently do nothing. Task 5, `reveals a hidden threshold field that is invalid when Save is pressed`.
4. **Gate switched on, then kana switched off in the form** must not leave a switch the user cannot turn off. Task 5, `keeps a switched-on gate operable after kana is switched off`.
5. **A type disabled while some of its cards are already learning** must still serve them when due. Task 3, `test_a_disabled_type_still_serves_the_cards_it_already_introduced`.
6. **Server 422s whose last path segment is `kana`, `kanji` or `vocab`** must land on the right field. Task 4, the `placeServerErrors` and `errors.ts` path tests.

---

## File Structure

| File | Change | Responsibility |
|---|---|---|
| `src/bunsho/models/review_settings.py` | modify | `TypeEnabled`, `KanaGate`, the two `ReviewSettings` fields, the gate-needs-kana validator |
| `src/bunsho/services/type_availability.py` | create | the pure rule: `BlockReason`, `Availability`, `kana_share`, `type_availability` |
| `src/bunsho/orchestration/review_session.py` | modify | `_plan` asks the service and blocks types |
| `frontend/openapi.json`, `frontend/src/api/schema.d.ts` | regenerate | committed API snapshot and generated types |
| `frontend/src/api/errors.ts` | modify | key 422 messages by dotted path below `body` |
| `frontend/src/features/settings/settingsForm.ts` | modify | form values, conversion, validation, server-error placement |
| `frontend/src/features/settings/SettingsPage.tsx` | modify | switches, "Kana first" group, disabled limits |
| `frontend/src/test/fixtures.ts` | modify | `makeSettings` carries the new fields |
| tests | modify/create | see each task |
| `pyproject.toml`, `src/bunsho/__init__.py`, `uv.lock`, `frontend/package.json`, `frontend/package-lock.json`, `CHANGELOG.md`, `README.md`, `TODO.md` | modify | 1.1.0 release and docs (Task 6) |

The plan deliberately puts the OpenAPI/type regeneration and the mechanical frontend plumbing in Task 1, so every task ends green (schema regeneration makes the new fields required in the generated types, which would otherwise break the frontend build mid-plan).

---

### Task 1: The settings document carries `type_enabled` and `kana_gate`

**Files:**
- Modify: `src/bunsho/models/review_settings.py`
- Modify: `tests/unit/models/test_review_settings.py`
- Modify: `tests/unit/services/test_review_settings_service.py`
- Modify: `tests/unit/api/test_settings_routes.py`
- Regenerate: `frontend/openapi.json`, `frontend/src/api/schema.d.ts`
- Modify: `frontend/src/test/fixtures.ts`
- Modify: `frontend/src/features/settings/settingsForm.ts`
- Modify: `frontend/src/features/settings/settingsForm.test.ts`

**Interfaces:**
- Produces (Python): `TypeEnabled(kana: bool = True, kanji: bool = True, vocab: bool = True)` with `.for_type(item_type: ItemType) -> bool`; `KanaGate(kanji: bool = False, vocab: bool = False, threshold: float = 0.80)` with `.gates(item_type: ItemType) -> bool` (kana → `False`); `ReviewSettings.type_enabled: TypeEnabled`, `ReviewSettings.kana_gate: KanaGate`.
- Produces (TypeScript): `SettingsFormValues.type_enabled: { kana: boolean; kanji: boolean; vocab: boolean }` and `SettingsFormValues.kana_gate: { kanji: boolean; vocab: boolean; threshold_percent: number | string }`; `RECOMMENDED_SETTINGS` and `makeSettings()` include both objects; `toFormValues`/`toRequest`/dirty-checking cover them.

- [ ] **Step 1: Write the failing model tests**

In `tests/unit/models/test_review_settings.py`, extend the import from `bunsho.models.review_settings` to include `KanaGate` and `TypeEnabled`, then append:

```python
def test_type_switches_and_the_kana_gate_default_to_todays_behaviour() -> None:
    settings = ReviewSettings()
    assert settings.type_enabled == TypeEnabled(kana=True, kanji=True, vocab=True)
    assert settings.kana_gate == KanaGate(kanji=False, vocab=False, threshold=0.80)


def test_type_switches_are_looked_up_by_item_type() -> None:
    enabled = TypeEnabled(kana=True, kanji=False, vocab=True)
    assert [enabled.for_type(t) for t in ItemType] == [True, False, True]


def test_only_kanji_and_vocab_can_be_gated() -> None:
    gate = KanaGate(kanji=True, vocab=False)
    assert [gate.gates(t) for t in ItemType] == [False, True, False]
    assert [KanaGate().gates(t) for t in ItemType] == [False, False, False]


@pytest.mark.parametrize("threshold", [0.0, 0.5, 1.0])
def test_the_gate_threshold_accepts_a_fraction(threshold: float) -> None:
    assert KanaGate(threshold=threshold).threshold == threshold


@pytest.mark.parametrize("threshold", [-0.01, 1.01])
def test_the_gate_threshold_rejects_anything_else(threshold: float) -> None:
    with pytest.raises(ValidationError):
        KanaGate(threshold=threshold)


@pytest.mark.parametrize("gate", [{"kanji": True}, {"vocab": True}, {"kanji": True, "vocab": True}])
def test_a_gate_needs_kana_to_be_enabled(gate: dict[str, bool]) -> None:
    with pytest.raises(ValidationError, match="Turn kana on") as caught:
        ReviewSettings(type_enabled=TypeEnabled(kana=False), kana_gate=KanaGate(**gate))
    assert [error["loc"] for error in caught.value.errors()] == [("kana_gate",)]
    assert caught.value.errors()[0]["type"] == "kana_gate_needs_kana"


def test_kana_can_be_off_while_no_gate_is_on_and_every_type_can_be_off() -> None:
    assert ReviewSettings(type_enabled=TypeEnabled(kana=False)).type_enabled.kana is False
    nothing = TypeEnabled(kana=False, kanji=False, vocab=False)
    assert ReviewSettings(type_enabled=nothing).type_enabled == nothing


def test_the_gate_check_is_skipped_when_the_switches_are_themselves_invalid() -> None:
    with pytest.raises(ValidationError) as caught:
        ReviewSettings.model_validate(
            {"type_enabled": {"kana": "maybe"}, "kana_gate": {"kanji": True}}
        )
    assert [error["loc"] for error in caught.value.errors()] == [("type_enabled", "kana")]


def test_unknown_keys_in_the_new_objects_are_rejected() -> None:
    with pytest.raises(ValidationError):
        TypeEnabled.model_validate({"kana": True, "surprise": True})
    with pytest.raises(ValidationError):
        KanaGate.model_validate({"surprise": True})
```

- [ ] **Step 2: Write the failing service and API tests**

In `tests/unit/services/test_review_settings_service.py` extend the import to `from bunsho.models.review_settings import KanaGate, NewCardPolicyName, ReviewSettings, TypeEnabled` and append:

```python
def test_a_document_saved_before_the_type_switches_existed_loads_with_todays_behaviour(
    tmp_path: Path,
) -> None:
    async def scenario(db: ProgressDatabase) -> None:
        repo = ProgressRepository(db)
        await repo.set_setting(
            SETTINGS_KEY, '{"new_card_policy": "mastery_unlock", "target_retention": 0.85}'
        )
        loaded = await ReviewSettingsService(repo, LOGGER).load()
        assert loaded == ReviewSettings(
            new_card_policy=NewCardPolicyName.MASTERY_UNLOCK, target_retention=0.85
        )
        assert loaded.type_enabled == TypeEnabled()
        assert loaded.kana_gate == KanaGate()

    run_with_database(tmp_path, scenario)
```

In `tests/unit/api/test_settings_routes.py` append:

```python
def test_the_type_switches_and_kana_gate_round_trip(
    review_client: TestClient, review_headers: Headers
) -> None:
    document = ReviewSettings().model_dump(mode="json")
    document["type_enabled"] = {"kana": True, "kanji": False, "vocab": True}
    document["kana_gate"] = {"kanji": False, "vocab": True, "threshold": 0.9}
    saved = review_client.put(SETTINGS, json=document, headers=review_headers)
    assert saved.status_code == 200
    assert saved.json() == document
    assert review_client.get(SETTINGS, headers=review_headers).json() == document


def test_a_gate_with_kana_disabled_is_rejected_at_the_gate_field(
    review_client: TestClient, review_headers: Headers
) -> None:
    good = ReviewSettings().model_dump(mode="json")
    assert review_client.put(SETTINGS, json=good, headers=review_headers).status_code == 200
    bad = {
        **good,
        "type_enabled": {"kana": False, "kanji": True, "vocab": True},
        "kana_gate": {"kanji": True, "vocab": False, "threshold": 0.8},
    }
    response = review_client.put(SETTINGS, json=bad, headers=review_headers)
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert [error["loc"] for error in detail] == [["body", "kana_gate"]]
    assert detail[0]["msg"].startswith("Turn kana on")
    assert review_client.get(SETTINGS, headers=review_headers).json() == good
```

- [ ] **Step 3: Run them to verify they fail**

Run: `unset VIRTUAL_ENV; uv run pytest tests/unit/models/test_review_settings.py tests/unit/services/test_review_settings_service.py tests/unit/api/test_settings_routes.py -q`
Expected: FAIL (`ImportError: cannot import name 'KanaGate'`).

- [ ] **Step 4: Implement the models**

In `src/bunsho/models/review_settings.py` change the pydantic import and add the new one, add the two classes after `NewLimits`, and add the two fields and the validator to `ReviewSettings`:

```python
from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator
from pydantic_core import PydanticCustomError
```

```python
class TypeEnabled(BaseModel):
    """Which item types may introduce new cards. Cards already introduced stay due either way."""

    model_config = ConfigDict(extra="forbid", json_schema_serialization_defaults_required=True)

    kana: bool = True
    kanji: bool = True
    vocab: bool = True

    def for_type(self, item_type: ItemType) -> bool:
        """Return whether ``item_type`` may introduce new cards."""
        match item_type:
            case ItemType.KANA:
                return self.kana
            case ItemType.KANJI:
                return self.kanji
            case ItemType.VOCAB:
                return self.vocab


class KanaGate(BaseModel):
    """Hold new kanji and/or vocabulary back until enough kana is learned.

    Kana is one stage: the share counts every kana card (both directions, hiragana and
    katakana together) that is in the FSRS Review state. ``threshold`` is a fraction from 0 to 1.
    """

    model_config = ConfigDict(extra="forbid", json_schema_serialization_defaults_required=True)

    kanji: bool = False
    vocab: bool = False
    threshold: float = Field(default=0.80, ge=0.0, le=1.0)

    def gates(self, item_type: ItemType) -> bool:
        """Return whether ``item_type`` waits for kana. Kana itself is never gated."""
        match item_type:
            case ItemType.KANA:
                return False
            case ItemType.KANJI:
                return self.kanji
            case ItemType.VOCAB:
                return self.vocab
```

Inside `ReviewSettings`, directly after the `new_limits` line add:

```python
    type_enabled: TypeEnabled = Field(default_factory=TypeEnabled)
    kana_gate: KanaGate = Field(default_factory=KanaGate)
```

and after the `mode_for` method add:

```python
    @field_validator("kana_gate")
    @classmethod
    def _gates_need_kana(cls, gate: KanaGate, info: ValidationInfo) -> KanaGate:
        """Reject a gate that could never open because kana is never introduced.

        Runs after ``type_enabled`` (declared first); if that field itself failed it is absent
        from ``info.data`` and this check is skipped, since its error is already reported.
        """
        enabled = info.data.get("type_enabled")
        if isinstance(enabled, TypeEnabled) and not enabled.kana and (gate.kanji or gate.vocab):
            raise PydanticCustomError(
                "kana_gate_needs_kana",
                "Turn kana on, or turn off the kana gate: kanji and vocabulary cannot wait "
                "for kana that is never introduced.",
            )
        return gate
```

Update the `ReviewSettings` docstring is unnecessary; leave it.

- [ ] **Step 5: Run the Python tests to verify they pass**

Run: `unset VIRTUAL_ENV; uv run pytest tests/unit/models/test_review_settings.py tests/unit/services/test_review_settings_service.py tests/unit/api/test_settings_routes.py -q`
Expected: PASS. (`tests/unit/api/test_openapi_snapshot.py` will fail until Step 6; do not run the whole suite yet.)

- [ ] **Step 6: Regenerate the OpenAPI snapshot and the generated types**

Run:
```
unset VIRTUAL_ENV; uv run python scripts/export_openapi.py
cd frontend && npm run gen:api && cd ..
git diff --stat -- frontend/openapi.json frontend/src/api/schema.d.ts
```
Expected: both files change; `schema.d.ts` now has `TypeEnabled-Input`/`TypeEnabled-Output` and `KanaGate-Input`/`KanaGate-Output` and `type_enabled`/`kana_gate` on `ReviewSettings-Output` and `-Input`. Confirm those schema names exist: `grep -c "KanaGate-Input" frontend/openapi.json` prints a number above 0 (the settings-form test in Step 8 depends on the `-Input` names; if the generator names them differently, use the names it produced).

Run: `unset VIRTUAL_ENV; uv run pytest tests/unit/api -q`
Expected: PASS (including the snapshot and OpenAPI tests).

- [ ] **Step 7: Write the failing frontend conversion tests**

In `frontend/src/features/settings/settingsForm.test.ts`:

Change the test `'round-trips a whole document unchanged'` so its `makeSettings` call also passes the new objects:

```ts
    const settings = makeSettings({
      new_card_policy: 'pinned_levels',
      new_limits: { kana: 0, kanji: 7, vocab: 10_000 },
      rollover_hour: 23,
      active_levels: ['N5', 'N3'],
      type_enabled: { kana: true, kanji: false, vocab: true },
      kana_gate: { kanji: false, vocab: true, threshold: 0.9 },
    });
    expect(toRequest(toFormValues(settings))).toEqual(settings);
```

Add inside `describe('toFormValues and toRequest', ...)`:

```ts
  it('shows the kana gate threshold as a whole percentage and sends it back as a fraction', () => {
    const values = toFormValues(
      makeSettings({ kana_gate: { kanji: true, vocab: false, threshold: 0.85 } }),
    );
    expect(values.kana_gate.threshold_percent).toBe(85);
    expect(values.type_enabled).toEqual({ kana: true, kanji: true, vocab: true });
    const request = toRequest({
      ...values,
      kana_gate: { ...values.kana_gate, threshold_percent: '65' },
    });
    expect(request.kana_gate).toEqual({ kanji: true, vocab: false, threshold: 0.65 });
  });
```

Add inside `describe('isSettingsDirty', ...)`:

```ts
  it('treats a changed type switch or gate field as dirty', () => {
    expect(
      isSettingsDirty(withValues({ type_enabled: { kana: true, kanji: false, vocab: true } }), VALID),
    ).toBe(true);
    expect(
      isSettingsDirty(
        withValues({ kana_gate: { ...VALID.kana_gate, kanji: true } }),
        VALID,
      ),
    ).toBe(true);
    expect(
      isSettingsDirty(
        withValues({ kana_gate: { ...VALID.kana_gate, threshold_percent: '' } }),
        VALID,
      ),
    ).toBe(true);
  });
```

In `describe('RECOMMENDED_SETTINGS', ...)` add after the `limits` constant and inside the block:

```ts
  const enabled = schemas['TypeEnabled-Input']?.properties ?? {};
  const gate = schemas['KanaGate-Input']?.properties ?? {};

  it('matches the type switches and kana gate the API declares', () => {
    expect(RECOMMENDED_SETTINGS.type_enabled.kana).toBe(enabled.kana?.default);
    expect(RECOMMENDED_SETTINGS.type_enabled.kanji).toBe(enabled.kanji?.default);
    expect(RECOMMENDED_SETTINGS.type_enabled.vocab).toBe(enabled.vocab?.default);
    expect(RECOMMENDED_SETTINGS.kana_gate.kanji).toBe(gate.kanji?.default);
    expect(RECOMMENDED_SETTINGS.kana_gate.vocab).toBe(gate.vocab?.default);
    expect(RECOMMENDED_SETTINGS.kana_gate.threshold).toBe(gate.threshold?.default);
  });
```

- [ ] **Step 8: Run them to verify they fail, then implement the plumbing**

Run: `cd frontend && npx vitest run src/features/settings/settingsForm.test.ts`
Expected: FAIL (type errors / missing fields).

Edit `frontend/src/test/fixtures.ts`, in `makeSettings` add after `new_limits`:

```ts
    type_enabled: { kana: true, kanji: true, vocab: true },
    kana_gate: { kanji: false, vocab: false, threshold: 0.8 },
```

Edit `frontend/src/features/settings/settingsForm.ts`:

In `SettingsFormValues` add after `new_limits`:

```ts
  type_enabled: { kana: boolean; kanji: boolean; vocab: boolean };
  /** The threshold is a whole percentage here (the API stores a fraction), `string` while cleared. */
  kana_gate: { kanji: boolean; vocab: boolean; threshold_percent: number | string };
```

In `RECOMMENDED_SETTINGS` add after `new_limits`:

```ts
  type_enabled: { kana: true, kanji: true, vocab: true },
  kana_gate: { kanji: false, vocab: false, threshold: 0.8 },
```

In `toFormValues` add after `new_limits`:

```ts
    type_enabled: { ...settings.type_enabled },
    kana_gate: {
      kanji: settings.kana_gate.kanji,
      vocab: settings.kana_gate.vocab,
      threshold_percent: toPercent(settings.kana_gate.threshold),
    },
```

In `toRequest` add after `new_limits`:

```ts
    type_enabled: { ...values.type_enabled },
    kana_gate: {
      kanji: values.kana_gate.kanji,
      vocab: values.kana_gate.vocab,
      threshold: toFraction(Number(values.kana_gate.threshold_percent)),
    },
```

In `canonical`, add these entries after the three `new_limits` strings:

```ts
    values.type_enabled.kana,
    values.type_enabled.kanji,
    values.type_enabled.vocab,
    values.kana_gate.kanji,
    values.kana_gate.vocab,
    String(values.kana_gate.threshold_percent),
```

Run: `cd frontend && npm run format && npx vitest run src/features/settings && npm run build`
Expected: PASS (all settings tests, including the existing `SettingsPage` tests, since the fixture and form now agree) and a clean type-check/build.

- [ ] **Step 9: Commit**

```bash
git add src/bunsho/models/review_settings.py tests/unit/models/test_review_settings.py tests/unit/services/test_review_settings_service.py tests/unit/api/test_settings_routes.py frontend/openapi.json frontend/src/api/schema.d.ts frontend/src/test/fixtures.ts frontend/src/features/settings/settingsForm.ts frontend/src/features/settings/settingsForm.test.ts
git commit -m "feat(settings): add type_enabled and kana_gate to the settings document" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 2: The availability service

**Files:**
- Create: `src/bunsho/services/type_availability.py`
- Create: `tests/unit/services/test_type_availability.py`

**Interfaces:**
- Consumes: `ReviewSettings`, `TypeEnabled.for_type`, `KanaGate.gates`/`.threshold` (Task 1); `CatalogEntry`, `CardKey`, `SchedState`, `ItemType`, `DIRECTIONS_BY_TYPE` from `bunsho.models.review`.
- Produces:
  - `BlockReason(StrEnum)`: `DISABLED = "disabled"`, `WAITING_FOR_KANA = "waiting_for_kana"`.
  - `Availability(allowed: bool, reason: BlockReason | None = None, kana_share: float | None = None)` (frozen dataclass).
  - `kana_share(kana_entries: Sequence[CatalogEntry], states: Mapping[CardKey, SchedState]) -> float | None` (`None` when there are no kana cards).
  - `type_availability(settings: ReviewSettings, kana_entries: Sequence[CatalogEntry], states: Mapping[CardKey, SchedState]) -> dict[ItemType, Availability]`.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/services/test_type_availability.py`:

```python
from collections.abc import Mapping, Sequence

import pytest

from bunsho.models.review import CardDirection, CardKey, CatalogEntry, ItemType, SchedState
from bunsho.models.review_settings import KanaGate, ReviewSettings, TypeEnabled
from bunsho.services.type_availability import (
    Availability,
    BlockReason,
    kana_share,
    type_availability,
)

KANA, KANJI, VOCAB = ItemType.KANA, ItemType.KANJI, ItemType.VOCAB
G2S, S2G = CardDirection.GLYPH_TO_SOUND, CardDirection.SOUND_TO_GLYPH


def kana_entries(count: int) -> list[CatalogEntry]:
    return [CatalogEntry(f"kana:{i}", KANA, None, i) for i in range(count)]


def learned(entries: Sequence[CatalogEntry], cards: int) -> dict[CardKey, SchedState]:
    """The first ``cards`` kana cards (entry by entry, both directions) in Review."""
    keys = [CardKey(entry.item_id, direction) for entry in entries for direction in (G2S, S2G)]
    return {key: SchedState.REVIEW for key in keys[:cards]}


def gated(threshold: float = 0.8, **switches: TypeEnabled) -> ReviewSettings:
    gate = KanaGate(kanji=True, vocab=True, threshold=threshold)
    return ReviewSettings(kana_gate=gate, **switches)


def test_everything_is_allowed_with_the_default_settings() -> None:
    result = type_availability(ReviewSettings(), kana_entries(5), {})
    assert result == {KANA: Availability(True), KANJI: Availability(True), VOCAB: Availability(True)}


def test_a_disabled_type_is_blocked_even_with_no_gate() -> None:
    settings = ReviewSettings(type_enabled=TypeEnabled(kanji=False))
    result = type_availability(settings, kana_entries(5), {})
    assert result[KANJI] == Availability(False, BlockReason.DISABLED)
    assert result[KANA].allowed and result[VOCAB].allowed


def test_every_type_can_be_disabled() -> None:
    off = TypeEnabled(kana=False, kanji=False, vocab=False)
    result = type_availability(ReviewSettings(type_enabled=off), [], {})
    assert {t: a.reason for t, a in result.items()} == {t: BlockReason.DISABLED for t in ItemType}


def test_a_type_that_is_both_disabled_and_gated_reports_disabled() -> None:
    settings = gated(type_enabled=TypeEnabled(vocab=False))
    result = type_availability(settings, kana_entries(5), {})
    assert result[VOCAB] == Availability(False, BlockReason.DISABLED)


def test_a_gated_type_waits_for_kana() -> None:
    result = type_availability(gated(), kana_entries(5), {})
    assert result[KANJI] == Availability(False, BlockReason.WAITING_FOR_KANA, 0.0)
    assert result[VOCAB] == Availability(False, BlockReason.WAITING_FOR_KANA, 0.0)


def test_kana_is_never_gated() -> None:
    result = type_availability(gated(), kana_entries(5), {})
    assert result[KANA] == Availability(True)


def test_only_the_gated_type_waits() -> None:
    settings = ReviewSettings(kana_gate=KanaGate(kanji=True, vocab=False))
    result = type_availability(settings, kana_entries(5), {})
    assert result[KANJI].allowed is False
    assert result[VOCAB] == Availability(True)


@pytest.mark.parametrize(
    ("learned_cards", "threshold", "expected"),
    [
        (8, 0.8, True),  # exactly at the threshold opens the gate
        (7, 0.8, False),  # just below
        (0, 0.0, True),  # a threshold of 0 is always open
        (10, 1.0, True),
        (9, 1.0, False),  # 1.0 needs every kana card in Review
        (0, 0.01, False),
    ],
)
def test_the_gate_opens_at_the_threshold(
    learned_cards: int, threshold: float, expected: bool
) -> None:
    entries = kana_entries(5)  # 10 kana cards: 5 entries x 2 directions
    result = type_availability(gated(threshold), entries, learned(entries, learned_cards))
    assert result[KANJI].allowed is expected
    assert result[VOCAB].allowed is expected


@pytest.mark.parametrize("state", [SchedState.NEW, SchedState.LEARNING, SchedState.RELEARNING])
def test_only_the_review_state_counts_as_learned(state: SchedState) -> None:
    entries = kana_entries(5)
    states = {key: state for key in learned(entries, 10)}
    assert type_availability(gated(), entries, states)[KANJI].allowed is False


def test_both_directions_of_every_kana_count() -> None:
    entries = kana_entries(3)  # 6 cards
    only_glyph_to_sound = {CardKey(e.item_id, G2S): SchedState.REVIEW for e in entries}
    assert kana_share(entries, only_glyph_to_sound) == 0.5
    assert type_availability(gated(0.5), entries, only_glyph_to_sound)[KANJI].allowed is True
    assert type_availability(gated(0.6), entries, only_glyph_to_sound)[KANJI].allowed is False


def test_an_empty_kana_catalog_leaves_the_gate_open() -> None:
    result = type_availability(gated(1.0), [], {})
    assert result[KANJI] == Availability(True, kana_share=None)
    assert result[VOCAB] == Availability(True, kana_share=None)


def test_the_share_is_measured_only_when_a_gate_is_on() -> None:
    class Untouchable(Sequence[CatalogEntry]):
        def __len__(self) -> int:
            raise AssertionError("the kana catalog was measured with no gate on")

        def __getitem__(self, index):  # type: ignore[no-untyped-def]
            raise AssertionError("the kana catalog was measured with no gate on")

    states: Mapping[CardKey, SchedState] = {}
    assert type_availability(ReviewSettings(), Untouchable(), states)[KANJI].allowed is True


def test_kana_share_is_none_without_kana_and_a_fraction_otherwise() -> None:
    assert kana_share([], {}) is None
    entries = kana_entries(2)  # 4 cards
    assert kana_share(entries, learned(entries, 1)) == 0.25
```

- [ ] **Step 2: Run to verify it fails**

Run: `unset VIRTUAL_ENV; uv run pytest tests/unit/services/test_type_availability.py -q`
Expected: FAIL (`ModuleNotFoundError: No module named 'bunsho.services.type_availability'`).

- [ ] **Step 3: Implement the service**

Create `src/bunsho/services/type_availability.py`:

```python
"""Which item types may introduce new cards right now: the enable switches and the kana gate.

Pure and synchronous, so the rule is testable without a database. The review session asks it
once per daily plan; policies never see it (a policy only sees its own type's catalog, so it
could not measure kana while choosing kanji).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum

from bunsho.models.review import DIRECTIONS_BY_TYPE, CardKey, CatalogEntry, ItemType, SchedState
from bunsho.models.review_settings import ReviewSettings


class BlockReason(StrEnum):
    """Why a type may not introduce new cards."""

    DISABLED = "disabled"
    WAITING_FOR_KANA = "waiting_for_kana"


@dataclass(frozen=True, slots=True)
class Availability:
    """Whether a type may introduce new cards and, when it may not, why."""

    allowed: bool
    reason: BlockReason | None = None
    kana_share: float | None = None
    """The kana share the gate compared with its threshold; ``None`` when no gate was checked."""


_OPEN = Availability(allowed=True)


def kana_share(
    kana_entries: Sequence[CatalogEntry], states: Mapping[CardKey, SchedState]
) -> float | None:
    """Return the share of kana cards in the Review state, or ``None`` when there are none.

    Kana is one stage: every entry, both directions, hiragana and katakana together.

    Args:
        kana_entries: Every kana catalog entry.
        states: Scheduling state of every card that has one.

    Returns:
        A fraction from 0 to 1, or ``None`` if the catalog has no kana cards.
    """
    directions = DIRECTIONS_BY_TYPE[ItemType.KANA]
    total = len(kana_entries) * len(directions)
    if total == 0:
        return None
    learned = sum(
        1
        for entry in kana_entries
        for direction in directions
        if states.get(CardKey(entry.item_id, direction)) is SchedState.REVIEW
    )
    return learned / total


def type_availability(
    settings: ReviewSettings,
    kana_entries: Sequence[CatalogEntry],
    states: Mapping[CardKey, SchedState],
) -> dict[ItemType, Availability]:
    """Decide, per item type, whether it may introduce new cards.

    A type is blocked when it is switched off, or when its kana gate is on and the kana share is
    below the threshold. An empty kana catalog leaves a gate open so a missing kana deck cannot
    block kanji and vocabulary forever. The share is measured at most once, and only when a gate
    is on. Due reviews are not this function's concern and are never affected.

    Args:
        settings: The review settings (switches, gate and threshold).
        kana_entries: Every kana catalog entry (only read when a gate is on).
        states: Scheduling state of every card that has one.

    Returns:
        An ``Availability`` for every item type.
    """
    result: dict[ItemType, Availability] = {}
    share: float | None = None
    measured = False
    for item_type in ItemType:
        if not settings.type_enabled.for_type(item_type):
            result[item_type] = Availability(False, BlockReason.DISABLED)
            continue
        if not settings.kana_gate.gates(item_type):
            result[item_type] = _OPEN
            continue
        if not measured:
            share, measured = kana_share(kana_entries, states), True
        if share is None or share >= settings.kana_gate.threshold:
            result[item_type] = Availability(True, kana_share=share)
        else:
            result[item_type] = Availability(False, BlockReason.WAITING_FOR_KANA, share)
    return result
```

- [ ] **Step 4: Run to verify it passes, then lint and type-check**

Run:
```
unset VIRTUAL_ENV; uv run pytest tests/unit/services/test_type_availability.py -q
unset VIRTUAL_ENV; uv run ruff check src tests && uv run ruff format --check src tests && uv run mypy src/
```
Expected: PASS. If `ruff format --check` complains, run `uv run ruff format src tests` and re-check (long lines in tests are wrapped by the formatter; long strings are not, so split those by hand). Keep the `# type: ignore[no-untyped-def]` on the test's `__getitem__`; mypy only checks `src`.

- [ ] **Step 5: Commit**

```bash
git add src/bunsho/services/type_availability.py tests/unit/services/test_type_availability.py
git commit -m "feat(services): add the type availability rule (enable switches and kana gate)" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 3: The daily plan uses the availability service

**Files:**
- Modify: `src/bunsho/orchestration/review_session.py` (imports, and `_plan` around lines 292-310)
- Modify: `tests/unit/orchestration/test_review_session.py`

**Interfaces:**
- Consumes: `type_availability(settings, kana_entries, states) -> dict[ItemType, Availability]`, `Availability.allowed`/`.reason`/`.kana_share` (Task 2); `KanaGate`, `TypeEnabled` (Task 1).
- Produces: behaviour only: a blocked type has `new_keys[type] == []` (so `counts.new_remaining` is 0 for it and `pick_new` skips it); one debug log line per blocked type: `type_blocked type=<type> reason=<reason> kana_share=<share> threshold=<threshold>`.

- [ ] **Step 1: Write the failing tests**

In `tests/unit/orchestration/test_review_session.py`, extend the settings import to include `KanaGate` and `TypeEnabled`:

```python
from bunsho.models.review_settings import (
    KanaGate,
    NewCardPolicyName,
    NewLimits,
    ReviewModeName,
    ReviewSettings,
    TypeEnabled,
)
```

Append (the helpers `answer`, `next_card`, `key_of`, the constants `A`, `B`, and the imports `make_kana`, `make_kanji`, `Grade`, `SchedState`, `TypeCounts`, `logging`, `LOGGER_NAME` already exist in this file):

```python
KANA_A, KANA_I = make_kana("あ", "a"), make_kana("い", "i")  # 4 kana cards
GATED = ReviewSettings(kana_gate=KanaGate(kanji=True, vocab=True, threshold=0.8))


async def learn_kana_cards(stack: ReviewStack, count: int) -> None:
    """Answer ``count`` new kana cards Easy, which puts each straight into the Review state."""
    for _ in range(count):
        card = await next_card(stack)
        assert card.item_type is ItemType.KANA
        await answer(stack, card, Grade.EASY)
    states = await stack.progress.card_states()
    kana_states = [state for key, state in states.items() if key.item_type is ItemType.KANA]
    assert kana_states == [SchedState.REVIEW] * count


def test_a_gated_stack_offers_only_kana_at_first(tmp_path: Path) -> None:
    async def scenario(db: ProgressDatabase) -> None:
        stack = build_review_stack(
            tmp_path, db, kana=[KANA_A, KANA_I], kanji=[make_kanji("日")], vocab=[A]
        )
        await stack.settings.save(GATED)
        result = await stack.orchestrator.next_card()
        assert result.card is not None
        assert result.card.item_type is ItemType.KANA
        assert result.counts.new_remaining == TypeCounts(kana=4, kanji=0, vocab=0)

    run_with_database(tmp_path, scenario)


def test_kanji_and_vocab_start_once_the_kana_share_reaches_the_threshold(tmp_path: Path) -> None:
    async def scenario(db: ProgressDatabase) -> None:
        stack = build_review_stack(
            tmp_path, db, kana=[KANA_A, KANA_I], kanji=[make_kanji("日")], vocab=[A]
        )
        await stack.settings.save(GATED)
        await learn_kana_cards(stack, 4)
        result = await stack.orchestrator.next_card()
        assert result.card is not None
        assert result.card.item_type in {ItemType.KANJI, ItemType.VOCAB}
        assert result.counts.new_remaining == TypeCounts(kana=0, kanji=3, vocab=2)

    run_with_database(tmp_path, scenario)


def test_the_gate_stays_shut_below_the_threshold_and_follows_the_setting(tmp_path: Path) -> None:
    async def scenario(db: ProgressDatabase) -> None:
        stack = build_review_stack(
            tmp_path, db, kana=[KANA_A, KANA_I], kanji=[make_kanji("日")], vocab=[A]
        )
        await stack.settings.save(GATED)
        await learn_kana_cards(stack, 3)  # 3 of 4 kana cards = 0.75 < 0.8
        below = await stack.orchestrator.next_card()
        assert below.card is not None
        assert below.card.item_type is ItemType.KANA  # the last kana card, not kanji or vocab
        assert below.counts.new_remaining == TypeCounts(kana=1, kanji=0, vocab=0)
        await stack.settings.save(
            ReviewSettings(kana_gate=KanaGate(kanji=True, vocab=True, threshold=0.75))
        )
        at = await stack.orchestrator.next_card()
        assert at.counts.new_remaining == TypeCounts(kana=1, kanji=3, vocab=2)

    run_with_database(tmp_path, scenario)


def test_a_gate_does_not_affect_kana(tmp_path: Path) -> None:
    async def scenario(db: ProgressDatabase) -> None:
        stack = build_review_stack(tmp_path, db, kana=[KANA_A, KANA_I])
        await stack.settings.save(GATED)
        assert (await stack.orchestrator.next_card()).counts.new_remaining.kana == 4

    run_with_database(tmp_path, scenario)


def test_a_disabled_type_offers_no_new_cards(tmp_path: Path) -> None:
    async def scenario(db: ProgressDatabase) -> None:
        stack = build_review_stack(tmp_path, db, kana=[KANA_A], vocab=[A])
        await stack.settings.save(ReviewSettings(type_enabled=TypeEnabled(vocab=False)))
        result = await stack.orchestrator.next_card()
        assert result.counts.new_remaining == TypeCounts(kana=2, kanji=0, vocab=0)
        assert result.card is not None
        assert result.card.item_type is ItemType.KANA

    run_with_database(tmp_path, scenario)


def test_a_disabled_type_still_serves_the_cards_it_already_introduced(tmp_path: Path) -> None:
    async def scenario(db: ProgressDatabase) -> None:
        stack = build_review_stack(tmp_path, db, vocab=[A, B])
        first = await next_card(stack)
        await answer(stack, first)  # now learning, due in minutes
        await stack.settings.save(ReviewSettings(type_enabled=TypeEnabled(vocab=False)))
        stack.clock.advance(minutes=11)
        result = await stack.orchestrator.next_card()
        assert result.card is not None
        assert (result.card.item_id, result.card.direction) == (first.item_id, first.direction)
        assert result.card.is_new is False
        assert result.counts.new_remaining.vocab == 0
        assert result.counts.due.vocab == 1

    run_with_database(tmp_path, scenario)


def test_with_every_type_disabled_only_scheduled_cards_remain(tmp_path: Path) -> None:
    async def scenario(db: ProgressDatabase) -> None:
        stack = build_review_stack(tmp_path, db, kana=[KANA_A], kanji=[make_kanji("日")], vocab=[A])
        await stack.settings.save(
            ReviewSettings(type_enabled=TypeEnabled(kana=False, kanji=False, vocab=False))
        )
        result = await stack.orchestrator.next_card()
        assert result.card is None
        assert result.counts.new_remaining == TypeCounts()

    run_with_database(tmp_path, scenario)


def test_a_blocked_type_is_logged_with_its_reason(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    async def scenario(db: ProgressDatabase) -> None:
        stack = build_review_stack(tmp_path, db, kana=[KANA_A], vocab=[A])
        await stack.settings.save(
            ReviewSettings(
                type_enabled=TypeEnabled(kanji=False),
                kana_gate=KanaGate(vocab=True, threshold=0.8),
            )
        )
        await stack.orchestrator.next_card()

    with caplog.at_level(logging.DEBUG, logger=LOGGER_NAME):
        run_with_database(tmp_path, scenario)
    assert "type_blocked type=kanji reason=disabled" in caplog.text
    expected = "type_blocked type=vocab reason=waiting_for_kana kana_share=0.0 threshold=0.8"
    assert expected in caplog.text
```

- [ ] **Step 2: Run to verify they fail**

Run: `unset VIRTUAL_ENV; uv run pytest tests/unit/orchestration/test_review_session.py -q -k "gated or gate or disabled or blocked or threshold"`
Expected: FAIL (the gate and the switches are not applied yet: for example `new_remaining` still shows kanji and vocab cards).

- [ ] **Step 3: Implement**

In `src/bunsho/orchestration/review_session.py`, in the same edit as the code that uses them, add `CatalogEntry` to the `bunsho.models.review` import list (after `CardSchedule`) and add `from bunsho.services.type_availability import type_availability` after the `study_day` import.

Replace the whole `_plan` method with:

```python
    async def _plan(
        self, now: datetime, repo: ContentRepository, settings: ReviewSettings
    ) -> _Plan:
        window = study_day_window(now, settings.rollover_hour, self._tz)
        states = await self._progress.card_states()
        introduced = await self._progress.new_cards_introduced(*window)
        due_counts = await self._progress.due_counts(now)
        policy = self._policy_factory(settings)
        catalog = ContentCatalog(repo)
        kana_entries: list[CatalogEntry] | None = None
        if settings.kana_gate.kanji or settings.kana_gate.vocab:
            kana_entries = await asyncio.to_thread(catalog.entries, ItemType.KANA)
        availability = type_availability(settings, kana_entries or [], states)
        new_keys: dict[ItemType, list[CardKey]] = {}
        for item_type in _TYPE_ORDER:
            status = availability[item_type]
            if not status.allowed:
                self._logger.debug(
                    "type_blocked type=%s reason=%s kana_share=%s threshold=%s",
                    item_type.value,
                    status.reason,
                    status.kana_share,
                    settings.kana_gate.threshold,
                )
                new_keys[item_type] = []
                continue
            limit = settings.new_limits.for_type(item_type)
            allowance = None if limit == 0 else max(0, limit - introduced.get(item_type, 0))
            if allowance == 0:
                new_keys[item_type] = []
                continue
            if item_type is ItemType.KANA and kana_entries is not None:
                entries = kana_entries
            else:
                entries = await asyncio.to_thread(catalog.entries, item_type)
            new_keys[item_type] = policy.select(item_type, entries, states, allowance)
        return _Plan(settings, introduced, due_counts, new_keys)
```

- [ ] **Step 4: Run to verify they pass, then the wider orchestrator and stats tests**

Run:
```
unset VIRTUAL_ENV; uv run pytest tests/unit/orchestration tests/unit/services tests/unit/api -q
unset VIRTUAL_ENV; uv run ruff check src tests && uv run ruff format --check src tests && uv run mypy src/
```
Expected: PASS. (The `caplog` line in the last test may exceed 100 columns; run `uv run ruff format tests/unit/orchestration/test_review_session.py` if `format --check` complains.)

- [ ] **Step 5: Commit**

```bash
git add src/bunsho/orchestration/review_session.py tests/unit/orchestration/test_review_session.py
git commit -m "feat(review): hold back disabled and kana-gated types when planning new cards" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 4: Frontend error placement by path, and the validation rule

**Files:**
- Modify: `frontend/src/api/errors.ts`
- Modify: `frontend/src/api/errors.test.ts`
- Modify: `frontend/src/features/settings/settingsForm.ts`
- Modify: `frontend/src/features/settings/settingsForm.test.ts`

**Interfaces:**
- Consumes: `SettingsFormValues.type_enabled`/`.kana_gate` (Task 1).
- Produces: `ApiError.fieldErrors` keyed by the dotted path below `body` (for example `new_limits.kana`, `kana_gate`, `target_retention`); `KANA_GATE_MESSAGE: string` exported from `settingsForm.ts`; `validateSettings` returns `kana_gate` and `kana_gate.threshold_percent` errors; `placeServerErrors` maps paths to form paths (`kana_gate` → `kana_gate`, `kana_gate.threshold` → `kana_gate.threshold_percent`).

- [ ] **Step 1: Write the failing tests**

In `frontend/src/api/errors.test.ts`, add after the existing `'maps a 422 list to per-field messages ...'` test:

```ts
  it('keys a 422 message by its dotted path below the request body', async () => {
    server.use(
      http.post('/api/v1/x', () =>
        HttpResponse.json(
          {
            detail: [
              { loc: ['body', 'new_limits', 'kana'], msg: 'too big', type: 'a' },
              { loc: ['body', 'type_enabled', 'kana'], msg: 'not a boolean', type: 'b' },
              { loc: ['body', 'active_levels', 0], msg: 'bad level', type: 'c' },
              { loc: ['body', 'kana_gate'], msg: 'needs kana', type: 'd' },
              { loc: ['body'], msg: 'no field', type: 'e' },
              { loc: ['query', 'page'], msg: 'bad page', type: 'f' },
            ],
          },
          { status: 422 },
        ),
      ),
    );
    const error = (await rawRequest('/x', { method: 'POST', body: {} }).catch(
      (caught: unknown) => caught,
    )) as ApiError;
    expect(error.fieldErrors).toEqual({
      'new_limits.kana': 'too big',
      'type_enabled.kana': 'not a boolean',
      'active_levels.0': 'bad level',
      kana_gate: 'needs kana',
      'query.page': 'bad page',
    });
  });
```

In `frontend/src/features/settings/settingsForm.test.ts`:

Import `KANA_GATE_MESSAGE` from `./settingsForm`. Replace the whole `describe('placeServerErrors', ...)` block with:

```ts
describe('placeServerErrors', () => {
  it('puts the server messages on the matching fields', () => {
    const placed = placeServerErrors(
      new ApiError(422, 'Request failed', {
        'new_limits.kana': 'Input should be less than or equal to 10000',
        target_retention: 'Input should be greater than or equal to 0.7',
        mastery_threshold: 'Input should be less than or equal to 1',
        rollover_hour: 'Input should be less than or equal to 23',
        active_levels: 'List should have at least 1 item',
        new_card_policy: 'Input should be a valid policy',
        'new_limits.kanji': 'bad',
        'new_limits.vocab': 'bad',
        kana_gate: 'Turn kana on',
        'kana_gate.threshold': 'Input should be less than or equal to 1',
        'kana_gate.kanji': 'not a boolean',
        'type_enabled.kana': 'not a boolean either',
      }),
    );
    expect(placed.fields).toEqual({
      'new_limits.kana': 'Input should be less than or equal to 10000',
      target_retention_percent: 'Input should be greater than or equal to 0.7',
      mastery_threshold_percent: 'Input should be less than or equal to 1',
      rollover_hour: 'Input should be less than or equal to 23',
      active_levels: 'List should have at least 1 item',
      new_card_policy: 'Input should be a valid policy',
      'new_limits.kanji': 'bad',
      'new_limits.vocab': 'bad',
      kana_gate: 'Turn kana on',
      'kana_gate.threshold_percent': 'Input should be less than or equal to 1',
      'kana_gate.kanji': 'not a boolean',
      'type_enabled.kana': 'not a boolean either',
    });
    expect(placed.general).toBeNull();
  });

  it('keeps kana, kanji and vocab under different groups apart', () => {
    const placed = placeServerErrors(
      new ApiError(422, 'Request failed', {
        'new_limits.kana': 'limit',
        'type_enabled.kana': 'switch',
        'kana_gate.kanji': 'gate',
      }),
    );
    expect(placed.fields).toEqual({
      'new_limits.kana': 'limit',
      'type_enabled.kana': 'switch',
      'kana_gate.kanji': 'gate',
    });
  });

  it('keeps messages for unknown fields for the general alert', () => {
    const placed = placeServerErrors(
      new ApiError(422, 'Request failed', {
        'new_limits.kana': 'too big',
        surprise: 'unexpected field',
      }),
    );
    expect(placed.fields).toEqual({ 'new_limits.kana': 'too big' });
    expect(placed.general).toBe('surprise: unexpected field');
  });

  it('says something when a 422 carries no field messages at all', () => {
    const placed = placeServerErrors(new ApiError(422, 'Request failed'));
    expect(placed.fields).toEqual({});
    expect(placed.general).toBe('The server did not accept these settings.');
  });
});
```

In `describe('validateSettings', ...)` add:

```ts
  it('asks for kana to be on when a gate is on', () => {
    const errors = validateSettings(
      withValues({
        type_enabled: { kana: false, kanji: true, vocab: true },
        kana_gate: { kanji: true, vocab: false, threshold_percent: 80 },
      }),
    );
    expect(errors).toEqual({ kana_gate: KANA_GATE_MESSAGE });
  });

  it('allows kana off with no gate, and every type off', () => {
    expect(
      validateSettings(
        withValues({ type_enabled: { kana: false, kanji: true, vocab: true } }),
      ),
    ).toEqual({});
    expect(
      validateSettings(
        withValues({ type_enabled: { kana: false, kanji: false, vocab: false } }),
      ),
    ).toEqual({});
  });

  it('accepts the edges of the gate threshold and rejects anything else', () => {
    for (const threshold of [0, 100, 80.5, '65']) {
      expect(
        validateSettings(
          withValues({ kana_gate: { ...VALID.kana_gate, threshold_percent: threshold } }),
        ),
      ).toEqual({});
    }
    for (const threshold of ['', ' ', -1, 101, 'abc']) {
      expect(
        validateSettings(
          withValues({ kana_gate: { ...VALID.kana_gate, threshold_percent: threshold } }),
        ),
      ).toEqual({ 'kana_gate.threshold_percent': 'Enter a percentage from 0 to 100.' });
    }
  });
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd frontend && npx vitest run src/api/errors.test.ts src/features/settings/settingsForm.test.ts`
Expected: FAIL (`KANA_GATE_MESSAGE` not exported; `fieldErrors` still keyed by last segment).

- [ ] **Step 3: Implement the path keying**

In `frontend/src/api/errors.ts` replace the doc comment on `fieldErrors` with:

```ts
  /** For 422 responses: the first message per field path below the request body (`new_limits.kana`). */
```

and replace `fieldErrorsOf` with:

```ts
/** A field's dotted path below the request body (`new_limits.kana`); null when it has none. */
function fieldPath(location: unknown[]): string | null {
  const parts = location.slice(location[0] === 'body' ? 1 : 0);
  if (parts.length === 0) return null;
  if (!parts.every((part) => typeof part === 'string' || typeof part === 'number')) return null;
  return parts.join('.');
}

function fieldErrorsOf(detail: unknown[]): Record<string, string> {
  const result: Record<string, string> = {};
  for (const item of detail) {
    if (!isRecord(item) || !Array.isArray(item.loc) || typeof item.msg !== 'string') continue;
    const path = fieldPath(item.loc);
    if (path !== null && !(path in result)) result[path] = item.msg;
  }
  return result;
}
```

- [ ] **Step 4: Implement the form rules**

In `frontend/src/features/settings/settingsForm.ts`:

Add near the other exported constants:

```ts
/** The same text the API sends when a gate is on while kana is off. */
export const KANA_GATE_MESSAGE =
  'Turn kana on, or turn off the kana gate: kanji and vocabulary cannot wait for kana that is never introduced.';

const PERCENTAGE_MESSAGE = 'Enter a percentage from 0 to 100.';
```

Add above `validateSettings`:

```ts
function isPercentage(value: number | string): boolean {
  if (typeof value === 'string' && value.trim() === '') return false;
  const number = Number(value);
  return !Number.isNaN(number) && number >= 0 && number <= 100;
}
```

In `validateSettings` replace the mastery-threshold block (from `const threshold = values.mastery_threshold_percent;` through its closing `}`) with:

```ts
  if (!isPercentage(values.mastery_threshold_percent)) {
    errors.mastery_threshold_percent = PERCENTAGE_MESSAGE;
  }
  const gate = values.kana_gate;
  if (!values.type_enabled.kana && (gate.kanji || gate.vocab)) {
    errors.kana_gate = KANA_GATE_MESSAGE;
  }
  if (!isPercentage(gate.threshold_percent)) {
    errors['kana_gate.threshold_percent'] = PERCENTAGE_MESSAGE;
  }
```

Replace `SERVER_FIELDS` with path keys:

```ts
/** Where the server's field paths (below `body`) live in the form. */
const SERVER_FIELDS: Readonly<Record<string, string>> = {
  new_card_policy: 'new_card_policy',
  'new_limits.kana': 'new_limits.kana',
  'new_limits.kanji': 'new_limits.kanji',
  'new_limits.vocab': 'new_limits.vocab',
  'type_enabled.kana': 'type_enabled.kana',
  'type_enabled.kanji': 'type_enabled.kanji',
  'type_enabled.vocab': 'type_enabled.vocab',
  kana_gate: 'kana_gate',
  'kana_gate.kanji': 'kana_gate.kanji',
  'kana_gate.vocab': 'kana_gate.vocab',
  'kana_gate.threshold': 'kana_gate.threshold_percent',
  target_retention: 'target_retention_percent',
  rollover_hour: 'rollover_hour',
  active_levels: 'active_levels',
  mastery_threshold: 'mastery_threshold_percent',
  kana_mode: 'kana_mode',
  kanji_mode: 'kanji_mode',
  vocab_mode: 'vocab_mode',
};
```

- [ ] **Step 5: Run to verify they pass, plus the page tests that use a 422**

Run: `cd frontend && npm run format && npx vitest run src/api src/features/settings && npm run lint && npm run build`
Expected: PASS (the existing `SettingsPage` test that returns `loc: ['body', 'new_limits', 'kana']` still lands on `Kana per day`, now via the path `new_limits.kana`).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/api/errors.ts frontend/src/api/errors.test.ts frontend/src/features/settings/settingsForm.ts frontend/src/features/settings/settingsForm.test.ts
git commit -m "feat(settings): place server errors by field path and validate the kana gate" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 5: The Settings page controls

**Files:**
- Modify: `frontend/src/features/settings/SettingsPage.tsx`
- Modify: `frontend/src/features/settings/SettingsPage.test.tsx`

**Interfaces:**
- Consumes: `SettingsFormValues.type_enabled`/`.kana_gate`, `validateSettings`, `placeServerErrors`, `KANA_GATE_MESSAGE` (Tasks 1 and 4).
- Produces: user-visible controls, with these accessible names (tests rely on them): switches `Introduce new kana`, `Introduce new kanji`, `Introduce new vocabulary`, `Wait for kana before starting kanji`, `Wait for kana before starting vocabulary`; number input `Kana needed before they start`; section title `Kana first`.

- [ ] **Step 1: Write the failing page tests**

In `frontend/src/features/settings/SettingsPage.test.tsx` add the import `import { KANA_GATE_MESSAGE } from './settingsForm';` (keep import order tidy) and, inside `describe('SettingsPage', ...)`, append:

```tsx
  it('fills the type switches and the kana gate from the saved settings', async () => {
    serveSettings(
      makeSettings({
        type_enabled: { kana: true, kanji: false, vocab: true },
        kana_gate: { kanji: false, vocab: true, threshold: 0.9 },
      }),
    );
    await openSettings();

    expect(screen.getByRole('switch', { name: 'Introduce new kana' })).toBeChecked();
    expect(screen.getByRole('switch', { name: 'Introduce new kanji' })).not.toBeChecked();
    expect(screen.getByRole('switch', { name: 'Introduce new vocabulary' })).toBeChecked();
    expect(
      screen.getByRole('switch', { name: 'Wait for kana before starting kanji' }),
    ).not.toBeChecked();
    expect(
      screen.getByRole('switch', { name: 'Wait for kana before starting vocabulary' }),
    ).toBeChecked();
    expect(screen.getByRole('textbox', { name: 'Kana needed before they start' })).toHaveValue(
      '90%',
    );
  });

  it('disables the daily limit of a type that is switched off and saves the switch', async () => {
    const user = userEvent.setup();
    const puts = serveSettings();
    await openSettings();

    await user.click(screen.getByRole('switch', { name: 'Introduce new kanji' }));
    expect(screen.getByRole('textbox', { name: 'Kanji per day' })).toBeDisabled();
    expect(screen.getByRole('textbox', { name: 'Kana per day' })).toBeEnabled();
    await user.click(screen.getByRole('button', { name: 'Save' }));

    expect(await screen.findByText('Settings saved')).toBeInTheDocument();
    expect(puts).toEqual([makeSettings({ type_enabled: { kana: true, kanji: false, vocab: true } })]);
  });

  it('shows the gate threshold only while a gate is on and sends it as a fraction', async () => {
    const user = userEvent.setup();
    const puts = serveSettings();
    await openSettings();
    expect(
      screen.queryByRole('textbox', { name: 'Kana needed before they start' }),
    ).not.toBeInTheDocument();

    await user.click(screen.getByRole('switch', { name: 'Wait for kana before starting kanji' }));
    const threshold = await screen.findByRole('textbox', { name: 'Kana needed before they start' });
    expect(threshold).toHaveValue('80%');
    await setNumber(user, 'Kana needed before they start', '90');
    await user.click(screen.getByRole('button', { name: 'Save' }));

    expect(await screen.findByText('Settings saved')).toBeInTheDocument();
    expect(puts).toEqual([makeSettings({ kana_gate: { kanji: true, vocab: false, threshold: 0.9 } })]);
  });

  it('will not save a kana gate while kana is switched off, and the message clears once fixed', async () => {
    const user = userEvent.setup();
    const puts = serveSettings(
      makeSettings({ kana_gate: { kanji: true, vocab: false, threshold: 0.8 } }),
    );
    await openSettings();

    await user.click(screen.getByRole('switch', { name: 'Introduce new kana' }));
    await user.click(screen.getByRole('button', { name: 'Save' }));
    expect(await screen.findByText(KANA_GATE_MESSAGE)).toBeInTheDocument();
    expect(puts).toEqual([]);

    await user.click(screen.getByRole('switch', { name: 'Wait for kana before starting kanji' }));
    expect(screen.queryByText(KANA_GATE_MESSAGE)).not.toBeInTheDocument();
  });

  it('keeps a switched-on gate operable after kana is switched off', async () => {
    const user = userEvent.setup();
    serveSettings(makeSettings({ kana_gate: { kanji: true, vocab: false, threshold: 0.8 } }));
    await openSettings();

    await user.click(screen.getByRole('switch', { name: 'Introduce new kana' }));
    expect(screen.getByRole('switch', { name: 'Wait for kana before starting kanji' })).toBeEnabled();
    expect(
      screen.getByRole('switch', { name: 'Wait for kana before starting vocabulary' }),
    ).toBeDisabled();
  });

  it('shows a server 422 on the kana gate group', async () => {
    const user = userEvent.setup();
    server.use(
      http.get('/api/v1/settings', () => HttpResponse.json(makeSettings())),
      http.put('/api/v1/settings', () =>
        HttpResponse.json(
          {
            detail: [{ loc: ['body', 'kana_gate'], msg: 'Server says no', type: 'kana_gate_needs_kana' }],
          },
          { status: 422 },
        ),
      ),
    );
    await openSettings();

    await user.click(screen.getByRole('switch', { name: 'Wait for kana before starting vocabulary' }));
    await user.click(screen.getByRole('button', { name: 'Save' }));

    expect(await screen.findByText('Server says no')).toBeInTheDocument();
    expect(screen.queryByText("Couldn't save your settings")).not.toBeInTheDocument();
  });

  it('reveals a hidden threshold field that is invalid when Save is pressed', async () => {
    const user = userEvent.setup();
    const puts = serveSettings(
      makeSettings({ kana_gate: { kanji: true, vocab: false, threshold: 0.8 } }),
    );
    await openSettings();

    await setNumber(user, 'Kana needed before they start', '');
    await user.click(screen.getByRole('switch', { name: 'Wait for kana before starting kanji' }));
    expect(
      screen.queryByRole('textbox', { name: 'Kana needed before they start' }),
    ).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Save' }));
    expect(await screen.findByText('Enter a percentage from 0 to 100.')).toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: 'Kana needed before they start' })).toBeInTheDocument();
    expect(puts).toEqual([]);
  });

  it('refills the type switches and the gate with the recommended values on Reset', async () => {
    const user = userEvent.setup();
    serveSettings(
      makeSettings({
        type_enabled: { kana: true, kanji: false, vocab: false },
        kana_gate: { kanji: true, vocab: true, threshold: 0.5 },
      }),
    );
    await openSettings();

    await user.click(screen.getByRole('button', { name: 'Reset to recommended values' }));
    expect(screen.getByRole('switch', { name: 'Introduce new kanji' })).toBeChecked();
    expect(screen.getByRole('switch', { name: 'Introduce new vocabulary' })).toBeChecked();
    expect(
      screen.getByRole('switch', { name: 'Wait for kana before starting kanji' }),
    ).not.toBeChecked();
  });
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd frontend && npx vitest run src/features/settings/SettingsPage.test.tsx`
Expected: FAIL (`Unable to find role="switch"`).

- [ ] **Step 3: Implement the controls**

In `frontend/src/features/settings/SettingsPage.tsx`:

Add `Switch` to the `@mantine/core` import list (alphabetical, after `Stack`). Add `KANA_GATE` nothing else to import (the message comes from the server or validation).

Inside `SettingsForm`, after `const retentionId = useId();` add `const gateId = useId();`. After the `submit` definition add:

```tsx
  type SwitchPath =
    | 'type_enabled.kana'
    | 'type_enabled.kanji'
    | 'type_enabled.vocab'
    | 'kana_gate.kanji'
    | 'kana_gate.vocab';
  /** Set a switch and drop the kana-gate message, so a fixed problem stops being shown. */
  const setSwitch = (path: SwitchPath, checked: boolean) => {
    form.setFieldValue(path, checked);
    form.clearFieldError('kana_gate');
  };
```

After `retentionError` add:

```tsx
  const gate = values.kana_gate;
  const gateError = typeof form.errors.kana_gate === 'string' ? form.errors.kana_gate : undefined;
  const thresholdError =
    typeof form.errors['kana_gate.threshold_percent'] === 'string'
      ? form.errors['kana_gate.threshold_percent']
      : undefined;
  // A hidden threshold that is invalid must still be shown, or Save would fail with no clue why.
  const showThreshold = gate.kanji || gate.vocab || thresholdError !== undefined;
  const kanaOff = !values.type_enabled.kana;
```

Replace the block from `<Group grow align="flex-start">` through the closing `</Text>` of "The most new cards…" in the "New cards" section with:

```tsx
          <Stack gap="xs">
            <Switch
              label="Introduce new kana"
              checked={values.type_enabled.kana}
              onChange={(event) => {
                setSwitch('type_enabled.kana', event.currentTarget.checked);
              }}
            />
            <Switch
              label="Introduce new kanji"
              checked={values.type_enabled.kanji}
              onChange={(event) => {
                setSwitch('type_enabled.kanji', event.currentTarget.checked);
              }}
            />
            <Switch
              label="Introduce new vocabulary"
              checked={values.type_enabled.vocab}
              onChange={(event) => {
                setSwitch('type_enabled.vocab', event.currentTarget.checked);
              }}
            />
            <Text size="sm" c="dimmed">
              A type that is switched off introduces no new cards. Cards you already started stay
              due, so no progress is lost.
            </Text>
          </Stack>
          <Group grow align="flex-start">
            <NumberInput
              label="Kana per day"
              min={0}
              max={LIMIT_MAX}
              allowDecimal={false}
              disabled={!values.type_enabled.kana}
              {...form.getInputProps('new_limits.kana')}
            />
            <NumberInput
              label="Kanji per day"
              min={0}
              max={LIMIT_MAX}
              allowDecimal={false}
              disabled={!values.type_enabled.kanji}
              {...form.getInputProps('new_limits.kanji')}
            />
            <NumberInput
              label="Vocabulary per day"
              min={0}
              max={LIMIT_MAX}
              allowDecimal={false}
              disabled={!values.type_enabled.vocab}
              {...form.getInputProps('new_limits.vocab')}
            />
          </Group>
          <Text size="sm" c="dimmed">
            The most new cards of each type per day. 0 means no limit.
          </Text>
        </Stack>

        <Stack gap="md">
          <Title order={3}>Kana first</Title>
          <Input.Wrapper
            id={gateId}
            label="Start kanji and vocabulary after kana"
            description="Hold them back until enough kana is learned. Your scheduled reviews are never held back."
            error={gateError}
            {...groupAria(gateId, gateError !== undefined)}
          >
            <Stack gap="xs" mt="xs">
              <Switch
                label="Wait for kana before starting kanji"
                checked={gate.kanji}
                disabled={kanaOff && !gate.kanji}
                onChange={(event) => {
                  setSwitch('kana_gate.kanji', event.currentTarget.checked);
                }}
              />
              <Switch
                label="Wait for kana before starting vocabulary"
                checked={gate.vocab}
                disabled={kanaOff && !gate.vocab}
                onChange={(event) => {
                  setSwitch('kana_gate.vocab', event.currentTarget.checked);
                }}
              />
            </Stack>
          </Input.Wrapper>
          {showThreshold && (
            <NumberInput
              label="Kana needed before they start"
              description="Share of all kana cards (both directions, hiragana and katakana) that must be well known (in Review). If it drops below this later, new kanji and vocabulary pause until it recovers."
              min={0}
              max={100}
              allowDecimal={false}
              suffix="%"
              {...form.getInputProps('kana_gate.threshold_percent')}
            />
          )}
```

so that the "New cards" `</Stack>` closes once (the replaced range ends by opening the `Kana first` stack whose closing `</Stack>` is the original one that closed "New cards"). Verify the JSX balances after the edit (the original `</Stack>` after the "The most new cards…" `<Text>` is the closing tag of the new "Kana first" stack).

Update the page doc comment at the bottom to: `/** How new cards are chosen and gated, how many, and how sharp your memory should stay. */`.

- [ ] **Step 4: Run to verify they pass, then the frontend gate**

Run: `cd frontend && npm run format && npx vitest run src/features/settings && npm run lint && npm run build`
Expected: PASS. If `getByRole('textbox', { name: 'Kana needed before they start' })` cannot find the input because the description text became part of its accessible name in this Mantine version, switch those queries to a regex (`/Kana needed before they start/`), as the existing `Mastery needed` tests do.

Then run the whole frontend suite once: `cd frontend && npm run coverage`
Expected: PASS above the configured thresholds.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/features/settings/SettingsPage.tsx frontend/src/features/settings/SettingsPage.test.tsx
git commit -m "feat(settings): add the type switches and the Kana first controls to the Settings page" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 6: Release 1.1.0 and docs

**Files:**
- Modify: `pyproject.toml`, `src/bunsho/__init__.py`, `uv.lock`, `frontend/package.json`, `frontend/package-lock.json`, `frontend/openapi.json`
- Modify: `CHANGELOG.md`, `README.md`, `TODO.md`

**Interfaces:**
- Consumes: everything above. Produces: version `1.1.0` everywhere; no behaviour change.

- [ ] **Step 1: Bump the version**

Run:
```
sed -i 's/^version = "1.0.0"/version = "1.1.0"/' pyproject.toml
sed -i 's/^__version__ = "1.0.0"/__version__ = "1.1.0"/' src/bunsho/__init__.py
unset VIRTUAL_ENV; uv lock
cd frontend && npm version 1.1.0 --no-git-tag-version && cd ..
unset VIRTUAL_ENV; uv run python scripts/export_openapi.py
cd frontend && npm run gen:api && cd ..
git diff --stat
```
Expected: changes only in `pyproject.toml`, `src/bunsho/__init__.py`, `uv.lock` (the `bunsho` entry), `frontend/package.json`, `frontend/package-lock.json` (two version lines), `frontend/openapi.json` (`info.version`); `schema.d.ts` unchanged. Confirm with `grep -rn "1\.0\.0" pyproject.toml src/bunsho/__init__.py frontend/package.json` printing nothing for the project's own version.

- [ ] **Step 2: Update `CHANGELOG.md`**

Get the date with `date +%F`. Directly under `## [Unreleased]` insert (replace `<DATE>` with that date):

```markdown
## [1.1.0] - <DATE>

### Added

- Study plan control (Settings): each of kana, kanji and vocabulary can be switched off for new cards
  (cards already introduced stay due, so nothing is lost; all three off gives a reviews-only
  session), and kanji and vocabulary can each be made to wait until a chosen share (default 80%) of
  all kana cards, both directions, hiragana and katakana together, is in the FSRS Review state. The
  gate works with every new-card policy and is checked on every plan, so if the kana share later
  falls below the threshold, new kanji and vocabulary pause until it recovers; scheduled reviews are
  never held back. The settings document gains `type_enabled` and `kana_gate`; defaults keep the
  previous behaviour and saved settings from 1.0.0 load unchanged. (#20)
```

- [ ] **Step 3: Update `README.md`**

In the **Settings** paragraph, replace `` `new_limits` per type in **cards** per day (kana 20, kanji 15, vocab 20; `0` = unlimited), `` with:

```
`new_limits` per type in **cards** per day (kana 20, kanji 15, vocab 20; `0` = unlimited), `type_enabled` per type (all `true`; a `false` type introduces no new cards but its scheduled cards stay due; all three `false` means reviews only), `kana_gate` (`kanji` and `vocab`, both `false`: hold that type's new cards back until `threshold` [0.80] of all kana cards, both directions, are in the FSRS Review state; needs kana enabled; checked on every plan, so a later dip pauses them again),
```

In the **Statistics and settings** paragraph replace `the daily new-card limits (0 means unlimited), the levels used` with:

```
the daily new-card limits (0 means unlimited), which types introduce new cards at all, an optional *Kana first* gate that holds back new kanji and vocabulary until enough kana is learned, the levels used
```

- [ ] **Step 4: Update `TODO.md`**

In the API Gaps item that begins `` - [ ] `GET /reviews/next` cannot say why no card is offered `` append to its last line: ` (the new `type_availability` service already returns a per-type block reason, so a blocked type could be reported here)`.

Under `### Later Sub-Projects` add a bullet:

```
- [ ] Study-path presets (for example Beginner: kana first, then kanji and vocabulary together)
      built on the type switches and the kana gate
```

- [ ] **Step 5: Run the full CI mirror**

Run:
```
unset VIRTUAL_ENV; uv sync --extra dev --locked && uv lock --check
uv run ruff check . && uv run ruff format --check . && uv run mypy src/ && uv run bandit -c pyproject.toml -r src/ -l
uv run pytest --cov --cov-report=term-missing
cd frontend && npm run format:check && npm run lint && npm run gen:api && git diff --exit-code -- src/api/schema.d.ts && npm run build && npm run coverage
```
Expected: everything passes, coverage at or above 90 percent on the backend, `git diff --exit-code` prints nothing. (A single failing `test_main.py` test caused by a real `.env` in the repo root is not a regression.)

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml src/bunsho/__init__.py uv.lock frontend/package.json frontend/package-lock.json frontend/openapi.json CHANGELOG.md README.md TODO.md
git commit -m "chore(release): bump version to 1.1.0" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Self-Review

**Spec coverage.** Data model and validation: Task 1. Compatibility (old document): Task 1 service test. Availability rule (order, kana share, empty catalog, threshold edges, measured once): Task 2. Orchestrator wiring, blocked types serving due cards, debug log: Task 3. API/OpenAPI and generated types: Task 1 Step 6 and Task 6 Step 1. Frontend values, conversion, dirty check, `RECOMMENDED_SETTINGS` drift test: Task 1; validation mirror and path keying: Task 4; UI (switches, disabled limits, gate group, threshold shown only with a gate, message on the group, gate switches disabled while kana is off but a switched-on one stays operable): Task 5. Error handling: Tasks 3 to 5. Release bump, CHANGELOG, README, TODO: Task 6. The spec's "shown only while a gate is on" is honoured with the one refinement that an invalid hidden threshold is revealed on Save.

**Placeholder scan.** The only placeholder is `<DATE>` in the changelog, filled from `date +%F` in the same step.

**Type consistency.** `TypeEnabled.for_type`, `KanaGate.gates`/`.threshold`, `Availability(allowed, reason, kana_share)`, `BlockReason.DISABLED`/`WAITING_FOR_KANA`, `kana_share()`, `type_availability()` are used with identical names in Tasks 1 to 3. Form names `type_enabled`, `kana_gate.threshold_percent`, `KANA_GATE_MESSAGE`, `isPercentage` match across Tasks 1, 4 and 5. Switch and input accessible names in Task 5's tests match the labels in its implementation.

**Review Focus.** Each of the six lines names an owning test above.
