# Bunshō: Per-Type Enable Switches and a Kana Gate — Design

Status: design approved in conversation 2026-09-23 (brainstorming); this document awaits review.
Next: implementation plan.
Issue: #20.
Parent designs: `2026-09-20-bunsho-2a-review-engine-design.md` (the review engine and new-card
policies this extends) and `2026-09-20-bunsho-2b3-stats-settings-design.md` (the Settings page).

## Scope

A learner should be able to start with kana alone and let kanji and vocabulary begin on their own once
kana is solid. Today all three item types introduce new cards from day one, a daily limit of `0` means
*unlimited* (so a type cannot be switched off), and nothing links one type to another.

Covers: a per-type enable switch for new cards; a kana gate that holds back new kanji and/or new vocab
until enough kana is learned; the `ReviewSettings` fields, validation and defaults; the availability
service and its use in the daily plan; the Settings page controls; and the 1.1.0 release bump.

Out of scope: named study-path presets; ordering hiragana before katakana (kana is one stage); an API
reason for an empty review queue (tracked in `TODO.md`; the service returns a reason per blocked type so
that item stays cheap); changing the three new-card policies, the scheduler, or the per-type daily
limits; a persisted "gate opened" latch (see decisions).

## Decisions (locked in brainstorming)

| Topic | Decision |
|---|---|
| Enable switch | `type_enabled` per type. A disabled type introduces no new cards; cards it already introduced stay due, so nothing is stranded. All three off is allowed and gives a reviews-only mode. |
| Gate | `kana_gate.kanji` and `kana_gate.vocab`, each switchable. A gated type may introduce new cards only while the kana share in the FSRS Review state is at least `kana_gate.threshold`. |
| Kana as one stage | The share is Review-state kana cards over all kana cards: both directions, hiragana and katakana together. |
| Threshold | Its own field, default 0.80, independent of `mastery_threshold` (which stays specific to the `mastery_unlock` policy). |
| Policy independence | The rule applies before, and regardless of, the new-card policy (`strict_order`, `mastery_unlock`, `pinned_levels`). |
| Settings shape | Objects, like `NewLimits`: `type_enabled: {kana, kanji, vocab}` and `kana_gate: {kanji, vocab, threshold}`. |
| Where the rule lives | A small pure service, `services/type_availability.py`, called once per daily plan. Policies stay unaware of it (a policy sees only its own type's catalog, so it cannot measure kana). |
| Defaults | Everything enabled, both gates off, threshold 0.80: today's behaviour exactly. |
| Empty kana catalog | The gate counts as open, so a missing kana deck cannot block kanji forever (the same guard `MasteryUnlockPolicy` has for empty levels). |
| Gate vs disabled kana | Rejected at save: a gate switched on while kana is disabled could never open. |
| Gate is live, not latched | **Changed from the wording in issue #20.** The share is evaluated on every plan, so if kana cards lapse into Relearning and the share falls below the threshold, new kanji and vocab pause until it recovers. Reviews are never affected. A persisted latch would need new state and a rule for when threshold changes reset it; this matches how `MasteryUnlockPolicy` already behaves. |

## Data model

`src/bunsho/models/review_settings.py`:

```python
class TypeEnabled(BaseModel):
    """Which item types may introduce new cards. Due reviews are never affected."""
    kana: bool = True
    kanji: bool = True
    vocab: bool = True
    def for_type(self, item_type: ItemType) -> bool: ...   # match, like NewLimits.for_type

class KanaGate(BaseModel):
    """Hold new kanji and/or vocab back until enough kana is learned."""
    kanji: bool = False
    vocab: bool = False
    threshold: float = Field(default=0.80, ge=0.0, le=1.0)
    def gates(self, item_type: ItemType) -> bool: ...      # kana is never gated

class ReviewSettings(BaseModel):
    ...
    type_enabled: TypeEnabled = Field(default_factory=TypeEnabled)
    kana_gate: KanaGate = Field(default_factory=KanaGate)   # declared after type_enabled
```

Both new models use `extra="forbid"` and `json_schema_serialization_defaults_required=True`, like
`NewLimits`, so the generated types mark defaulted fields required.

**Validation.** A `field_validator("kana_gate")` on `ReviewSettings` reads `info.data["type_enabled"]`
(hence the field order) and, if kana is disabled while either gate is on, raises a
`PydanticCustomError` with a plain message ("Turn kana on, or turn off the kana gate: kanji and vocab
cannot wait for kana that is never introduced."). Using a field validator puts the error at
`body.kana_gate` (a model validator would surface at `body`, which the form cannot place), and a custom
error avoids Pydantic's "Value error, " prefix. If `type_enabled` itself failed validation it is absent
from `info.data`; the validator skips the check then, since that error is already reported.

**Compatibility.** `ReviewSettingsService.load` validates the stored JSON; an old document lacks the
new keys and takes their defaults, so it loads unchanged and behaves as before. `extra="forbid"` on
the model still rejects a document from a *newer* version, which `load` already logs and replaces with
defaults. No database migration: settings are one JSON document in `app_setting`.

## Availability service

`src/bunsho/services/type_availability.py`, pure and synchronous:

```python
class BlockReason(StrEnum):
    DISABLED = "disabled"
    WAITING_FOR_KANA = "waiting_for_kana"

@dataclass(frozen=True, slots=True)
class Availability:
    allowed: bool
    reason: BlockReason | None       # None exactly when allowed

def type_availability(
    settings: ReviewSettings,
    kana_entries: Sequence[CatalogEntry],
    states: Mapping[CardKey, SchedState],
) -> dict[ItemType, Availability]: ...
```

Rule, in order, for each type:

1. Not enabled → `DISABLED`.
2. Kana, or a type whose gate is off → allowed.
3. Otherwise compute the kana share once: for every kana entry and every kana direction, count the card
   as learned when `states.get(CardKey(id, direction)) is SchedState.REVIEW`. No kana entries → open.
   Share ≥ `threshold` → allowed; else `WAITING_FOR_KANA`. Threshold 0 is always open; 1.0 needs every
   kana card in Review.

The share is computed at most once per call, only when a gate is on.

## Orchestrator change

`ReviewSessionOrchestrator._plan` (`orchestration/review_session.py`) already loads `states`. It gains:

- load the kana catalog entries once, before the per-type loop, and only when a gate is on or kana is
  allowed (`asyncio.to_thread(catalog.entries, ItemType.KANA)`); the loop's kana iteration reuses that
  list instead of reading the catalog again;
- call `type_availability(settings, kana_entries, states)`;
- in the per-type loop, `new_keys[item_type] = []` and `continue` when the type is not allowed, before the
  limit and policy work.

`pick_new` and the dashboard's `new_remaining` counts then behave with no change: a blocked type has no
new keys. Due cards are read from `card_states` and are untouched. `introduced` counting is unchanged.

## API and OpenAPI

`GET`/`PUT /settings` already return and accept `ReviewSettings`; the new objects flow through. Regenerate
the committed OpenAPI snapshot (`frontend/openapi.json`) and the generated `frontend/src/api/schema.d.ts`;
add `TypeEnabled` and `KanaGate` type aliases to `frontend/src/api/endpoints.ts` if the form needs them.
A 422 for the gate rule carries `loc: ["body", "kana_gate"]`.

## Frontend

`features/settings`:

- `SettingsFormValues` gains `type_enabled: {kana, kanji, vocab: boolean}` and
  `kana_gate: {kanji, vocab: boolean; threshold_percent: number | string}` (a percentage here, a fraction
  in the API, as `mastery_threshold_percent` already is). `RECOMMENDED_SETTINGS`, `toFormValues`,
  `toRequest` and `canonical` (dirty-checking) cover them; the test that compares
  `RECOMMENDED_SETTINGS` with the snapshot defaults keeps guarding drift.
- `validateSettings` mirrors the server rule with the same message on `kana_gate`, and checks the
  threshold is a percentage from 0 to 100.
- **Error placement.** `ApiError.fieldErrors` is keyed by the last segment of `loc`, and `kana`, `kanji`
  and `vocab` would now each name up to three settings fields (`new_limits.kana`, `type_enabled.kana`,
  `kana_gate.kanji`, ...). The error layer changes to key by the dotted path below `body`
  (`new_limits.kana`, `kana_gate`, `target_retention`), and `SERVER_FIELDS` maps those paths. This is a
  targeted change to `api/errors.ts` and `placeServerErrors`, with their tests updated, not a general
  refactor.
- **UI.** In the "New cards" section, a switch per type ("Introduce new kana / kanji / vocabulary"); a
  disabled type's daily-limit input is disabled, not hidden. Beneath it a "Kana first" group: two
  switches ("Wait for kana before starting kanji" / "...vocabulary") and one threshold input (percent,
  same control style as the mastery threshold) shown only while a gate is on, with helper text saying the
  share counts every kana card in both directions. The gate switches are disabled while kana is off, and
  the form shows the validation message on the group.

## Error handling

- 422 for gate-with-kana-disabled, shown on the Kana-first group, before and after the round trip.
- Nothing logs or fails at plan time for a blocked type; `type_availability` is total. A debug log line per
  blocked type (`type_blocked type=kanji reason=waiting_for_kana share=0.42 threshold=0.80`) makes a
  puzzled learner's "why are there no new kanji" answerable from the logs.
- A stored document that fails validation still falls back to defaults with the existing WARNING.

## Testing

- `type_availability` table tests: every enabled/gate combination; threshold 0, exactly at the threshold,
  just below, and 1.0; kana counted across both directions and both scripts; only Review counts (Learning
  and Relearning do not); empty kana catalog; the share computed once; kana disabled with no gate.
- `TypeEnabled.for_type` and `KanaGate.gates` for every type; `ReviewSettings` validation: defaults, the
  gate-with-kana-disabled rejection, the skip when `type_enabled` is itself invalid, a fraction range,
  and an old JSON document without the new keys loading unchanged (service test).
- Orchestrator: fresh database with both gates on offers only kana; a disabled type offers no new cards
  yet still serves its due ones; the gate opens when the kana share reaches the threshold; a gate does not
  affect kana; counts (`new_remaining`) show zero for blocked types.
- API: `PUT /settings` round trip with the new objects, the 422 location, old-shape body accepted with
  defaults; the OpenAPI snapshot test.
- Frontend: `settingsForm` conversion, dirty-checking, validation, and error placement by path (including
  the collision cases); `SettingsPage` interactions (switches, disabled limit input, threshold shown only
  with a gate, server 422 shown on the group); `errors.ts` keying by path.

## Release

Version 1.0.0 → 1.1.0 (backward-compatible feature): `pyproject.toml`, `src/bunsho/__init__.py`,
`uv.lock` (the `bunsho` entry), `frontend/package.json` and `frontend/package-lock.json`, the OpenAPI
snapshot's `info.version`, and `CHANGELOG.md` (Added entries, moved under a `[1.1.0]` heading with the
date the release is cut). It is the last task of the plan so the bump lands with the feature. As with
1.0.0, no tag is pushed and no release is created.

## Risks

- **Live gate re-locking** may surprise a learner mid-way; it is documented in the UI helper text and the
  changelog, and it never touches reviews. If it proves annoying, a latch can be added later behind the
  same service.
- **Error-key change** touches shared frontend code; it is confined to `errors.ts` and
  `placeServerErrors`, and every existing 422 field (`new_card_policy`, `target_retention`, ...) has a
  single unambiguous path, so mapping them by path is mechanical.
- **Kana catalog cost:** loading kana entries is cheap (a few hundred rows) and skipped when no gate is
  on.
