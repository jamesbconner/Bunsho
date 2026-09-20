# Bunshō Plan 2A: Review Engine Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the backend of the review engine: FSRS scheduling, lazy card creation, three switchable new-card policies, a session orchestrator, review/stats/settings endpoints, and the `progress.db` hardening that has to land with the first grade writes.

**Architecture:** Hexagonal modular monolith, as in Plans 1A-1C. Domain types live in `models/`, persistence in `db/`, business logic in `services/` behind Protocols, workflows in `orchestration/`, HTTP in `api/`. A card is `(item_id, direction)` and exists in `progress.db` only after its first grade (lazy creation). Policies and the scheduler are chosen by factories from settings stored in `app_setting`.

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy 2.0 async (aiosqlite), Alembic (no new migration), `py-fsrs`, `tzdata`, pydantic v2, pytest, ruff, mypy strict, bandit.

**Spec:** `docs/superpowers/specs/2026-09-20-bunsho-2a-review-engine-design.md` (parent design: `docs/superpowers/specs/2026-09-19-bunsho-foundation-and-review-engine-design.md`). Read the spec before starting; this plan implements it and lists the small refinements made while planning (see "Refinements to the spec" below).

## Global Constraints

Every task's requirements include this section. Values are copied from the spec and the project rules.

- Python `>=3.13`; ruff line length `100`; mypy `strict`; bandit clean; coverage `fail_under = 90` (`pyproject.toml`).
- All routes are under `/api/v1` and JWT-protected except login and health. Port `8192` (never `8000`).
- Card directions: kana `glyph_to_sound`, `sound_to_glyph`; kanji `kanji_to_meaning`, `kanji_to_reading`, `meaning_to_kanji`; vocab `recognition`, `recall`.
- Grades: Again=1, Hard=2, Good=3, Easy=4. Scheduling states: New=0, Learning=1, Review=2, Relearning=3 (New means "no `card_state` row yet").
- Setting defaults and ranges: `new_card_policy` `strict_order` | `mastery_unlock` | `pinned_levels`; daily new-card limits count **cards**, kana `20`, kanji `15`, vocab `20`, `0` = unlimited; `target_retention` default `0.90`, range `0.70`-`0.99`; `rollover_hour` default `4`, range `0`-`23`; `active_levels` default `["N5"]`; `mastery_threshold` default `0.80`, range `0`-`1`.
- Errors: `detail` is a string, except 422 where it is a list. 401 auth, 404 unknown item, 409 stale `expected_last_review`, 503 content not built.
- `POST /reviews/answer` (body: `item_id`, `direction`, `grade`, `expected_last_review`, `duration_ms?`) replaces the parent spec's `POST /reviews/{card_id}/answer`.
- Timestamps in `progress.db` are UTC ISO strings in the fixed format `%Y-%m-%dT%H:%M:%S.%fZ`.
- Project rules (`.claude/CLAUDE.md`): Google-style docstrings on all public code, type annotations everywhere, service factories validate config and raise `ValueError` for unsupported types, dry-run and structured `key=value` logging conventions, meaningful tests (new behavior needs new tests).
- Test conventions: there is **no pytest-asyncio**; run coroutines with `asyncio.run(...)` (helper `run_with_database` is added in Task 2). Tests never touch the network. `tests/**` ignores ruff `D`/`S101`.
- Commits: conventional commits, stage explicit paths only (never `git add .` or `-A`), and give the trailer as its own paragraph: `git commit -m "<subject>" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"`. Never stage `.gitignore`, `.github/`, `.python-version` unless a task says so. Never merge to `main`; James merges.
- Windows / Git Bash quirks: run `unset VIRTUAL_ENV` before `uv`; set `PYTHONIOENCODING=utf-8` when printing Japanese; quote paths (`Bunshō` contains ō); after writing Python files that contain backslash escapes or Japanese literals, re-read them (the write layer can collapse escapes); add an import only together with its first use (a formatter hook can drop unused imports).
- Verification commands (run from the repo root): `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy`, `uv run bandit -c pyproject.toml -r src -q`, `uv run pytest -q`.

## Refinements to the spec

Found while reading the code for this plan. None changes user-visible behaviour the spec promises; call them out in the PR description.

1. **Item type is derived from the direction**, never parsed from the content id (ids stay opaque). Because each direction belongs to exactly one type, an "invalid item/direction pair" cannot occur: an unknown item is a 404, an unknown direction is a 422 (enum validation).
2. **`ContentRepository.catalog(item_type)`** (ids and levels only, unleveled kanji excluded in SQL) replaces the spec's `leveled_only` option on `list_kanji`; it is what the catalogue needs and avoids parsing 7,700 JSON payloads per request.
3. **The hydrated card carries the domain item** (`kana`, `kanji` or `vocab`, exactly one set) instead of pre-rendered front/back fields; those models already hold reading segments, meanings and example sentences, and 2B decides the layout per direction.
4. **Study-day timezone:** `TZ` when set (IANA name), otherwise UTC with a startup warning. `tzdata` is added as a dependency so `ZoneInfo` works on Windows and in slim images.
5. **Backup and WAL:** the existing startup backup already uses the SQLite backup API (`sqlite3.Connection.backup` in `db/migrate.py`), which is WAL-safe, so no change is needed there; Task 2 adds a test that proves it.
6. **Settings are stored as one JSON document** under the `app_setting` key `review_settings`, so `PUT /settings` is atomic by construction. It is a full replacement (omitted fields take their defaults).

## File Structure

New files:

| File | Responsibility |
|---|---|
| `src/bunsho/models/review.py` | `ItemType`, `CardDirection`, `DIRECTIONS_BY_TYPE`, `Grade`, `SchedState`, `CardKey`, `CardSchedule`, `CatalogEntry`, review exceptions |
| `src/bunsho/models/review_settings.py` | `NewCardPolicyName`, `NewLimits`, `ReviewSettings` (validation) |
| `src/bunsho/models/review_session.py` | Response models: `TypeCounts`, `GradeIntervals`, `CardView`, `ReviewCounts`, `NextCard`, stats models |
| `src/bunsho/services/fsrs_scheduler.py` | `FSRSScheduler` (wraps `py-fsrs`) |
| `src/bunsho/services/study_day.py` | `study_day_window`, `study_date`, `resolve_timezone` |
| `src/bunsho/services/review_settings.py` | `ReviewSettingsService` (load/save the settings document) |
| `src/bunsho/services/content_catalog.py` | `ContentCatalog` (ordered, level-tagged entries per item type) |
| `src/bunsho/services/new_card_policies.py` | `StrictOrderPolicy`, `MasteryUnlockPolicy`, `PinnedLevelsPolicy` |
| `src/bunsho/services/content_access.py` | `ContentGate` (usable content repository or `ContentNotReadyError`) |
| `src/bunsho/services/review_stats.py` | `ReviewStatsService` |
| `src/bunsho/orchestration/review_session.py` | `ReviewSessionOrchestrator` |
| `src/bunsho/db/timestamps.py` | `format_timestamp`, `parse_timestamp` |
| `src/bunsho/db/progress_repository.py` | `ProgressRepository`, `StoredCard`, `ReviewRecord` |
| `src/bunsho/db/instance_lock.py` | `InstanceLock`, `InstanceLockedError` |
| `src/bunsho/api/responses.py` | Shared OpenAPI `responses=` fragments |
| `src/bunsho/api/routers/reviews.py`, `stats.py`, `settings.py` | The new routes |
| `tests/review_stack.py` | Test builders: content writer, `FakeClock`, `build_review_stack` |

Modified files: `pyproject.toml`, `uv.lock`, `src/bunsho/db/engine.py`, `src/bunsho/services/protocols.py`, `src/bunsho/services/content_repository.py`, `src/bunsho/factories.py`, `src/bunsho/api/services.py`, `src/bunsho/api/app.py`, `src/bunsho/api/schemas.py`, `src/bunsho/api/routers/{auth,health,admin,content}.py`, `tests/base.py`, `tests/unit/api/conftest.py`, `tests/unit/api/test_admin_routes.py`, `tests/unit/api/test_app_startup.py`, `scripts/smoke_test.py`, `README.md`, `CHANGELOG.md`, `TODO.md`, the Plan 2A spec (implementation notes).

## Task 0: Branch and draft PR

**Files:** none.

- [ ] **Step 1: Confirm the docs PR for the spec and this plan is merged**

Run: `gh pr list --state all --limit 3`
Expected: the `docs/plan-2a` PR shows `MERGED`. If it does not, stop and ask James (do not stack branches).

- [ ] **Step 2: Branch from a fresh main**

```bash
git checkout main && git pull
git checkout -b feat/plan-2a-review-engine
```

- [ ] **Step 3: Open the draft PR after the first commit (Task 1)**

After Task 1's commit: `git push -u origin feat/plan-2a-review-engine` then `gh pr create --draft --title "Plan 2A: review engine backend" --body "<summary>\n\n🤖 Generated with [Claude Code](https://claude.com/claude-code)"`. A draft PR early means CI runs on every push (ubuntu, windows, macOS).

---

## Task 1: Dependencies, domain types, scheduler

**Files:**
- Modify: `pyproject.toml`, `uv.lock` (via `uv add`)
- Create: `src/bunsho/models/review.py`
- Modify: `src/bunsho/services/protocols.py`
- Create: `src/bunsho/services/fsrs_scheduler.py`
- Modify: `src/bunsho/factories.py`
- Test: `tests/unit/models/test_review.py`, `tests/unit/services/test_fsrs_scheduler.py`, `tests/unit/test_review_factories.py`

**Interfaces:**
- Produces (used by every later task):
  - `models.review`: `ItemType` (`KANA|KANJI|VOCAB`, str values `"kana"|"kanji"|"vocab"`), `CardDirection` (7 members, property `.item_type`), `DIRECTIONS_BY_TYPE: dict[ItemType, tuple[CardDirection, ...]]`, `Grade` (`AGAIN=1..EASY=4`), `SchedState` (`NEW=0, LEARNING=1, REVIEW=2, RELEARNING=3`), `CardKey(item_id: str, direction: CardDirection)` frozen dataclass with property `item_type`, `CardSchedule` (frozen pydantic: `state: SchedState`, `step: int | None`, `stability: float | None`, `difficulty: float | None`, `due: AwareDatetime`, `last_review: AwareDatetime | None`), `CatalogEntry(item_id: str, item_type: ItemType, level: JlptLevel | None, position: int)`, exceptions `ReviewError`, `StaleReviewError`, `UnknownItemError`, `ContentNotReadyError` (all subclass `ReviewError`).
  - `services.protocols.Scheduler`: `initial(now) -> CardSchedule`, `schedule(current, grade, now) -> CardSchedule`, `preview(current, now) -> dict[Grade, CardSchedule]`.
  - `services.fsrs_scheduler.FSRSScheduler(*, desired_retention: float = 0.9, enable_fuzzing: bool = True)`.
  - `factories.create_scheduler(kind: str = "fsrs", *, desired_retention: float = 0.9, enable_fuzzing: bool = True) -> Scheduler` (`ValueError` for an unknown kind).

- [ ] **Step 1: Add the dependencies and inspect the real py-fsrs API**

```bash
unset VIRTUAL_ENV
uv add py-fsrs tzdata
PYTHONIOENCODING=utf-8 uv run python -c "import fsrs, inspect; print(inspect.signature(fsrs.Scheduler.__init__)); print(inspect.signature(fsrs.Card.__init__)); print(list(fsrs.State)); print(list(fsrs.Rating)); print(inspect.signature(fsrs.Scheduler.review_card))"
```
Expected: `Scheduler.__init__` accepts `desired_retention`, `learning_steps`, `enable_fuzzing`; `Card.__init__` accepts `state, step, stability, difficulty, due, last_review` (and an optional `card_id`); `State` has `Learning=1, Review=2, Relearning=3` (there is **no** "new" state; a fresh card is a Learning card at step 0); `review_card(card, rating, review_datetime, review_duration)` returns `(Card, ReviewLog)`.
If a signature differs from this, adapt only `_to_card` / `_from_card` in Step 6 and record the difference in the commit message.

- [ ] **Step 2: Write the failing model tests**

Create `tests/unit/models/test_review.py`:

```python
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from bunsho.models.review import (
    DIRECTIONS_BY_TYPE,
    CardDirection,
    CardKey,
    CardSchedule,
    Grade,
    ItemType,
    ReviewError,
    SchedState,
    StaleReviewError,
    UnknownItemError,
)


def test_every_direction_belongs_to_exactly_one_item_type() -> None:
    listed = [d for directions in DIRECTIONS_BY_TYPE.values() for d in directions]
    assert sorted(listed) == sorted(CardDirection)
    assert len(listed) == len(set(listed))


@pytest.mark.parametrize(
    ("item_type", "count"), [(ItemType.KANA, 2), (ItemType.KANJI, 3), (ItemType.VOCAB, 2)]
)
def test_direction_counts_per_type(item_type: ItemType, count: int) -> None:
    assert len(DIRECTIONS_BY_TYPE[item_type]) == count


@pytest.mark.parametrize(
    ("direction", "item_type"),
    [
        (CardDirection.GLYPH_TO_SOUND, ItemType.KANA),
        (CardDirection.SOUND_TO_GLYPH, ItemType.KANA),
        (CardDirection.KANJI_TO_MEANING, ItemType.KANJI),
        (CardDirection.KANJI_TO_READING, ItemType.KANJI),
        (CardDirection.MEANING_TO_KANJI, ItemType.KANJI),
        (CardDirection.RECOGNITION, ItemType.VOCAB),
        (CardDirection.RECALL, ItemType.VOCAB),
    ],
)
def test_a_direction_knows_its_item_type(direction: CardDirection, item_type: ItemType) -> None:
    assert direction.item_type is item_type
    assert CardKey("opaque:id", direction).item_type is item_type


def test_grades_and_states_use_the_documented_numbers() -> None:
    assert [g.value for g in Grade] == [1, 2, 3, 4]
    assert [s.value for s in SchedState] == [0, 1, 2, 3]


def test_card_schedule_rejects_naive_datetimes() -> None:
    with pytest.raises(ValidationError):
        CardSchedule(state=SchedState.NEW, due=datetime(2026, 9, 20, 12, 0))


def test_card_schedule_is_frozen() -> None:
    schedule = CardSchedule(state=SchedState.NEW, due=datetime(2026, 9, 20, tzinfo=UTC))
    with pytest.raises(ValidationError):
        schedule.state = SchedState.REVIEW  # type: ignore[misc]


def test_review_errors_share_a_base() -> None:
    assert issubclass(StaleReviewError, ReviewError)
    assert issubclass(UnknownItemError, ReviewError)
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/models/test_review.py -q`
Expected: FAIL (`ModuleNotFoundError: bunsho.models.review`).

- [ ] **Step 4: Implement the domain types**

Create `src/bunsho/models/review.py`:

```python
"""Domain types for the review engine: cards, grades, scheduling state and errors."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum, StrEnum

from pydantic import AwareDatetime, BaseModel, ConfigDict

from bunsho.models.content import JlptLevel


class ItemType(StrEnum):
    """The kind of content a card is about."""

    KANA = "kana"
    KANJI = "kanji"
    VOCAB = "vocab"


class CardDirection(StrEnum):
    """Which way a card asks its question. Each direction belongs to one item type."""

    GLYPH_TO_SOUND = "glyph_to_sound"
    SOUND_TO_GLYPH = "sound_to_glyph"
    KANJI_TO_MEANING = "kanji_to_meaning"
    KANJI_TO_READING = "kanji_to_reading"
    MEANING_TO_KANJI = "meaning_to_kanji"
    RECOGNITION = "recognition"
    RECALL = "recall"

    @property
    def item_type(self) -> ItemType:
        """The item type this direction belongs to."""
        return _TYPE_BY_DIRECTION[self]


DIRECTIONS_BY_TYPE: dict[ItemType, tuple[CardDirection, ...]] = {
    ItemType.KANA: (CardDirection.GLYPH_TO_SOUND, CardDirection.SOUND_TO_GLYPH),
    ItemType.KANJI: (
        CardDirection.KANJI_TO_MEANING,
        CardDirection.KANJI_TO_READING,
        CardDirection.MEANING_TO_KANJI,
    ),
    ItemType.VOCAB: (CardDirection.RECOGNITION, CardDirection.RECALL),
}

_TYPE_BY_DIRECTION: dict[CardDirection, ItemType] = {
    direction: item_type
    for item_type, directions in DIRECTIONS_BY_TYPE.items()
    for direction in directions
}


class Grade(IntEnum):
    """How well the card was recalled."""

    AGAIN = 1
    HARD = 2
    GOOD = 3
    EASY = 4


class SchedState(IntEnum):
    """Scheduling state. ``NEW`` means the card has no ``card_state`` row yet."""

    NEW = 0
    LEARNING = 1
    REVIEW = 2
    RELEARNING = 3


@dataclass(frozen=True, slots=True)
class CardKey:
    """Identity of a card: a content item plus a direction.

    ``item_id`` is an opaque content id (for example ``vocab:度:ど#2``); nothing parses it.
    """

    item_id: str
    direction: CardDirection

    @property
    def item_type(self) -> ItemType:
        """The item type, derived from the direction."""
        return self.direction.item_type


class CardSchedule(BaseModel):
    """FSRS scheduling state of one card; mirrors the ``card_state`` columns."""

    model_config = ConfigDict(frozen=True)

    state: SchedState
    step: int | None = None
    stability: float | None = None
    difficulty: float | None = None
    due: AwareDatetime
    last_review: AwareDatetime | None = None


@dataclass(frozen=True, slots=True)
class CatalogEntry:
    """One content item as the new-card policies see it.

    ``position`` is the item's index in ``content.db`` study order; ``level`` is ``None``
    for kana.
    """

    item_id: str
    item_type: ItemType
    level: JlptLevel | None
    position: int


class ReviewError(Exception):
    """Base class for review-engine errors the API maps to HTTP statuses."""


class StaleReviewError(ReviewError):
    """The card changed since the client fetched it (409)."""


class UnknownItemError(ReviewError):
    """The item id does not exist in the content database (404)."""


class ContentNotReadyError(ReviewError):
    """``content.db`` is missing, unreadable or has the wrong schema version (503)."""
```

- [ ] **Step 5: Run the model tests, then write the failing scheduler tests**

Run: `uv run pytest tests/unit/models/test_review.py -q` → Expected: PASS.

Create `tests/unit/services/test_fsrs_scheduler.py`:

```python
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from bunsho.models.review import CardSchedule, Grade, SchedState
from bunsho.services.fsrs_scheduler import FSRSScheduler

NOW = datetime(2026, 9, 20, 12, 0, tzinfo=UTC)


def make(retention: float = 0.9) -> FSRSScheduler:
    return FSRSScheduler(desired_retention=retention, enable_fuzzing=False)


def test_initial_card_is_new_and_due_now() -> None:
    card = make().initial(NOW)
    assert card.state is SchedState.NEW
    assert card.due == NOW
    assert card.last_review is None
    assert card.stability is None


def test_good_on_a_new_card_records_the_review() -> None:
    scheduler = make()
    after = scheduler.schedule(scheduler.initial(NOW), Grade.GOOD, NOW)
    assert after.state in {SchedState.LEARNING, SchedState.REVIEW}
    assert after.last_review == NOW
    assert after.due > NOW
    assert after.stability is not None
    assert after.difficulty is not None


def test_again_on_a_new_card_comes_back_within_the_hour() -> None:
    scheduler = make()
    after = scheduler.schedule(scheduler.initial(NOW), Grade.AGAIN, NOW)
    assert after.state is SchedState.LEARNING
    assert NOW < after.due <= NOW + timedelta(hours=1)


def test_easy_on_a_new_card_graduates_to_review_a_day_or_more_out() -> None:
    scheduler = make()
    after = scheduler.schedule(scheduler.initial(NOW), Grade.EASY, NOW)
    assert after.state is SchedState.REVIEW
    assert after.due >= NOW + timedelta(days=1)


def test_again_on_a_review_card_relearns() -> None:
    scheduler = make()
    review = scheduler.schedule(scheduler.initial(NOW), Grade.EASY, NOW)
    lapsed = scheduler.schedule(review, Grade.AGAIN, review.due)
    assert lapsed.state is SchedState.RELEARNING
    assert lapsed.due > review.due


@pytest.mark.parametrize("first_grade", [None, Grade.EASY])
def test_a_better_grade_never_schedules_sooner(first_grade: Grade | None) -> None:
    scheduler = make()
    card = scheduler.initial(NOW)
    moment = NOW
    if first_grade is not None:
        card = scheduler.schedule(card, first_grade, NOW)
        moment = card.due
    preview = scheduler.preview(card, moment)
    dues = [preview[grade].due for grade in (Grade.AGAIN, Grade.HARD, Grade.GOOD, Grade.EASY)]
    assert dues == sorted(dues)


def test_preview_matches_actual_scheduling_when_fuzzing_is_off() -> None:
    scheduler = make()
    card = scheduler.initial(NOW)
    preview = scheduler.preview(card, NOW)
    for grade in Grade:
        assert preview[grade] == scheduler.schedule(card, grade, NOW)


def test_a_higher_target_retention_schedules_sooner() -> None:
    base = make()
    review = base.schedule(base.initial(NOW), Grade.EASY, NOW)
    high = make(0.97).schedule(review, Grade.GOOD, review.due)
    low = make(0.80).schedule(review, Grade.GOOD, review.due)
    assert high.due < low.due


def test_a_naive_now_is_rejected() -> None:
    scheduler = make()
    with pytest.raises(ValueError, match="timezone"):
        scheduler.schedule(scheduler.initial(NOW), Grade.GOOD, datetime(2026, 9, 20, 12, 0))


def test_a_non_utc_now_is_normalised_to_utc() -> None:
    scheduler = make()
    tokyo = NOW.astimezone(ZoneInfo("Asia/Tokyo"))
    after = scheduler.schedule(scheduler.initial(NOW), Grade.GOOD, tokyo)
    assert after.last_review == NOW
    assert after.due.utcoffset() == timedelta(0)


def test_schedule_does_not_mutate_its_input() -> None:
    scheduler = make()
    card = scheduler.initial(NOW)
    snapshot = card.model_copy()
    scheduler.schedule(card, Grade.GOOD, NOW)
    assert card == snapshot


def test_states_round_trip_through_card_schedule() -> None:
    scheduler = make()
    review = scheduler.schedule(scheduler.initial(NOW), Grade.EASY, NOW)
    assert CardSchedule.model_validate(review.model_dump()) == review
```

- [ ] **Step 6: Run to verify failure, then add the `Scheduler` protocol and `FSRSScheduler`**

Run: `uv run pytest tests/unit/services/test_fsrs_scheduler.py -q` → Expected: FAIL (`ModuleNotFoundError: bunsho.services.fsrs_scheduler`).

In `src/bunsho/services/protocols.py` change the imports and append the protocol:

```python
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Protocol

from bunsho.models.content import ImportedDeck, Kana, Kanji, KanjiDetails, Vocab
from bunsho.models.review import CardSchedule, Grade
```

```python
class Scheduler(Protocol):
    """Spaced-repetition scheduling: what happens to a card when it is graded."""

    def initial(self, now: datetime) -> CardSchedule:
        """Return the state of a card that has never been reviewed (``SchedState.NEW``)."""
        ...

    def schedule(self, current: CardSchedule, grade: Grade, now: datetime) -> CardSchedule:
        """Return the state after grading ``current`` at ``now``.

        Raises:
            ValueError: ``now`` is not timezone-aware.
        """
        ...

    def preview(self, current: CardSchedule, now: datetime) -> dict[Grade, CardSchedule]:
        """Return the state each of the four grades would produce (never fuzzed)."""
        ...
```

Create `src/bunsho/services/fsrs_scheduler.py`:

```python
"""FSRS scheduling behind the ``Scheduler`` protocol."""

from __future__ import annotations

from datetime import UTC, datetime

from fsrs import Card, Rating, State
from fsrs import Scheduler as _FsrsScheduler

from bunsho.models.review import CardSchedule, Grade, SchedState

_RATINGS: dict[Grade, Rating] = {
    Grade.AGAIN: Rating.Again,
    Grade.HARD: Rating.Hard,
    Grade.GOOD: Rating.Good,
    Grade.EASY: Rating.Easy,
}


def _utc(now: datetime) -> datetime:
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware (a naive datetime has no timezone)")
    return now.astimezone(UTC)


def _to_card(current: CardSchedule, now: datetime) -> Card:
    if current.state is SchedState.NEW:
        # py-fsrs has no "new" state: a fresh card is a Learning card at step 0.
        return Card(
            state=State.Learning,
            step=0,
            stability=None,
            difficulty=None,
            due=now,
            last_review=None,
        )
    return Card(
        state=State(int(current.state)),
        step=current.step,
        stability=current.stability,
        difficulty=current.difficulty,
        due=current.due,
        last_review=current.last_review,
    )


def _from_card(card: Card) -> CardSchedule:
    return CardSchedule(
        state=SchedState(int(card.state)),
        step=card.step,
        stability=card.stability,
        difficulty=card.difficulty,
        due=card.due,
        last_review=card.last_review,
    )


def _review(
    scheduler: _FsrsScheduler, current: CardSchedule, grade: Grade, now: datetime
) -> CardSchedule:
    moment = _utc(now)
    reviewed, _log = scheduler.review_card(_to_card(current, moment), _RATINGS[grade], moment)
    return _from_card(reviewed)


class FSRSScheduler:
    """``Scheduler`` implementation backed by ``py-fsrs``."""

    def __init__(self, *, desired_retention: float = 0.9, enable_fuzzing: bool = True) -> None:
        """Create the scheduler.

        Args:
            desired_retention: Target probability of recall when a card comes due.
            enable_fuzzing: Spread review-state intervals randomly (turn off in tests).
        """
        self._scheduler = _FsrsScheduler(
            desired_retention=desired_retention, enable_fuzzing=enable_fuzzing
        )
        # Button labels must not jitter, so previews always use a fuzz-free scheduler.
        self._preview_scheduler = _FsrsScheduler(
            desired_retention=desired_retention, enable_fuzzing=False
        )

    def initial(self, now: datetime) -> CardSchedule:
        """Return the state of a card that has never been reviewed.

        Args:
            now: The current time (timezone-aware).

        Returns:
            A ``NEW`` schedule that is due immediately.

        Raises:
            ValueError: ``now`` is not timezone-aware.
        """
        return CardSchedule(state=SchedState.NEW, due=_utc(now))

    def schedule(self, current: CardSchedule, grade: Grade, now: datetime) -> CardSchedule:
        """Return the state after grading ``current`` at ``now``.

        Args:
            current: The card's state before this review.
            grade: How well it was recalled.
            now: The review time (timezone-aware; converted to UTC).

        Returns:
            The new state, with ``last_review == now``.

        Raises:
            ValueError: ``now`` is not timezone-aware.
        """
        return _review(self._scheduler, current, grade, now)

    def preview(self, current: CardSchedule, now: datetime) -> dict[Grade, CardSchedule]:
        """Return the state each grade would produce, without fuzzing.

        Args:
            current: The card's state.
            now: The review time (timezone-aware).

        Returns:
            One state per ``Grade``.

        Raises:
            ValueError: ``now`` is not timezone-aware.
        """
        return {grade: _review(self._preview_scheduler, current, grade, now) for grade in Grade}
```

If `mypy` later reports `module is installed, but missing library stubs or py.typed marker` for `fsrs`, add `"fsrs"` to the `ignore_missing_imports` override list in `pyproject.toml` (`[[tool.mypy.overrides]]`).

- [ ] **Step 7: Run the scheduler tests**

Run: `uv run pytest tests/unit/services/test_fsrs_scheduler.py -q`
Expected: PASS. If `test_easy_on_a_new_card_graduates...` or the monotonic test fails, print the values (`PYTHONIOENCODING=utf-8 uv run python -c ...`) before loosening anything; the assertions encode documented FSRS behaviour.

- [ ] **Step 8: Write the failing factory tests and add `create_scheduler`**

Create `tests/unit/test_review_factories.py`:

```python
from datetime import UTC, datetime

import pytest

from bunsho.factories import create_scheduler
from bunsho.models.review import Grade
from bunsho.services.fsrs_scheduler import FSRSScheduler


def test_create_scheduler_builds_the_fsrs_scheduler_by_default() -> None:
    assert isinstance(create_scheduler(), FSRSScheduler)


def test_create_scheduler_passes_the_retention_through() -> None:
    now = datetime(2026, 9, 20, 12, tzinfo=UTC)
    high = create_scheduler("fsrs", desired_retention=0.97, enable_fuzzing=False)
    low = create_scheduler("fsrs", desired_retention=0.80, enable_fuzzing=False)
    review = high.schedule(high.initial(now), Grade.EASY, now)
    assert high.schedule(review, Grade.GOOD, review.due).due < low.schedule(
        review, Grade.GOOD, review.due
    ).due


def test_create_scheduler_rejects_unknown_kinds() -> None:
    with pytest.raises(ValueError, match="sm2"):
        create_scheduler("sm2")
```

In `src/bunsho/factories.py` add imports (with their first use) and the function. Imports to add: `from bunsho.services.fsrs_scheduler import FSRSScheduler` and extend the protocols import to `from bunsho.services.protocols import KanjiCatalog, KanjiInfoSource, Scheduler`. Append:

```python
def create_scheduler(
    kind: str = "fsrs", *, desired_retention: float = 0.9, enable_fuzzing: bool = True
) -> Scheduler:
    """Build the spaced-repetition scheduler named by ``kind``.

    Args:
        kind: Scheduler algorithm; only ``"fsrs"`` is supported today.
        desired_retention: Target probability of recall when a card comes due.
        enable_fuzzing: Spread review intervals randomly (disable for deterministic tests).

    Returns:
        The scheduler.

    Raises:
        ValueError: ``kind`` is not a supported scheduler.
    """
    match kind:
        case "fsrs":
            return FSRSScheduler(desired_retention=desired_retention, enable_fuzzing=enable_fuzzing)
        case _:
            raise ValueError(f"unsupported scheduler {kind!r}; supported: 'fsrs'")
```

- [ ] **Step 9: Run everything for this task, lint, commit**

```bash
uv run pytest tests/unit/models/test_review.py tests/unit/services/test_fsrs_scheduler.py tests/unit/test_review_factories.py -q
uv run ruff format . && uv run ruff check . && uv run mypy
git add pyproject.toml uv.lock src/bunsho/models/review.py src/bunsho/services/protocols.py src/bunsho/services/fsrs_scheduler.py src/bunsho/factories.py tests/unit/models/test_review.py tests/unit/services/test_fsrs_scheduler.py tests/unit/test_review_factories.py
git commit -m "feat: review domain types and FSRS scheduler" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```
Expected: all pass. Then push and open the draft PR (Task 0, Step 3).

---

## Task 2: `progress.db` repository, WAL and foreign keys

**Files:**
- Modify: `src/bunsho/db/engine.py`
- Create: `src/bunsho/db/timestamps.py`, `src/bunsho/db/progress_repository.py`
- Modify: `tests/base.py`
- Test: `tests/unit/db/test_engine.py` (append), `tests/unit/db/test_timestamps.py`, `tests/unit/db/test_progress_repository.py`, `tests/unit/db/test_migrate.py` (append)

**Interfaces:**
- Consumes: Task 1 (`CardKey`, `CardSchedule`, `Grade`, `SchedState`, `CardDirection`, `ItemType`, `StaleReviewError`).
- Produces:
  - `db.timestamps.format_timestamp(value: datetime) -> str`, `parse_timestamp(text: str) -> datetime` (UTC-aware).
  - `db.progress_repository`: `StoredCard(key: CardKey, schedule: CardSchedule, reps: int, lapses: int)`, `ReviewRecord(reviewed_at: datetime, grade: Grade, state_before: SchedState, direction: CardDirection)`, and `ProgressRepository(database: ProgressDatabase)` with async methods:
    - `get_card(key) -> StoredCard | None`
    - `due_cards(now, limit) -> list[StoredCard]` (earliest due first)
    - `due_counts(now) -> dict[ItemType, int]`
    - `next_due_after(now) -> datetime | None`
    - `card_states() -> dict[CardKey, SchedState]`
    - `new_cards_introduced(start, end) -> dict[ItemType, int]`
    - `reviews_between(start, end) -> list[ReviewRecord]` (`start` inclusive, `end` exclusive, oldest first)
    - `record_review(key, *, before, after, grade, mode, duration_ms) -> None` (raises `StaleReviewError`)
    - `get_setting(key) -> str | None`, `set_setting(key, value) -> None`
  - `tests.base.make_progress_database(tmp_path) -> ProgressDatabase` and `tests.base.run_with_database(tmp_path, scenario)`.

- [ ] **Step 1: Write the failing engine tests (WAL, foreign keys)**

Append to `tests/unit/db/test_engine.py` (add `from sqlalchemy import text` to its imports):

```python
def test_connections_use_wal_and_enforce_foreign_keys(tmp_path: Path) -> None:
    path = tmp_path / "progress.db"
    run_migrations(path, backup_dir=tmp_path / "backups")

    async def scenario() -> tuple[str, int, int]:
        database = ProgressDatabase(path)
        try:
            async with database.sessions() as session:
                mode = (await session.execute(text("PRAGMA journal_mode"))).scalar_one()
                foreign_keys = (await session.execute(text("PRAGMA foreign_keys"))).scalar_one()
                synchronous = (await session.execute(text("PRAGMA synchronous"))).scalar_one()
            return mode, foreign_keys, synchronous
        finally:
            await database.dispose()

    # synchronous=1 is NORMAL, the recommended pairing with WAL.
    assert asyncio.run(scenario()) == ("wal", 1, 1)
```

Run: `uv run pytest tests/unit/db/test_engine.py -q` → Expected: the new test FAILS (`'delete'`).

- [ ] **Step 2: Add the connect hook to `ProgressDatabase`**

In `src/bunsho/db/engine.py` change the imports and add the hook:

```python
from pathlib import Path
from typing import Any

from sqlalchemy import event, text
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


def _configure_connection(dbapi_connection: Any, _connection_record: Any) -> None:
    """Apply the pragmas every ``progress.db`` connection needs.

    WAL lets readers proceed while a review is being written and is persistent in the file;
    ``foreign_keys`` is per connection and must be set each time.
    """
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA foreign_keys=ON")
    finally:
        cursor.close()
```

and in `ProgressDatabase.__init__`, right after `self._engine = create_async_engine(...)`:

```python
        event.listen(self._engine.sync_engine, "connect", _configure_connection)
```

Also extend the class docstring with one sentence: "Every connection runs in WAL mode with foreign keys enforced."
Run: `uv run pytest tests/unit/db/test_engine.py -q` → Expected: PASS.

- [ ] **Step 3: Prove the startup backup is WAL-safe**

Append to `tests/unit/db/test_migrate.py` (imports it already has are enough plus `sqlite3`, `closing`, `asyncio`; add whatever is missing):

```python
def test_backup_of_a_wal_database_contains_uncheckpointed_writes(tmp_path: Path) -> None:
    """The pre-migration backup uses the SQLite backup API, so WAL content is not lost."""
    from bunsho.db.engine import ProgressDatabase
    from bunsho.db.migrate import _backup

    db_path = tmp_path / "progress.db"
    run_migrations(db_path, backup_dir=tmp_path / "backups")

    async def write() -> None:
        database = ProgressDatabase(db_path)
        try:
            async with database.sessions() as session, session.begin():
                session.add(AppSetting(key="wal-marker", value="kept"))
        finally:
            await database.dispose()

    asyncio.run(write())
    backup = _backup(db_path, tmp_path / "backups", "0001", datetime.now(UTC))
    with closing(sqlite3.connect(backup)) as con:
        rows = con.execute("SELECT value FROM app_setting WHERE key = 'wal-marker'").fetchall()
    assert rows == [("kept",)]
```
Add the imports this needs at the top of that file if absent: `import asyncio`, `import sqlite3`, `from contextlib import closing`, `from datetime import UTC, datetime`, `from bunsho.db.models import AppSetting`.
Run: `uv run pytest tests/unit/db/test_migrate.py -q` → Expected: PASS. (If it fails, the backup is not WAL-safe: switch `_backup` to `VACUUM INTO` or fix the copy before continuing.)

- [ ] **Step 4: Write the timestamp tests and module**

Create `tests/unit/db/test_timestamps.py`:

```python
from datetime import UTC, datetime, timedelta, timezone

import pytest

from bunsho.db.timestamps import format_timestamp, parse_timestamp


def test_format_is_fixed_width_utc() -> None:
    assert format_timestamp(datetime(2026, 9, 20, 12, 0, tzinfo=UTC)) == "2026-09-20T12:00:00.000000Z"
    assert len(format_timestamp(datetime(2026, 1, 2, 3, 4, 5, 6, tzinfo=UTC))) == 27


def test_round_trip_keeps_microseconds() -> None:
    moment = datetime(2026, 9, 20, 12, 0, 1, 123456, tzinfo=UTC)
    assert parse_timestamp(format_timestamp(moment)) == moment


def test_other_offsets_are_converted_to_utc() -> None:
    tokyo = timezone(timedelta(hours=9))
    assert format_timestamp(datetime(2026, 9, 20, 21, 0, tzinfo=tokyo)) == (
        "2026-09-20T12:00:00.000000Z"
    )


def test_lexicographic_order_matches_time_order() -> None:
    earlier = format_timestamp(datetime(2026, 9, 20, 12, 0, 0, 5, tzinfo=UTC))
    later = format_timestamp(datetime(2026, 9, 20, 12, 0, 1, tzinfo=UTC))
    assert earlier < later


def test_naive_datetimes_are_rejected() -> None:
    with pytest.raises(ValueError, match="timezone"):
        format_timestamp(datetime(2026, 9, 20, 12, 0))
```

Create `src/bunsho/db/timestamps.py`:

```python
"""Fixed-width UTC timestamp strings for ``progress.db``.

The width is fixed so that ``due <= :now`` comparisons in SQL are ordinary string comparisons.
"""

from __future__ import annotations

from datetime import UTC, datetime

_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"


def format_timestamp(value: datetime) -> str:
    """Format ``value`` as a UTC string such as ``2026-09-20T12:00:00.000000Z``.

    Args:
        value: A timezone-aware datetime.

    Returns:
        The 27-character UTC string.

    Raises:
        ValueError: ``value`` is naive.
    """
    if value.tzinfo is None:
        raise ValueError("timestamps must be timezone-aware (a naive datetime has no timezone)")
    return value.astimezone(UTC).strftime(_FORMAT)


def parse_timestamp(text: str) -> datetime:
    """Parse a string written by ``format_timestamp`` into an aware UTC datetime.

    Raises:
        ValueError: ``text`` is not in the stored format.
    """
    return datetime.strptime(text, _FORMAT).replace(tzinfo=UTC)
```
Run: `uv run pytest tests/unit/db/test_timestamps.py -q` → Expected: PASS (the format test may need `strftime("%f")` zero-padding: it produces 6 digits).

- [ ] **Step 5: Add the shared test helpers**

In `tests/base.py` add imports `import asyncio`, `from collections.abc import Awaitable, Callable`, `from bunsho.db.engine import ProgressDatabase`, `from bunsho.db.migrate import run_migrations` (each with its first use below) and append:

```python
def make_progress_database(tmp_path: Path) -> ProgressDatabase:
    """Migrate a fresh ``progress.db`` under ``tmp_path`` and open it."""
    path = tmp_path / "progress.db"
    run_migrations(path, backup_dir=tmp_path / "backups")
    return ProgressDatabase(path)


def run_with_database[T](
    tmp_path: Path, scenario: Callable[[ProgressDatabase], Awaitable[T]]
) -> T:
    """Run ``scenario`` against a fresh migrated ``progress.db`` and dispose the engine.

    The suite has no pytest-asyncio; async tests are plain functions that call this.
    """
    database = make_progress_database(tmp_path)

    async def main() -> T:
        try:
            return await scenario(database)
        finally:
            await database.dispose()

    return asyncio.run(main())
```

- [ ] **Step 6: Write the failing repository tests**

Create `tests/unit/db/test_progress_repository.py`:

```python
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from bunsho.db.engine import ProgressDatabase
from bunsho.db.progress_repository import ProgressRepository
from bunsho.models.review import (
    CardDirection,
    CardKey,
    Grade,
    ItemType,
    SchedState,
    StaleReviewError,
)
from bunsho.services.fsrs_scheduler import FSRSScheduler
from tests.base import run_with_database

NOW = datetime(2026, 9, 20, 12, 0, tzinfo=UTC)
KANA = CardKey("kana:hira:あ", CardDirection.GLYPH_TO_SOUND)
VOCAB = CardKey("vocab:日本:にほん", CardDirection.RECOGNITION)
SCHEDULER = FSRSScheduler(enable_fuzzing=False)


async def _review(
    repo: ProgressRepository, key: CardKey, grade: Grade, at: datetime
) -> None:
    stored = await repo.get_card(key)
    before = stored.schedule if stored else SCHEDULER.initial(at)
    after = SCHEDULER.schedule(before, grade, at)
    await repo.record_review(
        key, before=before, after=after, grade=grade, mode="flip", duration_ms=1200
    )


def test_the_first_review_creates_the_card_and_logs_it(tmp_path: Path) -> None:
    async def scenario(db: ProgressDatabase) -> None:
        repo = ProgressRepository(db)
        assert await repo.get_card(KANA) is None
        await _review(repo, KANA, Grade.GOOD, NOW)
        stored = await repo.get_card(KANA)
        assert stored is not None
        assert stored.key == KANA
        assert stored.reps == 1
        assert stored.lapses == 0
        assert stored.schedule.last_review == NOW
        assert stored.schedule.state in {SchedState.LEARNING, SchedState.REVIEW}
        [record] = await repo.reviews_between(NOW - timedelta(days=1), NOW + timedelta(days=1))
        assert record.grade is Grade.GOOD
        assert record.state_before is SchedState.NEW
        assert record.direction is CardDirection.GLYPH_TO_SOUND
        assert record.reviewed_at == NOW

    run_with_database(tmp_path, scenario)


def test_later_reviews_update_the_card_and_count_lapses(tmp_path: Path) -> None:
    async def scenario(db: ProgressDatabase) -> None:
        repo = ProgressRepository(db)
        await _review(repo, VOCAB, Grade.EASY, NOW)
        first = await repo.get_card(VOCAB)
        assert first is not None
        assert first.schedule.state is SchedState.REVIEW
        await _review(repo, VOCAB, Grade.AGAIN, first.schedule.due)
        second = await repo.get_card(VOCAB)
        assert second is not None
        assert (second.reps, second.lapses) == (2, 1)
        assert second.schedule.state is SchedState.RELEARNING
        records = await repo.reviews_between(NOW - timedelta(days=1), NOW + timedelta(days=400))
        assert [r.state_before for r in records] == [SchedState.NEW, SchedState.REVIEW]

    run_with_database(tmp_path, scenario)


def test_recording_a_new_card_twice_is_a_stale_review(tmp_path: Path) -> None:
    async def scenario(db: ProgressDatabase) -> None:
        repo = ProgressRepository(db)
        before = SCHEDULER.initial(NOW)
        after = SCHEDULER.schedule(before, Grade.GOOD, NOW)
        await repo.record_review(
            KANA, before=before, after=after, grade=Grade.GOOD, mode="flip", duration_ms=None
        )
        with pytest.raises(StaleReviewError):
            await repo.record_review(
                KANA, before=before, after=after, grade=Grade.GOOD, mode="flip", duration_ms=None
            )
        records = await repo.reviews_between(NOW - timedelta(days=1), NOW + timedelta(days=1))
        assert len(records) == 1

    run_with_database(tmp_path, scenario)


def test_a_review_based_on_an_outdated_state_is_stale_and_leaves_no_log(
    tmp_path: Path,
) -> None:
    async def scenario(db: ProgressDatabase) -> None:
        repo = ProgressRepository(db)
        await _review(repo, VOCAB, Grade.GOOD, NOW)
        outdated = (await repo.get_card(VOCAB))
        assert outdated is not None
        await _review(repo, VOCAB, Grade.GOOD, NOW + timedelta(minutes=11))
        after = SCHEDULER.schedule(outdated.schedule, Grade.GOOD, NOW + timedelta(minutes=12))
        with pytest.raises(StaleReviewError):
            await repo.record_review(
                VOCAB,
                before=outdated.schedule,
                after=after,
                grade=Grade.GOOD,
                mode="flip",
                duration_ms=None,
            )
        records = await repo.reviews_between(NOW - timedelta(days=1), NOW + timedelta(days=1))
        assert len(records) == 2  # the rejected review was not logged

    run_with_database(tmp_path, scenario)


def test_a_failure_after_the_card_write_rolls_the_card_back(tmp_path: Path) -> None:
    async def scenario(db: ProgressDatabase) -> None:
        repo = ProgressRepository(db)
        before = SCHEDULER.initial(NOW)
        after = SCHEDULER.schedule(before, Grade.GOOD, NOW)
        # The card row is flushed first; building the log row then fails on ``int(grade)``.
        with pytest.raises(TypeError):
            await repo.record_review(
                KANA,
                before=before,
                after=after,
                grade=None,  # type: ignore[arg-type]
                mode="flip",
                duration_ms=None,
            )
        assert await repo.get_card(KANA) is None
        assert await repo.reviews_between(NOW - timedelta(days=1), NOW + timedelta(days=1)) == []

    run_with_database(tmp_path, scenario)


def test_due_cards_are_ordered_and_limited(tmp_path: Path) -> None:
    async def scenario(db: ProgressDatabase) -> None:
        repo = ProgressRepository(db)
        await _review(repo, VOCAB, Grade.GOOD, NOW)  # due in about ten minutes
        await _review(repo, KANA, Grade.AGAIN, NOW)  # due in about one minute
        later = NOW + timedelta(hours=1)
        due = await repo.due_cards(later, limit=10)
        assert [c.key for c in due] == [KANA, VOCAB]
        assert [c.key for c in await repo.due_cards(later, limit=1)] == [KANA]
        assert await repo.due_cards(NOW, limit=10) == []
        assert await repo.due_counts(later) == {ItemType.KANA: 1, ItemType.VOCAB: 1}
        assert await repo.due_counts(NOW) == {}

    run_with_database(tmp_path, scenario)


def test_next_due_after_finds_the_soonest_future_card(tmp_path: Path) -> None:
    async def scenario(db: ProgressDatabase) -> None:
        repo = ProgressRepository(db)
        assert await repo.next_due_after(NOW) is None
        await _review(repo, VOCAB, Grade.GOOD, NOW)
        await _review(repo, KANA, Grade.AGAIN, NOW)
        soonest = await repo.next_due_after(NOW)
        kana = await repo.get_card(KANA)
        assert kana is not None
        assert soonest == kana.schedule.due
        assert await repo.next_due_after(NOW + timedelta(days=30)) is None

    run_with_database(tmp_path, scenario)


def test_card_states_and_new_cards_introduced(tmp_path: Path) -> None:
    async def scenario(db: ProgressDatabase) -> None:
        repo = ProgressRepository(db)
        await _review(repo, KANA, Grade.GOOD, NOW)
        await _review(repo, VOCAB, Grade.EASY, NOW)
        await _review(repo, VOCAB, Grade.GOOD, NOW + timedelta(days=30))  # not a new card
        states = await repo.card_states()
        assert set(states) == {KANA, VOCAB}
        assert states[VOCAB] is SchedState.REVIEW
        today = (NOW - timedelta(hours=8), NOW + timedelta(hours=16))
        assert await repo.new_cards_introduced(*today) == {ItemType.KANA: 1, ItemType.VOCAB: 1}
        tomorrow = (today[1], today[1] + timedelta(days=1))
        assert await repo.new_cards_introduced(*tomorrow) == {}

    run_with_database(tmp_path, scenario)


def test_reviews_between_treats_the_end_as_exclusive(tmp_path: Path) -> None:
    async def scenario(db: ProgressDatabase) -> None:
        repo = ProgressRepository(db)
        await _review(repo, KANA, Grade.GOOD, NOW)
        assert len(await repo.reviews_between(NOW, NOW + timedelta(seconds=1))) == 1
        assert await repo.reviews_between(NOW - timedelta(seconds=1), NOW) == []

    run_with_database(tmp_path, scenario)


def test_settings_are_upserted(tmp_path: Path) -> None:
    async def scenario(db: ProgressDatabase) -> None:
        repo = ProgressRepository(db)
        assert await repo.get_setting("k") is None
        await repo.set_setting("k", "one")
        await repo.set_setting("k", "two")
        assert await repo.get_setting("k") == "two"

    run_with_database(tmp_path, scenario)
```

Run: `uv run pytest tests/unit/db/test_progress_repository.py -q` → Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 7: Implement `ProgressRepository`**

Create `src/bunsho/db/progress_repository.py`:

```python
"""Async persistence of card scheduling state, the review log and settings."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, cast

from sqlalchemy import func, select, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import IntegrityError

from bunsho.db.engine import ProgressDatabase
from bunsho.db.models import AppSetting, CardState, ReviewLog
from bunsho.db.timestamps import format_timestamp, parse_timestamp
from bunsho.models.review import (
    CardDirection,
    CardKey,
    CardSchedule,
    Grade,
    ItemType,
    SchedState,
    StaleReviewError,
)


@dataclass(frozen=True, slots=True)
class StoredCard:
    """A ``card_state`` row as a domain object."""

    key: CardKey
    schedule: CardSchedule
    reps: int
    lapses: int


@dataclass(frozen=True, slots=True)
class ReviewRecord:
    """The parts of a ``review_log`` row that statistics need."""

    reviewed_at: datetime
    grade: Grade
    state_before: SchedState
    direction: CardDirection


def _stored(row: CardState) -> StoredCard:
    return StoredCard(
        key=CardKey(row.item_id, CardDirection(row.direction)),
        schedule=CardSchedule(
            state=SchedState(row.state),
            step=row.step,
            stability=row.stability,
            difficulty=row.difficulty,
            due=parse_timestamp(row.due),
            last_review=parse_timestamp(row.last_review) if row.last_review else None,
        ),
        reps=row.reps,
        lapses=row.lapses,
    )


class ProgressRepository:
    """Reads and writes ``progress.db``: cards, the review log and settings."""

    def __init__(self, database: ProgressDatabase) -> None:
        """Create the repository.

        Args:
            database: The async engine wrapper for ``progress.db``.
        """
        self._database = database

    async def get_card(self, key: CardKey) -> StoredCard | None:
        """Return the stored card, or ``None`` when it has never been reviewed."""
        async with self._database.sessions() as session:
            row = await session.scalar(
                select(CardState).where(
                    CardState.item_id == key.item_id, CardState.direction == key.direction.value
                )
            )
        return _stored(row) if row else None

    async def due_cards(self, now: datetime, limit: int) -> list[StoredCard]:
        """Return up to ``limit`` cards due at ``now``, earliest due first."""
        statement = (
            select(CardState)
            .where(CardState.due <= format_timestamp(now))
            .order_by(CardState.due, CardState.id)
            .limit(limit)
        )
        async with self._database.sessions() as session:
            rows = (await session.scalars(statement)).all()
        return [_stored(row) for row in rows]

    async def due_counts(self, now: datetime) -> dict[ItemType, int]:
        """Count the cards due at ``now`` per item type (types with none are omitted)."""
        statement = (
            select(CardState.direction, func.count())
            .where(CardState.due <= format_timestamp(now))
            .group_by(CardState.direction)
        )
        async with self._database.sessions() as session:
            rows = (await session.execute(statement)).all()
        return _sum_by_type(rows)

    async def next_due_after(self, now: datetime) -> datetime | None:
        """Return the soonest due time after ``now``, or ``None`` when nothing is scheduled."""
        async with self._database.sessions() as session:
            due = await session.scalar(
                select(func.min(CardState.due)).where(CardState.due > format_timestamp(now))
            )
        return parse_timestamp(due) if due else None

    async def card_states(self) -> dict[CardKey, SchedState]:
        """Return the scheduling state of every card that has been reviewed."""
        async with self._database.sessions() as session:
            rows = (
                await session.execute(
                    select(CardState.item_id, CardState.direction, CardState.state)
                )
            ).all()
        return {
            CardKey(item_id, CardDirection(direction)): SchedState(state)
            for item_id, direction, state in rows
        }

    async def new_cards_introduced(self, start: datetime, end: datetime) -> dict[ItemType, int]:
        """Count first reviews per item type with ``start <= reviewed_at < end``."""
        statement = (
            select(ReviewLog.direction, func.count())
            .where(
                ReviewLog.state_before == int(SchedState.NEW),
                ReviewLog.reviewed_at >= format_timestamp(start),
                ReviewLog.reviewed_at < format_timestamp(end),
            )
            .group_by(ReviewLog.direction)
        )
        async with self._database.sessions() as session:
            rows = (await session.execute(statement)).all()
        return _sum_by_type(rows)

    async def reviews_between(self, start: datetime, end: datetime) -> list[ReviewRecord]:
        """Return reviews with ``start <= reviewed_at < end``, oldest first."""
        statement = (
            select(
                ReviewLog.reviewed_at,
                ReviewLog.grade,
                ReviewLog.state_before,
                ReviewLog.direction,
            )
            .where(
                ReviewLog.reviewed_at >= format_timestamp(start),
                ReviewLog.reviewed_at < format_timestamp(end),
            )
            .order_by(ReviewLog.reviewed_at, ReviewLog.id)
        )
        async with self._database.sessions() as session:
            rows = (await session.execute(statement)).all()
        return [
            ReviewRecord(
                reviewed_at=parse_timestamp(reviewed_at),
                grade=Grade(grade),
                state_before=SchedState(state_before or 0),
                direction=CardDirection(direction),
            )
            for reviewed_at, grade, state_before, direction in rows
        ]

    async def record_review(
        self,
        key: CardKey,
        *,
        before: CardSchedule,
        after: CardSchedule,
        grade: Grade,
        mode: str,
        duration_ms: int | None,
    ) -> None:
        """Store the new card state and append the review log entry in one transaction.

        The write is a compare-and-set: a new card is inserted (the unique constraint
        rejects a second first review), an existing card is updated only if its
        ``last_review`` still equals ``before.last_review``. Either failure means another
        review got there first.

        Args:
            key: The card.
            before: The state the review was based on (``SchedState.NEW`` for a new card).
            after: The state to store; ``after.last_review`` is the review time.
            grade: The grade given.
            mode: The review mode, for example ``"flip"``.
            duration_ms: How long the answer took, if known.

        Raises:
            StaleReviewError: The stored card no longer matches ``before``.
            ValueError: ``after.last_review`` is missing, or ``before`` is not new but
                has no ``last_review``.
        """
        if after.last_review is None:
            raise ValueError("after.last_review is required")
        reviewed_at = format_timestamp(after.last_review)
        is_new = before.state is SchedState.NEW
        if not is_new and before.last_review is None:
            raise ValueError("before.last_review is required for a card that is not new")
        elapsed = (
            None
            if before.last_review is None
            else (after.last_review - before.last_review).total_seconds() / 86400
        )
        lapsed = grade is Grade.AGAIN and before.state is SchedState.REVIEW
        values: dict[str, Any] = {
            "state": int(after.state),
            "step": after.step,
            "stability": after.stability,
            "difficulty": after.difficulty,
            "due": format_timestamp(after.due),
            "last_review": reviewed_at,
        }
        async with self._database.sessions() as session, session.begin():
            if is_new:
                session.add(
                    CardState(
                        item_id=key.item_id,
                        direction=key.direction.value,
                        reps=1,
                        lapses=0,
                        **values,
                    )
                )
                try:
                    await session.flush()
                except IntegrityError as exc:
                    raise StaleReviewError(
                        f"card {key.item_id} ({key.direction.value}) was already reviewed"
                    ) from exc
            else:
                assert before.last_review is not None  # checked above; narrows for mypy
                result = await session.execute(
                    update(CardState)
                    .where(
                        CardState.item_id == key.item_id,
                        CardState.direction == key.direction.value,
                        CardState.last_review == format_timestamp(before.last_review),
                    )
                    .values(
                        reps=CardState.reps + 1,
                        lapses=CardState.lapses + (1 if lapsed else 0),
                        **values,
                    )
                )
                if cast(CursorResult[Any], result).rowcount != 1:
                    raise StaleReviewError(
                        f"card {key.item_id} ({key.direction.value}) changed since it was read"
                    )
            session.add(
                ReviewLog(
                    item_id=key.item_id,
                    direction=key.direction.value,
                    grade=int(grade),
                    mode=mode,
                    reviewed_at=reviewed_at,
                    state_before=int(before.state),
                    stability_before=before.stability,
                    difficulty_before=before.difficulty,
                    elapsed_days=elapsed,
                    duration_ms=duration_ms,
                )
            )

    async def get_setting(self, key: str) -> str | None:
        """Return a stored setting value, or ``None`` when it was never saved."""
        async with self._database.sessions() as session:
            return await session.scalar(select(AppSetting.value).where(AppSetting.key == key))

    async def set_setting(self, key: str, value: str) -> None:
        """Insert or replace a setting."""
        statement = sqlite_insert(AppSetting).values(key=key, value=value)
        statement = statement.on_conflict_do_update(
            index_elements=[AppSetting.key], set_={"value": value}
        )
        async with self._database.sessions() as session, session.begin():
            await session.execute(statement)


def _sum_by_type(rows: Any) -> dict[ItemType, int]:
    totals: dict[ItemType, int] = {}
    for direction, count in rows:
        item_type = CardDirection(direction).item_type
        totals[item_type] = totals.get(item_type, 0) + count
    return totals
```

- [ ] **Step 8: Run the repository tests, lint, commit**

```bash
uv run pytest tests/unit/db -q
uv run ruff format . && uv run ruff check . && uv run mypy
git add src/bunsho/db/engine.py src/bunsho/db/timestamps.py src/bunsho/db/progress_repository.py tests/base.py tests/unit/db/test_engine.py tests/unit/db/test_migrate.py tests/unit/db/test_timestamps.py tests/unit/db/test_progress_repository.py
git commit -m "feat: progress repository with WAL, foreign keys and compare-and-set reviews" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```
Expected: PASS. If mypy rejects the `Any` typed `rows` helper or the `**values` unpacking into `CardState(...)`, keep behaviour and narrow the types (do not remove the tests).

---

## Task 3: Instance lock and startup schema check

**Files:**
- Create: `src/bunsho/db/instance_lock.py`
- Modify: `src/bunsho/api/services.py`
- Test: `tests/unit/db/test_instance_lock.py`, `tests/unit/api/test_app_startup.py` (append)

**Interfaces:**
- Consumes: existing `build_services`, `Services`, `StartupError`, `filelock.FileLock`.
- Produces: `db.instance_lock.InstanceLock(data_dir: Path)` with `.path: Path`, `.acquire() -> None` (raises `InstanceLockedError`), `.release() -> None`; `Services.instance_lock: InstanceLock` (released by `Services.aclose`).

- [ ] **Step 1: Write the failing lock tests**

Create `tests/unit/db/test_instance_lock.py`:

```python
from pathlib import Path

import pytest

from bunsho.db.instance_lock import INSTANCE_LOCK_NAME, InstanceLock, InstanceLockedError


def test_the_lock_file_lives_in_the_data_folder(tmp_path: Path) -> None:
    lock = InstanceLock(tmp_path / "data")
    lock.acquire()
    try:
        assert lock.path == tmp_path / "data" / INSTANCE_LOCK_NAME
        assert lock.path.exists()
    finally:
        lock.release()


def test_a_second_lock_on_the_same_folder_is_refused_until_the_first_is_released(
    tmp_path: Path,
) -> None:
    first = InstanceLock(tmp_path)
    second = InstanceLock(tmp_path)
    first.acquire()
    try:
        with pytest.raises(InstanceLockedError, match="already using"):
            second.acquire()
    finally:
        first.release()
    second.acquire()
    second.release()


def test_release_is_idempotent(tmp_path: Path) -> None:
    lock = InstanceLock(tmp_path)
    lock.acquire()
    lock.release()
    lock.release()


def test_locks_on_different_folders_do_not_conflict(tmp_path: Path) -> None:
    one, two = InstanceLock(tmp_path / "a"), InstanceLock(tmp_path / "b")
    one.acquire()
    two.acquire()
    one.release()
    two.release()
```

Run: `uv run pytest tests/unit/db/test_instance_lock.py -q` → Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 2: Implement `InstanceLock`**

Create `src/bunsho/db/instance_lock.py`:

```python
"""One running instance per data folder."""

from __future__ import annotations

from pathlib import Path

from filelock import FileLock, Timeout

INSTANCE_LOCK_NAME = ".bunsho.instance.lock"


class InstanceLockedError(RuntimeError):
    """Another process already holds the data folder."""


class InstanceLock:
    """An OS-level exclusive lock on the data folder, held for the process lifetime.

    Two instances on one volume would both start; the startup temp-file sweep of one could
    then delete the other's in-flight build file, and both would write ``progress.db``.
    """

    def __init__(self, data_dir: Path) -> None:
        """Create the lock (nothing is acquired yet).

        Args:
            data_dir: The data folder (created on ``acquire`` if missing).
        """
        self._path = data_dir / INSTANCE_LOCK_NAME
        # Process-wide, not per thread: acquire and release may run on different threads.
        self._lock = FileLock(str(self._path), thread_local=False)

    @property
    def path(self) -> Path:
        """The lock file."""
        return self._path

    def acquire(self) -> None:
        """Take the lock without waiting.

        Raises:
            InstanceLockedError: Another process holds it.
            OSError: The lock file cannot be created (for example a read-only folder).
        """
        self._path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._lock.acquire(timeout=0)
        except Timeout as exc:
            raise InstanceLockedError(
                f"Another Bunshō instance is already using the data folder {self._path.parent} "
                f"(lock file {self._path}). Run one instance per data volume: stop the other "
                "instance, or point this one at a different folder."
            ) from exc

    def release(self) -> None:
        """Release the lock; safe to call when it is not held."""
        self._lock.release()
```
Run: `uv run pytest tests/unit/db/test_instance_lock.py -q` → Expected: PASS.

- [ ] **Step 3: Write the failing startup tests**

Append to `tests/unit/api/test_app_startup.py` (add `import logging`; `ContentWriter` import `from bunsho.services.content_repository import ContentWriter`):

```python
def test_a_second_instance_on_the_same_data_folder_is_refused(
    service_config: ServiceConfig,
) -> None:
    async def scenario() -> None:
        first = await build_services(service_config)
        try:
            with pytest.raises(StartupError, match="instance"):
                await build_services(service_config)
        finally:
            await first.aclose()
        second = await build_services(service_config)  # the lock was released by aclose
        await second.aclose()

    asyncio.run(scenario())


def test_a_failed_startup_releases_the_instance_lock(service_config: ServiceConfig) -> None:
    from bunsho.db.instance_lock import InstanceLock

    path = service_config.app.progress_db_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"not a database" * 100)
    with pytest.raises(StartupError):
        asyncio.run(build_services(service_config))
    probe = InstanceLock(service_config.app.data_dir)
    probe.acquire()  # would raise InstanceLockedError if the failed start kept the lock
    probe.release()


def test_an_unusable_data_folder_gives_an_actionable_startup_error(
    service_config: ServiceConfig,
) -> None:
    service_config.app.data_dir.parent.mkdir(parents=True, exist_ok=True)
    service_config.app.data_dir.write_text("a file, not a folder")
    with pytest.raises(StartupError, match="instance lock"):
        asyncio.run(build_services(service_config))


def test_startup_logs_a_content_schema_mismatch_but_still_starts(
    service_config: ServiceConfig, caplog: pytest.LogCaptureFixture
) -> None:
    ContentWriter().write(
        service_config.app.content_db_path,
        kana=[],
        kanji=[],
        vocab=[],
        meta={"schema_version": "1"},
    )

    async def scenario() -> None:
        services = await build_services(service_config)
        await services.aclose()

    with caplog.at_level(logging.ERROR, logger="bunsho"):
        asyncio.run(scenario())
    assert "content_schema_check_failed" in caplog.text
```
Run: `uv run pytest tests/unit/api/test_app_startup.py -q` → Expected: the four new tests FAIL.

- [ ] **Step 4: Wire the lock and the schema check into `build_services`**

In `src/bunsho/api/services.py`:

1. Imports: add `import sqlite3`, `from bunsho.db.instance_lock import InstanceLock, InstanceLockedError`, and change the content repository import to `from bunsho.services.content_repository import ContentSchemaError, remove_stale_temp_files`.
2. Add the field to `Services` (after `health`): `instance_lock: InstanceLock`.
3. Replace `Services.aclose` with:

```python
    async def aclose(self) -> None:
        """Wait briefly for an active build, close the engine, release the instance lock.

        The engine is disposed and the lock released even if waiting for the build fails or
        is cancelled.
        """
        try:
            await self.tasks.aclose()
        finally:
            try:
                await self.progress_db.dispose()
            finally:
                self.instance_lock.release()
```

4. In `build_services`, acquire the lock first and release it on any failure. Replace the body from `logger = ...` to the end with the following (the migration, sweep and service construction code is unchanged apart from the lock, the schema check and the new `instance_lock=` argument):

```python
    logger = logging.getLogger("bunsho")
    app_config = config.app
    backup_dir = app_config.data_dir / "backups"
    lock = InstanceLock(app_config.data_dir)
    try:
        lock.acquire()
    except InstanceLockedError as exc:
        logger.error("instance_lock_held path=%s", lock.path)
        raise StartupError(str(exc)) from exc
    except OSError as exc:
        raise StartupError(
            f"cannot create the instance lock in {app_config.data_dir} "
            f"({type(exc).__name__}: {exc}). Check that the data folder exists and is "
            "writable by the service user."
        ) from exc
    try:
        try:
            await asyncio.to_thread(
                run_migrations, app_config.progress_db_path, backup_dir=backup_dir, logger=logger
            )
        except (DatabaseError, CommandError, OSError) as exc:  # OSError includes filelock.Timeout
            logger.error(
                "progress_db_startup_failed path=%s backups=%s error=%s: %s",
                app_config.progress_db_path,
                backup_dir,
                type(exc).__name__,
                exc,
            )
            raise StartupError(
                f"progress.db could not be opened or migrated ({type(exc).__name__}). "
                f"Database: {app_config.progress_db_path}. Backups: {backup_dir}. "
                "Check that the data folder is writable by the service user and that the file is "
                "a Bunshō progress database. To restore, stop the service and copy a backup over "
                "progress.db."
            ) from exc
        await asyncio.to_thread(remove_stale_temp_files, app_config.content_db_path, logger)
        progress_db = ProgressDatabase(app_config.progress_db_path)
        try:
            await progress_db.ping()
            ctx = await asyncio.to_thread(create_context, app_config, logger=logger)
            await _check_content_schema(ctx, logger)
            factory = (overrides.orchestrator_factory if overrides else None) or (
                create_content_build_orchestrator
            )
            return Services(
                config=config,
                ctx=ctx,
                progress_db=progress_db,
                auth=AuthService(config.auth),
                throttle=LoginThrottle(),
                tasks=BuildTaskManager(ctx, factory),
                health=HealthService(progress_db, ctx),
                instance_lock=lock,
            )
        except BaseException:
            await progress_db.dispose()
            raise
    except BaseException:
        lock.release()
        raise


async def _check_content_schema(ctx: Context, logger: logging.Logger) -> None:
    """Log (at ERROR) when ``content.db`` exists but cannot be used; never blocks startup.

    ``/health`` reports the same problem as ``degraded`` and the review endpoints answer 503
    until the content is rebuilt.
    """
    if ctx.content_repo is None:
        return
    try:
        await asyncio.to_thread(ctx.content_repo.verify_schema)
    except (ContentSchemaError, sqlite3.Error, OSError) as exc:
        logger.error("content_schema_check_failed error=%s: %s", type(exc).__name__, exc)
```

- [ ] **Step 5: Run the tests (and loop the lock tests), lint, commit**

```bash
uv run pytest tests/unit/db/test_instance_lock.py tests/unit/api -q
for i in $(seq 40); do uv run pytest tests/unit/db/test_instance_lock.py tests/unit/api/test_app_startup.py -q -x || break; done
uv run ruff format . && uv run ruff check . && uv run mypy
git add src/bunsho/db/instance_lock.py src/bunsho/api/services.py tests/unit/db/test_instance_lock.py tests/unit/api/test_app_startup.py
git commit -m "feat: one instance per data folder and a startup content schema check" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```
Expected: PASS all 40 loops (lock tests touch real files and OS locks; a flake here is a real bug).

---

## Task 4: Settings, study day and timezone

**Files:**
- Create: `src/bunsho/models/review_settings.py`, `src/bunsho/services/review_settings.py`, `src/bunsho/services/study_day.py`
- Test: `tests/unit/models/test_review_settings.py`, `tests/unit/services/test_review_settings_service.py`, `tests/unit/services/test_study_day.py`

**Interfaces:**
- Consumes: Task 1 (`ItemType`), Task 2 (`ProgressRepository.get_setting/set_setting`, `run_with_database`).
- Produces:
  - `models.review_settings`: `NewCardPolicyName` (`STRICT_ORDER="strict_order"`, `MASTERY_UNLOCK="mastery_unlock"`, `PINNED_LEVELS="pinned_levels"`), `NewLimits(kana=20, kanji=15, vocab=20)` with `.for_type(item_type) -> int`, `ReviewSettings` (fields `new_card_policy`, `new_limits`, `target_retention`, `rollover_hour`, `active_levels: list[Literal["N1".."N5"]]`, `mastery_threshold`) with `.levels() -> frozenset[JlptLevel]`.
  - `services.review_settings`: `SETTINGS_KEY = "review_settings"`, `ReviewSettingsService(progress: ProgressRepository, logger: logging.Logger)` with `async load() -> ReviewSettings`, `async save(settings) -> ReviewSettings`.
  - `services.study_day`: `study_day_window(now: datetime, rollover_hour: int, tz: tzinfo) -> tuple[datetime, datetime]` (UTC instants, start inclusive, end exclusive), `study_date(instant: datetime, rollover_hour: int, tz: tzinfo) -> date`, `resolve_timezone(name: str | None = None, *, logger: logging.Logger | None = None) -> tzinfo`.

- [ ] **Step 1: Write the failing settings-model tests**

Create `tests/unit/models/test_review_settings.py`:

```python
import pytest
from pydantic import ValidationError

from bunsho.models.content import JlptLevel
from bunsho.models.review import ItemType
from bunsho.models.review_settings import NewCardPolicyName, NewLimits, ReviewSettings


def test_defaults_match_the_spec() -> None:
    settings = ReviewSettings()
    assert settings.new_card_policy is NewCardPolicyName.STRICT_ORDER
    assert (settings.new_limits.kana, settings.new_limits.kanji, settings.new_limits.vocab) == (
        20,
        15,
        20,
    )
    assert settings.target_retention == 0.90
    assert settings.rollover_hour == 4
    assert settings.active_levels == ["N5"]
    assert settings.mastery_threshold == 0.80


def test_limits_are_looked_up_by_item_type() -> None:
    limits = NewLimits(kana=1, kanji=2, vocab=3)
    assert [limits.for_type(t) for t in ItemType] == [1, 2, 3]


def test_active_levels_map_to_jlpt_levels() -> None:
    assert ReviewSettings(active_levels=["N5", "N3"]).levels() == {JlptLevel.N5, JlptLevel.N3}


@pytest.mark.parametrize(
    "bad",
    [
        {"target_retention": 0.69},
        {"target_retention": 1.0},
        {"rollover_hour": -1},
        {"rollover_hour": 24},
        {"mastery_threshold": -0.1},
        {"mastery_threshold": 1.1},
        {"new_limits": {"kana": -1}},
        {"active_levels": []},
        {"active_levels": ["N6"]},
        {"new_card_policy": "random"},
        {"unknown_field": 1},
        {"new_limits": {"kana": 1, "extra": 1}},
    ],
)
def test_invalid_settings_are_rejected(bad: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        ReviewSettings.model_validate(bad)


@pytest.mark.parametrize(
    "good",
    [
        {"target_retention": 0.70},
        {"target_retention": 0.99},
        {"rollover_hour": 0},
        {"rollover_hour": 23},
        {"mastery_threshold": 0},
        {"mastery_threshold": 1},
        {"new_limits": {"kana": 0}},
    ],
)
def test_boundary_values_are_accepted(good: dict[str, object]) -> None:
    ReviewSettings.model_validate(good)


def test_settings_round_trip_through_json() -> None:
    settings = ReviewSettings(
        new_card_policy=NewCardPolicyName.PINNED_LEVELS, active_levels=["N4", "N5"]
    )
    assert ReviewSettings.model_validate_json(settings.model_dump_json()) == settings
```

Run: `uv run pytest tests/unit/models/test_review_settings.py -q` → Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 2: Implement the settings model**

Create `src/bunsho/models/review_settings.py`:

```python
"""User-adjustable review settings, validated as one document."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from bunsho.models.content import JlptLevel
from bunsho.models.review import ItemType

LevelLabel = Literal["N1", "N2", "N3", "N4", "N5"]


class NewCardPolicyName(StrEnum):
    """How new cards are chosen each day."""

    STRICT_ORDER = "strict_order"
    MASTERY_UNLOCK = "mastery_unlock"
    PINNED_LEVELS = "pinned_levels"


class NewLimits(BaseModel):
    """Daily new-card limits per item type, counted in cards. ``0`` means unlimited."""

    model_config = ConfigDict(extra="forbid")

    kana: int = Field(default=20, ge=0, le=10_000)
    kanji: int = Field(default=15, ge=0, le=10_000)
    vocab: int = Field(default=20, ge=0, le=10_000)

    def for_type(self, item_type: ItemType) -> int:
        """Return the limit for ``item_type``."""
        match item_type:
            case ItemType.KANA:
                return self.kana
            case ItemType.KANJI:
                return self.kanji
            case ItemType.VOCAB:
                return self.vocab


class ReviewSettings(BaseModel):
    """Every review setting. ``PUT /settings`` replaces the whole document."""

    model_config = ConfigDict(extra="forbid")

    new_card_policy: NewCardPolicyName = NewCardPolicyName.STRICT_ORDER
    new_limits: NewLimits = Field(default_factory=NewLimits)
    target_retention: float = Field(default=0.90, ge=0.70, le=0.99)
    rollover_hour: int = Field(default=4, ge=0, le=23)
    active_levels: list[LevelLabel] = Field(default_factory=lambda: ["N5"], min_length=1)
    mastery_threshold: float = Field(default=0.80, ge=0.0, le=1.0)

    def levels(self) -> frozenset[JlptLevel]:
        """The active levels as ``JlptLevel`` members (used by ``pinned_levels``)."""
        return frozenset(JlptLevel[label] for label in self.active_levels)
```
Run: `uv run pytest tests/unit/models/test_review_settings.py -q` → Expected: PASS.

- [ ] **Step 3: Write the failing service tests and implement the service**

Create `tests/unit/services/test_review_settings_service.py`:

```python
import logging
from pathlib import Path

import pytest

from bunsho.db.engine import ProgressDatabase
from bunsho.db.progress_repository import ProgressRepository
from bunsho.models.review_settings import NewCardPolicyName, ReviewSettings
from bunsho.services.review_settings import SETTINGS_KEY, ReviewSettingsService
from tests.base import run_with_database

LOGGER = logging.getLogger("bunsho.tests.settings")


def test_load_returns_defaults_when_nothing_was_saved(tmp_path: Path) -> None:
    async def scenario(db: ProgressDatabase) -> None:
        service = ReviewSettingsService(ProgressRepository(db), LOGGER)
        assert await service.load() == ReviewSettings()

    run_with_database(tmp_path, scenario)


def test_saved_settings_are_loaded_back(tmp_path: Path) -> None:
    async def scenario(db: ProgressDatabase) -> None:
        service = ReviewSettingsService(ProgressRepository(db), LOGGER)
        chosen = ReviewSettings(
            new_card_policy=NewCardPolicyName.MASTERY_UNLOCK, target_retention=0.85
        )
        assert await service.save(chosen) == chosen
        assert await service.load() == chosen

    run_with_database(tmp_path, scenario)


def test_an_unreadable_stored_document_falls_back_to_defaults_with_a_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    async def scenario(db: ProgressDatabase) -> None:
        repo = ProgressRepository(db)
        await repo.set_setting(SETTINGS_KEY, '{"rollover_hour": 99}')
        service = ReviewSettingsService(repo, LOGGER)
        assert await service.load() == ReviewSettings()

    with caplog.at_level(logging.WARNING, logger=LOGGER.name):
        run_with_database(tmp_path, scenario)
    assert "review_settings_invalid" in caplog.text
```

Create `src/bunsho/services/review_settings.py`:

```python
"""Loading and saving the review settings document."""

from __future__ import annotations

import logging

from pydantic import ValidationError

from bunsho.db.progress_repository import ProgressRepository
from bunsho.models.review_settings import ReviewSettings

SETTINGS_KEY = "review_settings"
"""The ``app_setting`` row that holds the whole settings document as JSON."""


class ReviewSettingsService:
    """Stores the review settings as one JSON document, so a save is atomic."""

    def __init__(self, progress: ProgressRepository, logger: logging.Logger) -> None:
        """Create the service.

        Args:
            progress: Repository for ``app_setting`` rows.
            logger: Logger for key=value messages.
        """
        self._progress = progress
        self._logger = logger

    async def load(self) -> ReviewSettings:
        """Return the saved settings, or the defaults if none are saved or the row is invalid.

        An invalid stored document (for example written by a newer version) is logged at
        WARNING and ignored rather than blocking every review.
        """
        raw = await self._progress.get_setting(SETTINGS_KEY)
        if raw is None:
            return ReviewSettings()
        try:
            return ReviewSettings.model_validate_json(raw)
        except ValidationError as exc:
            self._logger.warning(
                "review_settings_invalid using=defaults errors=%d", exc.error_count()
            )
            return ReviewSettings()

    async def save(self, settings: ReviewSettings) -> ReviewSettings:
        """Store ``settings`` (a full replacement) and return them."""
        await self._progress.set_setting(SETTINGS_KEY, settings.model_dump_json())
        return settings
```
Run: `uv run pytest tests/unit/services/test_review_settings_service.py -q` → Expected: PASS.

- [ ] **Step 4: Write the failing study-day tests**

Create `tests/unit/services/test_study_day.py`:

```python
import logging
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from bunsho.services.study_day import resolve_timezone, study_date, study_day_window

NEW_YORK = ZoneInfo("America/New_York")


def utc(*args: int) -> datetime:
    return datetime(*args, tzinfo=UTC)


def test_the_window_starts_at_the_rollover_hour_of_the_current_day() -> None:
    start, end = study_day_window(utc(2026, 9, 20, 12), 4, UTC)
    assert (start, end) == (utc(2026, 9, 20, 4), utc(2026, 9, 21, 4))


def test_before_the_rollover_hour_belongs_to_the_previous_day() -> None:
    start, end = study_day_window(utc(2026, 9, 20, 3, 59), 4, UTC)
    assert (start, end) == (utc(2026, 9, 19, 4), utc(2026, 9, 20, 4))


def test_the_boundary_instant_starts_the_new_day() -> None:
    start, _ = study_day_window(utc(2026, 9, 20, 4), 4, UTC)
    assert start == utc(2026, 9, 20, 4)


def test_the_window_follows_the_timezone() -> None:
    # 12:00 UTC on 20 Sep is 08:00 in New York (EDT, UTC-4): the day began at 04:00 EDT.
    start, end = study_day_window(utc(2026, 9, 20, 12), 4, NEW_YORK)
    assert (start, end) == (utc(2026, 9, 20, 8), utc(2026, 9, 21, 8))


def test_the_spring_forward_day_is_23_hours_long() -> None:
    # New York clocks jump forward at 02:00 EST (07:00 UTC) on 2026-03-08. 07:30 UTC is
    # 03:30 EDT, still before that day's 04:00 rollover, so it belongs to the 7th.
    start, end = study_day_window(utc(2026, 3, 8, 7, 30), 4, NEW_YORK)
    assert (start, end) == (utc(2026, 3, 7, 9), utc(2026, 3, 8, 8))  # 04:00 EST to 04:00 EDT
    assert end - start == timedelta(hours=23)


def test_the_fall_back_day_is_25_hours_long() -> None:
    # Clocks go back at 02:00 EDT on 2026-11-01. The day that starts at 04:00 EDT on 31 Oct
    # ends at 04:00 EST on 1 Nov, one hour later than 24 hours.
    start, end = study_day_window(utc(2026, 10, 31, 20), 4, NEW_YORK)
    assert (start, end) == (utc(2026, 10, 31, 8), utc(2026, 11, 1, 9))
    assert end - start == timedelta(hours=25)


def test_consecutive_windows_tile_without_gaps() -> None:
    moment = utc(2026, 3, 6, 12)
    windows = []
    for _ in range(5):
        start, end = study_day_window(moment, 4, NEW_YORK)
        windows.append((start, end))
        moment = end
    for (_, previous_end), (next_start, _) in zip(windows, windows[1:], strict=False):
        assert previous_end == next_start


def test_study_date_uses_the_rollover_hour() -> None:
    assert study_date(utc(2026, 9, 20, 3, 59), 4, UTC) == date(2026, 9, 19)
    assert study_date(utc(2026, 9, 20, 4, 0), 4, UTC) == date(2026, 9, 20)
    assert study_date(utc(2026, 9, 20, 12), 4, NEW_YORK) == date(2026, 9, 20)


def test_a_naive_instant_is_rejected() -> None:
    with pytest.raises(ValueError, match="timezone"):
        study_day_window(datetime(2026, 9, 20, 12), 4, UTC)


def test_resolve_timezone_uses_an_explicit_name() -> None:
    assert resolve_timezone("America/New_York") == NEW_YORK


def test_resolve_timezone_reads_the_tz_variable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TZ", "Asia/Tokyo")
    assert resolve_timezone() == ZoneInfo("Asia/Tokyo")


def test_resolve_timezone_falls_back_to_utc_with_a_warning(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.delenv("TZ", raising=False)
    logger = logging.getLogger("bunsho.tests.tz")
    with caplog.at_level(logging.WARNING, logger=logger.name):
        assert resolve_timezone(logger=logger) == UTC
        assert resolve_timezone("Not/AZone", logger=logger) == UTC
    assert "study_timezone_not_set" in caplog.text
    assert "study_timezone_unknown" in caplog.text
```

Run: `uv run pytest tests/unit/services/test_study_day.py -q` → Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 5: Implement the study-day helpers**

Create `src/bunsho/services/study_day.py`:

```python
"""The "study day": daily limits reset at a rollover hour in the server's timezone."""

from __future__ import annotations

import logging
import os
from datetime import UTC, date, datetime, timedelta, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def study_day_window(now: datetime, rollover_hour: int, tz: tzinfo) -> tuple[datetime, datetime]:
    """Return the study day containing ``now`` as UTC instants ``[start, end)``.

    A study day starts at ``rollover_hour`` o'clock wall time in ``tz`` and ends at the
    next such moment, so it is 23 or 25 hours long across a DST change.

    Args:
        now: A timezone-aware instant.
        rollover_hour: Hour of the day (0-23) at which a new study day begins.
        tz: The timezone in which the rollover hour is read.

    Returns:
        The window start (inclusive) and end (exclusive), both in UTC.

    Raises:
        ValueError: ``now`` is naive.
    """
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware (a naive datetime has no timezone)")
    local = now.astimezone(tz)
    start = local.replace(hour=rollover_hour, minute=0, second=0, microsecond=0)
    if local < start:
        start -= timedelta(days=1)
    end = start + timedelta(days=1)  # wall-clock arithmetic: keeps the rollover hour across DST
    return start.astimezone(UTC), end.astimezone(UTC)


def study_date(instant: datetime, rollover_hour: int, tz: tzinfo) -> date:
    """Return the calendar date of the study day containing ``instant``."""
    start, _ = study_day_window(instant, rollover_hour, tz)
    return start.astimezone(tz).date()


def resolve_timezone(name: str | None = None, *, logger: logging.Logger | None = None) -> tzinfo:
    """Return the timezone for study days.

    Args:
        name: An IANA name such as ``America/New_York``. ``None`` reads the ``TZ``
            environment variable.
        logger: Logger for the fallback warnings.

    Returns:
        The named zone, or UTC (with a WARNING) when none is set or the name is unknown.
    """
    log = logger or logging.getLogger(__name__)
    chosen = os.environ.get("TZ", "") if name is None else name
    if not chosen:
        log.warning("study_timezone_not_set using=UTC hint='set TZ, e.g. TZ=America/New_York'")
        return UTC
    try:
        return ZoneInfo(chosen)
    except (ZoneInfoNotFoundError, ValueError):
        log.warning("study_timezone_unknown name=%s using=UTC", chosen)
        return UTC
```
Run: `uv run pytest tests/unit/services/test_study_day.py -q` → Expected: PASS. (The DST expectations were derived by hand: EST is UTC-5, EDT is UTC-4, and the rollover is read as wall-clock time, so the spring-forward day is 23 hours and the fall-back day 25.)

- [ ] **Step 6: Lint and commit**

```bash
uv run pytest tests/unit/models tests/unit/services -q
uv run ruff format . && uv run ruff check . && uv run mypy
git add src/bunsho/models/review_settings.py src/bunsho/services/review_settings.py src/bunsho/services/study_day.py tests/unit/models/test_review_settings.py tests/unit/services/test_review_settings_service.py tests/unit/services/test_study_day.py
git commit -m "feat: review settings document, study-day window and timezone resolution" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```
Expected: PASS.

## Task 5: Content catalogue and the three new-card policies

**Files:**
- Modify: `src/bunsho/services/content_repository.py`, `src/bunsho/services/protocols.py`, `src/bunsho/factories.py`, `tests/base.py`
- Create: `src/bunsho/services/content_catalog.py`, `src/bunsho/services/new_card_policies.py`
- Test: `tests/unit/services/test_content_repository_catalog.py`, `tests/unit/services/test_content_catalog.py`, `tests/unit/services/test_new_card_policies.py`, `tests/unit/test_review_factories.py` (append)

**Interfaces:**
- Consumes: Task 1 (`ItemType`, `CardKey`, `CatalogEntry`, `SchedState`, `DIRECTIONS_BY_TYPE`), Task 4 (`ReviewSettings`, `NewCardPolicyName`).
- Produces:
  - `ContentRepository.catalog(item_type: ItemType) -> list[tuple[str, JlptLevel | None]]` (ids and levels in study order; kanji excludes unleveled), `ContentRepository.get_kana(item_id: str) -> Kana | None`.
  - `ContentCatalog(repository: ContentRepository).entries(item_type: ItemType) -> list[CatalogEntry]` (synchronous; callers use `asyncio.to_thread`).
  - `services.protocols.NewCardPolicy.select(item_type, catalog: Sequence[CatalogEntry], states: Mapping[CardKey, SchedState], limit: int | None) -> list[CardKey]` (`None` = no limit; candidates are ordered level N5 first, then stable `position`, then direction order; cards already in `states` are skipped).
  - `StrictOrderPolicy()`, `MasteryUnlockPolicy(threshold: float)`, `PinnedLevelsPolicy(levels: Iterable[JlptLevel])`.
  - `factories.create_new_card_policy(settings: ReviewSettings) -> NewCardPolicy` (`ValueError` for an unknown name), `factories.create_scheduler_from_settings(settings: ReviewSettings) -> Scheduler`.
  - `tests.base`: `make_kana(char, romaji, script)`, `make_kanji(char, level)`, `write_content(path, *, kana, kanji, vocab, schema_version) -> ContentRepository`.

- [ ] **Step 1: Add the shared content test builders**

In `tests/base.py` extend the content imports and add the builders (add each import together with its first use):

```python
from bunsho.models.content import (
    JlptLevel,
    Kana,
    KanaKind,
    KanaScript,
    Kanji,
    KanjiDetails,
    RubySegment,
    Sentence,
    Vocab,
    kana_id,
    kanji_id,
    vocab_id,
)
from bunsho.services.content_repository import (
    CONTENT_SCHEMA_VERSION,
    ContentRepository,
    ContentWriter,
)
```

```python
def make_kana(
    char: str = "あ", romaji: str = "a", script: KanaScript = KanaScript.HIRAGANA
) -> Kana:
    """Build a ``Kana`` with sensible defaults for tests."""
    return Kana(
        id=kana_id(script, char),
        script=script,
        char=char,
        romaji=romaji,
        kind=KanaKind.BASIC,
        group="a",
    )


def make_kanji(char: str = "日", level: JlptLevel | None = JlptLevel.N5) -> Kanji:
    """Build a ``Kanji`` (``level=None`` makes it an unleveled one)."""
    return Kanji(
        id=kanji_id(char),
        char=char,
        level=level,
        meanings=("day",),
        on_readings=("ニチ",),
        kun_readings=("ひ",),
        stroke_count=4,
        grade=1,
        frequency=1,
        radical=72,
    )


def write_content(
    path: Path,
    *,
    kana: Iterable[Kana] = (),
    kanji: Iterable[Kanji] = (),
    vocab: Iterable[Vocab] = (),
    schema_version: str = CONTENT_SCHEMA_VERSION,
) -> ContentRepository:
    """Write a small ``content.db`` at ``path`` and open it."""
    ContentWriter().write(
        path,
        kana=list(kana),
        kanji=list(kanji),
        vocab=list(vocab),
        meta={"schema_version": schema_version},
    )
    return ContentRepository(path)
```
(`Iterable` comes from `collections.abc`; merge with the existing `Awaitable, Callable` import added in Task 2. Remove the now-duplicate names from the old imports, keeping the file's import block sorted.)
Re-read the file afterwards: the Japanese literals must be intact.

- [ ] **Step 2: Write the failing repository tests**

Create `tests/unit/services/test_content_repository_catalog.py`:

```python
from pathlib import Path

from bunsho.models.content import JlptLevel
from bunsho.models.review import ItemType
from bunsho.services.content_repository import ContentRepository
from tests.base import make_kana, make_kanji, make_vocab, write_content


def _repo(tmp_path: Path) -> ContentRepository:
    return write_content(
        tmp_path / "content.db",
        kana=[make_kana("あ", "a"), make_kana("い", "i")],
        kanji=[make_kanji("日", JlptLevel.N5), make_kanji("犬", None), make_kanji("曜", JlptLevel.N4)],
        vocab=[
            make_vocab("日本", "にほん", JlptLevel.N5),
            make_vocab("学生", "がくせい", JlptLevel.N4),
            make_vocab("先生", "せんせい", JlptLevel.N5),
        ],
    )


def test_catalog_lists_kana_without_levels(tmp_path: Path) -> None:
    assert _repo(tmp_path).catalog(ItemType.KANA) == [("kana:hira:あ", None), ("kana:hira:い", None)]


def test_catalog_lists_vocab_in_deck_order_with_levels(tmp_path: Path) -> None:
    assert _repo(tmp_path).catalog(ItemType.VOCAB) == [
        ("vocab:日本:にほん", JlptLevel.N5),
        ("vocab:学生:がくせい", JlptLevel.N4),
        ("vocab:先生:せんせい", JlptLevel.N5),
    ]


def test_catalog_excludes_unleveled_kanji(tmp_path: Path) -> None:
    assert _repo(tmp_path).catalog(ItemType.KANJI) == [
        ("kanji:日", JlptLevel.N5),
        ("kanji:曜", JlptLevel.N4),
    ]


def test_catalog_agrees_with_an_unfiltered_list_vocab(tmp_path: Path) -> None:
    """Content ids are opaque: consumers must take them from the repository, in this order."""
    repo = _repo(tmp_path)
    assert repo.catalog(ItemType.VOCAB) == [(v.id, v.level) for v in repo.list_vocab()]


def test_get_kana_finds_a_kana_by_id(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    found = repo.get_kana("kana:hira:あ")
    assert found is not None
    assert found.char == "あ"
    assert repo.get_kana("kana:hira:missing") is None
```

Run: `uv run pytest tests/unit/services/test_content_repository_catalog.py -q` → Expected: FAIL (`AttributeError: ... 'catalog'`).

- [ ] **Step 3: Add `catalog` and `get_kana` to `ContentRepository`**

In `src/bunsho/services/content_repository.py` add `from bunsho.models.review import ItemType` to the imports and these methods to `ContentRepository` (after `get_vocab`):

```python
    def get_kana(self, item_id: str) -> Kana | None:
        """Return the kana with this stable ID, if any."""
        with self._connect() as con:
            row = con.execute("SELECT data FROM kana WHERE id = ?", (item_id,)).fetchone()
        return Kana.model_validate_json(row[0]) if row else None

    def catalog(self, item_type: ItemType) -> list[tuple[str, JlptLevel | None]]:
        """List item ids and levels in study order without parsing the item payloads.

        Kanji without a level (not used by the deck) are excluded: they are not offered as
        lessons. Kana have no level. Ids are opaque; use them only as given.

        Args:
            item_type: Which content table to list.

        Returns:
            ``(item_id, level)`` pairs in ``content.db`` order.
        """
        with self._connect() as con:
            match item_type:
                case ItemType.KANA:
                    rows = con.execute("SELECT id, NULL FROM kana ORDER BY rowid").fetchall()
                case ItemType.KANJI:
                    rows = con.execute(
                        "SELECT id, level FROM kanji WHERE level IS NOT NULL ORDER BY rowid"
                    ).fetchall()
                case ItemType.VOCAB:
                    rows = con.execute("SELECT id, level FROM vocab ORDER BY rowid").fetchall()
        return [(row[0], None if row[1] is None else JlptLevel(row[1])) for row in rows]
```
Run: `uv run pytest tests/unit/services/test_content_repository_catalog.py tests/unit/services/test_content_repository.py -q` → Expected: PASS.

- [ ] **Step 4: Write and implement `ContentCatalog`**

Create `tests/unit/services/test_content_catalog.py`:

```python
from pathlib import Path

from bunsho.models.content import JlptLevel
from bunsho.models.review import CatalogEntry, ItemType
from bunsho.services.content_catalog import ContentCatalog
from tests.base import make_kana, make_kanji, make_vocab, write_content


def test_entries_carry_type_level_and_position(tmp_path: Path) -> None:
    repo = write_content(
        tmp_path / "content.db",
        kana=[make_kana("あ", "a")],
        kanji=[make_kanji("日", JlptLevel.N5), make_kanji("犬", None)],
        vocab=[make_vocab("日本", "にほん", JlptLevel.N5), make_vocab("学生", "がくせい", JlptLevel.N4)],
    )
    catalog = ContentCatalog(repo)
    assert catalog.entries(ItemType.VOCAB) == [
        CatalogEntry("vocab:日本:にほん", ItemType.VOCAB, JlptLevel.N5, 0),
        CatalogEntry("vocab:学生:がくせい", ItemType.VOCAB, JlptLevel.N4, 1),
    ]
    assert catalog.entries(ItemType.KANA) == [
        CatalogEntry("kana:hira:あ", ItemType.KANA, None, 0)
    ]
    assert [e.item_id for e in catalog.entries(ItemType.KANJI)] == ["kanji:日"]  # 犬 is unleveled
```

Create `src/bunsho/services/content_catalog.py`:

```python
"""The ordered, level-tagged list of items new cards are chosen from."""

from __future__ import annotations

from bunsho.models.review import CatalogEntry, ItemType
from bunsho.services.content_repository import ContentRepository


class ContentCatalog:
    """Builds ``CatalogEntry`` lists from ``content.db``.

    This is the one place that decides which items are lesson material: unleveled kanji are
    left out (``ContentRepository.catalog`` filters them).
    """

    def __init__(self, repository: ContentRepository) -> None:
        """Create the catalogue.

        Args:
            repository: The content repository to read.
        """
        self._repository = repository

    def entries(self, item_type: ItemType) -> list[CatalogEntry]:
        """Return the entries for ``item_type`` in stable study order.

        Blocking (SQLite); call it through ``asyncio.to_thread`` from async code.
        """
        return [
            CatalogEntry(item_id=item_id, item_type=item_type, level=level, position=position)
            for position, (item_id, level) in enumerate(self._repository.catalog(item_type))
        ]
```
Run: `uv run pytest tests/unit/services/test_content_catalog.py -q` → Expected: PASS.

- [ ] **Step 5: Write the failing policy tests**

Create `tests/unit/services/test_new_card_policies.py`:

```python
import pytest

from bunsho.models.content import JlptLevel
from bunsho.models.review import CardDirection, CardKey, CatalogEntry, ItemType, SchedState
from bunsho.services.new_card_policies import (
    MasteryUnlockPolicy,
    PinnedLevelsPolicy,
    StrictOrderPolicy,
)

VOCAB = ItemType.VOCAB
REC, RECALL = CardDirection.RECOGNITION, CardDirection.RECALL
N4, N5 = JlptLevel.N4, JlptLevel.N5


def entries(item_type: ItemType, spec: list[tuple[str, JlptLevel | None]]) -> list[CatalogEntry]:
    return [CatalogEntry(item_id, item_type, level, i) for i, (item_id, level) in enumerate(spec)]


# Deck order is mixed on purpose: the policies must order by level, then by position.
DECK = entries(VOCAB, [("a", N4), ("b", N5), ("c", N5), ("d", N4)])


def test_strict_order_offers_n5_before_n4_in_stable_order() -> None:
    chosen = StrictOrderPolicy().select(VOCAB, DECK, {}, 5)
    assert chosen == [
        CardKey("b", REC),
        CardKey("b", RECALL),
        CardKey("c", REC),
        CardKey("c", RECALL),
        CardKey("a", REC),
    ]


def test_strict_order_skips_cards_already_introduced() -> None:
    states = {CardKey("b", REC): SchedState.LEARNING}
    assert StrictOrderPolicy().select(VOCAB, DECK, states, 2) == [
        CardKey("b", RECALL),
        CardKey("c", REC),
    ]


def test_a_limit_of_none_means_everything_and_zero_means_nothing() -> None:
    assert len(StrictOrderPolicy().select(VOCAB, DECK, {}, None)) == 8
    assert StrictOrderPolicy().select(VOCAB, DECK, {}, 0) == []


def test_a_negative_limit_offers_nothing() -> None:
    assert StrictOrderPolicy().select(VOCAB, DECK, {}, -3) == []


LEVELS = entries(VOCAB, [("a", N5), ("b", N5), ("c", N4)])  # 4 N5 cards, 2 N4 cards
ALL_N5_LEARNED = {CardKey(i, d): SchedState.REVIEW for i in ("a", "b") for d in (REC, RECALL)}
N4_CARDS = [CardKey("c", REC), CardKey("c", RECALL)]


def test_mastery_unlocks_the_next_level_when_the_threshold_is_met() -> None:
    assert MasteryUnlockPolicy(0.8).select(VOCAB, LEVELS, ALL_N5_LEARNED, None) == N4_CARDS


def test_mastery_holds_the_next_level_back_below_the_threshold() -> None:
    states = {**ALL_N5_LEARNED, CardKey("b", RECALL): SchedState.LEARNING}  # 3 of 4 = 0.75
    assert MasteryUnlockPolicy(0.8).select(VOCAB, LEVELS, states, None) == []
    assert MasteryUnlockPolicy(0.75).select(VOCAB, LEVELS, states, None) == N4_CARDS


def test_mastery_still_offers_unintroduced_cards_of_an_unlocked_level() -> None:
    assert MasteryUnlockPolicy(0.8).select(VOCAB, LEVELS, {}, None) == [
        CardKey("a", REC),
        CardKey("a", RECALL),
        CardKey("b", REC),
        CardKey("b", RECALL),
    ]


def test_an_empty_level_does_not_block_the_next_one() -> None:
    only_n4 = entries(VOCAB, [("c", N4)])
    assert MasteryUnlockPolicy(0.9).select(VOCAB, only_n4, {}, None) == N4_CARDS


def test_pinned_levels_only_offers_the_chosen_levels() -> None:
    chosen = PinnedLevelsPolicy({N4}).select(VOCAB, DECK, {}, None)
    assert [key.item_id for key in chosen] == ["a", "a", "d", "d"]


def test_kanji_items_have_three_directions() -> None:
    kanji = entries(ItemType.KANJI, [("kanji:日", N5)])
    assert [k.direction for k in StrictOrderPolicy().select(ItemType.KANJI, kanji, {}, None)] == [
        CardDirection.KANJI_TO_MEANING,
        CardDirection.KANJI_TO_READING,
        CardDirection.MEANING_TO_KANJI,
    ]


@pytest.mark.parametrize(
    "policy",
    [StrictOrderPolicy(), MasteryUnlockPolicy(1.0), PinnedLevelsPolicy({JlptLevel.N1})],
)
def test_kana_is_never_level_gated(
    policy: StrictOrderPolicy | MasteryUnlockPolicy | PinnedLevelsPolicy,
) -> None:
    kana = entries(ItemType.KANA, [("k1", None), ("k2", None)])
    assert policy.select(ItemType.KANA, kana, {}, None) == [
        CardKey("k1", CardDirection.GLYPH_TO_SOUND),
        CardKey("k1", CardDirection.SOUND_TO_GLYPH),
        CardKey("k2", CardDirection.GLYPH_TO_SOUND),
        CardKey("k2", CardDirection.SOUND_TO_GLYPH),
    ]
```

Run: `uv run pytest tests/unit/services/test_new_card_policies.py -q` → Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 6: Add the `NewCardPolicy` protocol and implement the policies**

In `src/bunsho/services/protocols.py` extend the review import to `from bunsho.models.review import CardKey, CardSchedule, CatalogEntry, Grade, ItemType, SchedState` and append:

```python
class NewCardPolicy(Protocol):
    """Chooses which never-seen cards of one item type to introduce next."""

    def select(
        self,
        item_type: ItemType,
        catalog: Sequence[CatalogEntry],
        states: Mapping[CardKey, SchedState],
        limit: int | None,
    ) -> list[CardKey]:
        """Return up to ``limit`` unintroduced cards, in the order they should appear.

        Args:
            item_type: The item type the catalogue belongs to.
            catalog: The type's entries (any order; the policy sorts them).
            states: State of every card that has been reviewed (its keys are "introduced").
            limit: Maximum number of cards, or ``None`` for no limit.
        """
        ...
```

Create `src/bunsho/services/new_card_policies.py`:

```python
"""The three ways of choosing which new cards to introduce.

All three order candidates the same way (JLPT level N5 first, then ``content.db`` position,
then direction order) and skip cards that already have a ``card_state`` row. They differ only
in which levels they offer. Kana has no level and is never gated. Because candidates are
ordered by level, a later level is only reached once the earlier ones are used up.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from itertools import islice

from bunsho.models.content import JlptLevel
from bunsho.models.review import (
    DIRECTIONS_BY_TYPE,
    CardKey,
    CatalogEntry,
    ItemType,
    SchedState,
)

_STUDY_ORDER = JlptLevel.study_order()


def _rank(level: JlptLevel | None) -> int:
    return -1 if level is None else _STUDY_ORDER.index(level)


def _candidates(
    item_type: ItemType,
    catalog: Sequence[CatalogEntry],
    states: Mapping[CardKey, SchedState],
    allowed: Callable[[CatalogEntry], bool],
) -> Iterator[CardKey]:
    directions = DIRECTIONS_BY_TYPE[item_type]
    for entry in sorted(catalog, key=lambda e: (_rank(e.level), e.position)):
        if not allowed(entry):
            continue
        for direction in directions:
            key = CardKey(entry.item_id, direction)
            if key not in states:
                yield key


def _take(candidates: Iterator[CardKey], limit: int | None) -> list[CardKey]:
    return list(candidates) if limit is None else list(islice(candidates, max(limit, 0)))


class StrictOrderPolicy:
    """N5 first, then N4 and so on; a level starts once the earlier ones are all introduced."""

    def select(
        self,
        item_type: ItemType,
        catalog: Sequence[CatalogEntry],
        states: Mapping[CardKey, SchedState],
        limit: int | None,
    ) -> list[CardKey]:
        """Return the next unintroduced cards in strict level order."""
        return _take(_candidates(item_type, catalog, states, lambda _entry: True), limit)


class MasteryUnlockPolicy:
    """Strict order, but a level also waits for the previous one to be mostly learned.

    Level N+1 is offered only when at least ``threshold`` of **all** cards at level N are in
    the FSRS Review state. Measuring against all cards (not just introduced ones) stops a
    handful of easy early cards from unlocking the next level.
    """

    def __init__(self, threshold: float) -> None:
        """Create the policy.

        Args:
            threshold: Share (0-1) of a level's cards that must be in Review to unlock the next.
        """
        self._threshold = threshold

    def select(
        self,
        item_type: ItemType,
        catalog: Sequence[CatalogEntry],
        states: Mapping[CardKey, SchedState],
        limit: int | None,
    ) -> list[CardKey]:
        """Return the next unintroduced cards from the levels that are unlocked."""
        unlocked = self._unlocked_levels(item_type, catalog, states)
        return _take(
            _candidates(
                item_type,
                catalog,
                states,
                lambda entry: entry.level is None or entry.level in unlocked,
            ),
            limit,
        )

    def _unlocked_levels(
        self,
        item_type: ItemType,
        catalog: Sequence[CatalogEntry],
        states: Mapping[CardKey, SchedState],
    ) -> set[JlptLevel]:
        directions = DIRECTIONS_BY_TYPE[item_type]
        total: Counter[JlptLevel] = Counter()
        mastered: Counter[JlptLevel] = Counter()
        for entry in catalog:
            if entry.level is None:
                continue
            for direction in directions:
                total[entry.level] += 1
                if states.get(CardKey(entry.item_id, direction)) is SchedState.REVIEW:
                    mastered[entry.level] += 1
        unlocked: set[JlptLevel] = set()
        for level in _STUDY_ORDER:
            unlocked.add(level)
            if total[level] and mastered[level] / total[level] < self._threshold:
                break
        return unlocked


class PinnedLevelsPolicy:
    """Only the levels chosen in the settings, in order."""

    def __init__(self, levels: Iterable[JlptLevel]) -> None:
        """Create the policy.

        Args:
            levels: The levels new cards may come from.
        """
        self._levels = frozenset(levels)

    def select(
        self,
        item_type: ItemType,
        catalog: Sequence[CatalogEntry],
        states: Mapping[CardKey, SchedState],
        limit: int | None,
    ) -> list[CardKey]:
        """Return the next unintroduced cards from the pinned levels."""
        return _take(
            _candidates(
                item_type,
                catalog,
                states,
                lambda entry: entry.level is None or entry.level in self._levels,
            ),
            limit,
        )
```
Run: `uv run pytest tests/unit/services/test_new_card_policies.py -q` → Expected: PASS.

- [ ] **Step 7: Add the factories with tests**

Append to `tests/unit/test_review_factories.py` (add the new imports at the top of the file, sorted):

```python
from bunsho.factories import create_new_card_policy, create_scheduler_from_settings
from bunsho.models.content import JlptLevel
from bunsho.models.review import CardDirection, CardKey, CatalogEntry, ItemType
from bunsho.models.review_settings import NewCardPolicyName, ReviewSettings
from bunsho.services.new_card_policies import (
    MasteryUnlockPolicy,
    PinnedLevelsPolicy,
    StrictOrderPolicy,
)


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        (NewCardPolicyName.STRICT_ORDER, StrictOrderPolicy),
        (NewCardPolicyName.MASTERY_UNLOCK, MasteryUnlockPolicy),
        (NewCardPolicyName.PINNED_LEVELS, PinnedLevelsPolicy),
    ],
)
def test_create_new_card_policy_picks_the_policy_by_name(
    name: NewCardPolicyName, expected: type
) -> None:
    assert isinstance(create_new_card_policy(ReviewSettings(new_card_policy=name)), expected)


def test_the_pinned_policy_uses_the_active_levels_setting() -> None:
    settings = ReviewSettings(
        new_card_policy=NewCardPolicyName.PINNED_LEVELS, active_levels=["N4"]
    )
    catalog = [
        CatalogEntry("n5-word", ItemType.VOCAB, JlptLevel.N5, 0),
        CatalogEntry("n4-word", ItemType.VOCAB, JlptLevel.N4, 1),
    ]
    chosen = create_new_card_policy(settings).select(ItemType.VOCAB, catalog, {}, None)
    assert chosen == [
        CardKey("n4-word", CardDirection.RECOGNITION),
        CardKey("n4-word", CardDirection.RECALL),
    ]


def test_an_unknown_policy_name_is_rejected() -> None:
    settings = ReviewSettings.model_construct(new_card_policy="bogus")
    with pytest.raises(ValueError, match="bogus"):
        create_new_card_policy(settings)


def test_the_scheduler_follows_the_target_retention_setting() -> None:
    now = datetime(2026, 9, 20, 12, tzinfo=UTC)
    high = create_scheduler_from_settings(ReviewSettings(target_retention=0.97))
    low = create_scheduler_from_settings(ReviewSettings(target_retention=0.80))
    assert isinstance(high, FSRSScheduler)
    base = create_scheduler("fsrs", enable_fuzzing=False)
    review = base.schedule(base.initial(now), Grade.EASY, now)
    high_due = high.preview(review, review.due)[Grade.GOOD].due
    low_due = low.preview(review, review.due)[Grade.GOOD].due
    assert high_due < low_due
```

In `src/bunsho/factories.py` add imports `from bunsho.models.review_settings import NewCardPolicyName, ReviewSettings`, `from bunsho.services.new_card_policies import MasteryUnlockPolicy, PinnedLevelsPolicy, StrictOrderPolicy`, extend the protocols import with `NewCardPolicy`, and append:

```python
def create_new_card_policy(settings: ReviewSettings) -> NewCardPolicy:
    """Build the new-card policy named by ``settings.new_card_policy``.

    Args:
        settings: The review settings (policy name, mastery threshold, active levels).

    Returns:
        The policy.

    Raises:
        ValueError: The policy name is not supported.
    """
    match settings.new_card_policy:
        case NewCardPolicyName.STRICT_ORDER:
            return StrictOrderPolicy()
        case NewCardPolicyName.MASTERY_UNLOCK:
            return MasteryUnlockPolicy(settings.mastery_threshold)
        case NewCardPolicyName.PINNED_LEVELS:
            return PinnedLevelsPolicy(settings.levels())
        case _:
            raise ValueError(f"unsupported new-card policy {settings.new_card_policy!r}")


def create_scheduler_from_settings(settings: ReviewSettings) -> Scheduler:
    """Build the scheduler configured by ``settings.target_retention`` (fuzzing on)."""
    return create_scheduler("fsrs", desired_retention=settings.target_retention)
```

- [ ] **Step 8: Run, lint, commit**

```bash
uv run pytest tests/unit -q
uv run ruff format . && uv run ruff check . && uv run mypy
git add src/bunsho/services/content_repository.py src/bunsho/services/protocols.py src/bunsho/services/content_catalog.py src/bunsho/services/new_card_policies.py src/bunsho/factories.py tests/base.py tests/unit/services/test_content_repository_catalog.py tests/unit/services/test_content_catalog.py tests/unit/services/test_new_card_policies.py tests/unit/test_review_factories.py
git commit -m "feat: content catalogue and switchable new-card policies" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```
Expected: PASS.

---

## Task 6: Review session orchestrator and statistics

**Files:**
- Create: `src/bunsho/models/review_session.py`, `src/bunsho/services/content_access.py`, `src/bunsho/orchestration/review_session.py`, `src/bunsho/services/review_stats.py`, `tests/review_stack.py`
- Test: `tests/unit/services/test_content_access.py`, `tests/unit/models/test_review_session.py`, `tests/unit/orchestration/test_review_session.py`, `tests/unit/services/test_review_stats.py`

**Interfaces:**
- Consumes: Tasks 1-5 (everything above).
- Produces:
  - `models.review_session`: `TypeCounts(kana=0, kanji=0, vocab=0)` with `from_mapping(Mapping[ItemType, int])`; `GradeIntervals(again, hard, good, easy)` (seconds until due); `CardView(item_id, direction, item_type, is_new, state, expected_last_review, intervals, kana=None, kanji=None, vocab=None)`; `ReviewCounts(due: TypeCounts, new_remaining: TypeCounts)`; `NextCard(card: CardView | None, next_due_at: AwareDatetime | None, counts: ReviewCounts)`; `TypeProgress(total, learning, review, relearning)`; `LevelProgress(item_type, level: str, total, introduced, review)`; `DayCount(day: date, reviews: int)`; `StatsSummary(reviewed_today, introduced_today: TypeCounts, daily_reviews: list[DayCount], retention_30d: float | None, by_type: dict[ItemType, TypeProgress], by_level: list[LevelProgress])`.
  - `services.content_access.ContentGate(ctx: Context)` with `async repository() -> ContentRepository` (raises `ContentNotReadyError`).
  - `orchestration.review_session.ReviewSessionOrchestrator(*, gate, progress, settings, scheduler_factory: Callable[[ReviewSettings], Scheduler], policy_factory: Callable[[ReviewSettings], NewCardPolicy], tz: tzinfo, logger, clock: Callable[[], datetime] | None = None)` with `async next_card(now=None) -> NextCard` and `async answer(key: CardKey, grade: Grade, *, expected_last_review: datetime | None, duration_ms: int | None = None, now=None) -> ReviewCounts` (raises `ContentNotReadyError`, `UnknownItemError`, `StaleReviewError`).
  - `services.review_stats.ReviewStatsService(*, gate, progress, settings, tz, clock=None)` with `async summary(now=None) -> StatsSummary`.
  - `tests.review_stack`: `START`, `FakeClock`, `ReviewStack`, `build_review_stack(...)`, `stack_for_repository(...)`.

- [ ] **Step 1: Write and implement the response models**

Create `tests/unit/models/test_review_session.py`:

```python
from bunsho.models.review import ItemType
from bunsho.models.review_session import TypeCounts


def test_type_counts_from_a_partial_mapping() -> None:
    counts = TypeCounts.from_mapping({ItemType.KANJI: 3, ItemType.VOCAB: 7})
    assert counts == TypeCounts(kana=0, kanji=3, vocab=7)


def test_type_counts_default_to_zero() -> None:
    assert TypeCounts() == TypeCounts.from_mapping({})
```

Create `src/bunsho/models/review_session.py`:

```python
"""Response models for review sessions and statistics."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date

from pydantic import AwareDatetime, BaseModel

from bunsho.models.content import Kana, Kanji, Vocab
from bunsho.models.review import CardDirection, ItemType, SchedState


class TypeCounts(BaseModel):
    """A count per item type."""

    kana: int = 0
    kanji: int = 0
    vocab: int = 0

    @classmethod
    def from_mapping(cls, counts: Mapping[ItemType, int]) -> TypeCounts:
        """Build from a mapping; missing types count as zero."""
        return cls(
            kana=counts.get(ItemType.KANA, 0),
            kanji=counts.get(ItemType.KANJI, 0),
            vocab=counts.get(ItemType.VOCAB, 0),
        )


class GradeIntervals(BaseModel):
    """Seconds until the card would be due again, for each grade (for button labels)."""

    again: int
    hard: int
    good: int
    easy: int


class CardView(BaseModel):
    """A card ready to show: identity, scheduling facts and the content item.

    Exactly one of ``kana``, ``kanji`` and ``vocab`` is set, matching ``item_type``. Send
    ``expected_last_review`` back unchanged when answering.
    """

    item_id: str
    direction: CardDirection
    item_type: ItemType
    is_new: bool
    state: SchedState
    expected_last_review: AwareDatetime | None
    intervals: GradeIntervals
    kana: Kana | None = None
    kanji: Kanji | None = None
    vocab: Vocab | None = None


class ReviewCounts(BaseModel):
    """What is left to do right now."""

    due: TypeCounts
    new_remaining: TypeCounts


class NextCard(BaseModel):
    """Response of ``GET /reviews/next``.

    ``card`` is ``None`` when nothing is due and no new card is available; ``next_due_at``
    then says when the next scheduled card (for example a learning step) comes due.
    """

    card: CardView | None
    next_due_at: AwareDatetime | None
    counts: ReviewCounts


class TypeProgress(BaseModel):
    """Cards of one item type by scheduling state."""

    total: int
    learning: int
    review: int
    relearning: int


class LevelProgress(BaseModel):
    """Progress through one JLPT level of one item type."""

    item_type: ItemType
    level: str
    total: int
    introduced: int
    review: int


class DayCount(BaseModel):
    """Reviews on one study day."""

    day: date
    reviews: int


class StatsSummary(BaseModel):
    """Response of ``GET /stats/summary``."""

    reviewed_today: int
    introduced_today: TypeCounts
    daily_reviews: list[DayCount]
    retention_30d: float | None
    by_type: dict[ItemType, TypeProgress]
    by_level: list[LevelProgress]
```
Run: `uv run pytest tests/unit/models/test_review_session.py -q` → Expected: PASS.

- [ ] **Step 2: Write the failing `ContentGate` tests and implement it**

Create `tests/unit/services/test_content_access.py`:

```python
import asyncio
import logging
from pathlib import Path

import pytest

from bunsho.context import Context
from bunsho.models.review import ContentNotReadyError
from bunsho.services.content_access import ContentGate
from tests.base import make_service_config, make_vocab, write_content


def _ctx(tmp_path: Path, repo) -> Context:  # type: ignore[no-untyped-def]
    return Context(
        config=make_service_config(tmp_path).app,
        logger=logging.getLogger("bunsho.tests.gate"),
        content_repo=repo,
    )


def test_missing_content_is_not_ready(tmp_path: Path) -> None:
    with pytest.raises(ContentNotReadyError, match="not been built"):
        asyncio.run(ContentGate(_ctx(tmp_path, None)).repository())


def test_a_schema_mismatch_is_not_ready(tmp_path: Path) -> None:
    repo = write_content(tmp_path / "c.db", schema_version="1")
    with pytest.raises(ContentNotReadyError, match="schema_version"):
        asyncio.run(ContentGate(_ctx(tmp_path, repo)).repository())


def test_usable_content_is_returned_and_verified_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = write_content(tmp_path / "c.db", vocab=[make_vocab()])
    calls: list[int] = []
    original = repo.verify_schema
    monkeypatch.setattr(repo, "verify_schema", lambda: (calls.append(1), original())[1])
    gate = ContentGate(_ctx(tmp_path, repo))

    async def scenario() -> None:
        assert await gate.repository() is repo
        assert await gate.repository() is repo

    asyncio.run(scenario())
    assert calls == [1]


def test_a_rebuilt_repository_is_verified_again(tmp_path: Path) -> None:
    first = write_content(tmp_path / "a.db")
    ctx = _ctx(tmp_path, first)
    gate = ContentGate(ctx)

    async def scenario() -> None:
        assert await gate.repository() is first
        ctx.content_repo = write_content(tmp_path / "b.db", schema_version="1")
        with pytest.raises(ContentNotReadyError):
            await gate.repository()

    asyncio.run(scenario())
```

Create `src/bunsho/services/content_access.py`:

```python
"""Access to the content repository once it is known to be usable."""

from __future__ import annotations

import asyncio
import sqlite3

from bunsho.context import Context
from bunsho.models.review import ContentNotReadyError
from bunsho.services.content_repository import ContentRepository, ContentSchemaError


class ContentGate:
    """Hands out ``ctx.content_repo`` after checking its schema once per repository object.

    A content build replaces ``ctx.content_repo`` with a new object, so a rebuilt database is
    verified again automatically.
    """

    def __init__(self, ctx: Context) -> None:
        """Create the gate.

        Args:
            ctx: The application context whose ``content_repo`` is read on every call.
        """
        self._ctx = ctx
        self._verified: ContentRepository | None = None

    async def repository(self) -> ContentRepository:
        """Return the content repository.

        Raises:
            ContentNotReadyError: Content has not been built, has another schema version,
                or cannot be read.
        """
        repo = self._ctx.content_repo
        if repo is None:
            raise ContentNotReadyError("content has not been built yet; run a content build")
        if repo is not self._verified:
            try:
                await asyncio.to_thread(repo.verify_schema)
            except ContentSchemaError as exc:
                raise ContentNotReadyError(str(exc)) from exc
            except (sqlite3.Error, OSError) as exc:
                self._ctx.logger.warning(
                    "content_unreadable error=%s: %s", type(exc).__name__, exc
                )
                raise ContentNotReadyError("content.db cannot be read; see /health") from exc
            self._verified = repo
        return repo
```
Run: `uv run pytest tests/unit/services/test_content_access.py -q` → Expected: PASS.

- [ ] **Step 3: Create the review test stack**

Create `tests/review_stack.py`:

```python
"""Builders for review-engine tests: a fake clock and a fully wired session stack."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, tzinfo
from pathlib import Path

from bunsho.context import Context
from bunsho.db.engine import ProgressDatabase
from bunsho.db.progress_repository import ProgressRepository
from bunsho.factories import create_new_card_policy, create_scheduler
from bunsho.models.content import Kana, Kanji, Vocab
from bunsho.models.review_settings import ReviewSettings
from bunsho.orchestration.review_session import ReviewSessionOrchestrator
from bunsho.services.content_access import ContentGate
from bunsho.services.content_repository import CONTENT_SCHEMA_VERSION, ContentRepository
from bunsho.services.protocols import Scheduler
from bunsho.services.review_settings import ReviewSettingsService
from bunsho.services.review_stats import ReviewStatsService
from tests.base import make_service_config, write_content

START = datetime(2026, 9, 20, 12, 0, tzinfo=UTC)
LOGGER_NAME = "bunsho.tests.review"


class FakeClock:
    """A controllable clock: call it for the time, ``advance`` to move it."""

    def __init__(self, now: datetime = START) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **delta: float) -> None:
        """Move the clock forward, for example ``advance(minutes=11)``."""
        self.now += timedelta(**delta)


@dataclass(slots=True)
class ReviewStack:
    """Everything a review test needs, wired together."""

    ctx: Context
    clock: FakeClock
    progress: ProgressRepository
    settings: ReviewSettingsService
    orchestrator: ReviewSessionOrchestrator
    stats: ReviewStatsService


def _scheduler(settings: ReviewSettings) -> Scheduler:
    return create_scheduler("fsrs", desired_retention=settings.target_retention, enable_fuzzing=False)


def stack_for_repository(
    tmp_path: Path,
    database: ProgressDatabase,
    repository: ContentRepository | None,
    *,
    clock: FakeClock | None = None,
    tz: tzinfo = UTC,
) -> ReviewStack:
    """Wire the services around an existing content repository (``None`` = not built)."""
    fake = clock or FakeClock()
    logger = logging.getLogger(LOGGER_NAME)
    ctx = Context(config=make_service_config(tmp_path).app, logger=logger, content_repo=repository)
    progress = ProgressRepository(database)
    settings = ReviewSettingsService(progress, logger)
    gate = ContentGate(ctx)
    orchestrator = ReviewSessionOrchestrator(
        gate=gate,
        progress=progress,
        settings=settings,
        scheduler_factory=_scheduler,
        policy_factory=create_new_card_policy,
        tz=tz,
        logger=logger,
        clock=fake,
    )
    stats = ReviewStatsService(gate=gate, progress=progress, settings=settings, tz=tz, clock=fake)
    return ReviewStack(ctx, fake, progress, settings, orchestrator, stats)


def build_review_stack(
    tmp_path: Path,
    database: ProgressDatabase,
    *,
    kana: Iterable[Kana] = (),
    kanji: Iterable[Kanji] = (),
    vocab: Iterable[Vocab] = (),
    schema_version: str = CONTENT_SCHEMA_VERSION,
    built: bool = True,
    clock: FakeClock | None = None,
    tz: tzinfo = UTC,
) -> ReviewStack:
    """Write a small ``content.db`` (unless ``built=False``) and wire a stack around it."""
    repository = (
        write_content(
            tmp_path / "data" / "content.db",
            kana=kana,
            kanji=kanji,
            vocab=vocab,
            schema_version=schema_version,
        )
        if built
        else None
    )
    return stack_for_repository(tmp_path, database, repository, clock=clock, tz=tz)
```

- [ ] **Step 4: Write the failing orchestrator tests**

Create `tests/unit/orchestration/test_review_session.py`:

```python
import logging
from datetime import timedelta
from pathlib import Path

import pytest

from bunsho.db.engine import ProgressDatabase
from bunsho.models.content import JlptLevel
from bunsho.models.review import (
    CardDirection,
    CardKey,
    ContentNotReadyError,
    Grade,
    ItemType,
    SchedState,
    StaleReviewError,
    UnknownItemError,
)
from bunsho.models.review_session import CardView, TypeCounts
from bunsho.models.review_settings import NewCardPolicyName, NewLimits, ReviewSettings
from bunsho.services.fsrs_scheduler import FSRSScheduler
from tests.base import make_kana, make_kanji, make_vocab, run_with_database
from tests.review_stack import LOGGER_NAME, START, ReviewStack, build_review_stack

A = make_vocab("日本", "にほん")
B = make_vocab("学生", "がくせい")
REC, RECALL = CardDirection.RECOGNITION, CardDirection.RECALL


def key_of(card: CardView) -> CardKey:
    return CardKey(card.item_id, card.direction)


async def answer(stack: ReviewStack, card: CardView, grade: Grade = Grade.GOOD) -> None:
    await stack.orchestrator.answer(
        key_of(card), grade, expected_last_review=card.expected_last_review
    )


async def next_card(stack: ReviewStack) -> CardView:
    card = (await stack.orchestrator.next_card()).card
    assert card is not None
    return card


def test_the_first_new_card_is_the_first_vocab_recognition(tmp_path: Path) -> None:
    async def scenario(db: ProgressDatabase) -> None:
        stack = build_review_stack(tmp_path, db, vocab=[A, B])
        result = await stack.orchestrator.next_card()
        card = result.card
        assert card is not None
        assert (card.item_type, card.direction) == (ItemType.VOCAB, REC)
        assert card.is_new is True
        assert card.state is SchedState.NEW
        assert card.expected_last_review is None
        assert card.vocab is not None
        assert card.vocab.id == A.id
        assert card.kana is None
        assert card.kanji is None
        intervals = card.intervals
        assert intervals.again <= intervals.hard <= intervals.good <= intervals.easy
        assert result.counts.new_remaining == TypeCounts(kana=0, kanji=0, vocab=4)
        assert result.counts.due == TypeCounts()
        assert result.next_due_at is None

    run_with_database(tmp_path, scenario)


def test_next_is_stable_until_the_card_is_answered(tmp_path: Path) -> None:
    async def scenario(db: ProgressDatabase) -> None:
        stack = build_review_stack(tmp_path, db, vocab=[A, B])
        first = await next_card(stack)
        again = await next_card(stack)
        assert key_of(first) == key_of(again)
        assert await stack.progress.get_card(key_of(first)) is None  # next created nothing

    run_with_database(tmp_path, scenario)


def test_answering_a_new_card_advances_to_its_sibling_direction(tmp_path: Path) -> None:
    async def scenario(db: ProgressDatabase) -> None:
        stack = build_review_stack(tmp_path, db, vocab=[A, B])
        first = await next_card(stack)
        counts = await stack.orchestrator.answer(
            key_of(first), Grade.GOOD, expected_last_review=None
        )
        assert counts.new_remaining.vocab == 3
        assert counts.due.vocab == 0  # the learning step is minutes away
        second = await next_card(stack)
        assert (second.item_id, second.direction) == (A.id, RECALL)

    run_with_database(tmp_path, scenario)


def test_a_due_card_comes_before_new_cards(tmp_path: Path) -> None:
    async def scenario(db: ProgressDatabase) -> None:
        stack = build_review_stack(tmp_path, db, vocab=[A, B])
        first = await next_card(stack)
        await answer(stack, first)
        stack.clock.advance(minutes=11)
        result = await stack.orchestrator.next_card()
        card = result.card
        assert card is not None
        assert (card.item_id, card.direction) == (A.id, REC)
        assert card.is_new is False
        assert card.state is SchedState.LEARNING
        assert card.expected_last_review == START
        assert result.counts.due.vocab == 1

    run_with_database(tmp_path, scenario)


def test_reaching_the_daily_limit_leaves_only_scheduled_cards(tmp_path: Path) -> None:
    async def scenario(db: ProgressDatabase) -> None:
        stack = build_review_stack(tmp_path, db, vocab=[A, B])
        await stack.settings.save(ReviewSettings(new_limits=NewLimits(vocab=1)))
        await answer(stack, await next_card(stack))
        result = await stack.orchestrator.next_card()
        assert result.card is None
        assert result.counts.new_remaining.vocab == 0
        assert result.next_due_at is not None
        assert START < result.next_due_at <= START + timedelta(hours=1)

    run_with_database(tmp_path, scenario)


def test_the_limit_resets_after_the_rollover_hour(tmp_path: Path) -> None:
    async def scenario(db: ProgressDatabase) -> None:
        stack = build_review_stack(tmp_path, db, vocab=[A, B])
        await stack.settings.save(ReviewSettings(new_limits=NewLimits(vocab=1)))
        await answer(stack, await next_card(stack))
        assert (await stack.orchestrator.next_card()).counts.new_remaining.vocab == 0
        stack.clock.advance(hours=23)  # 11:00 the next day, after the 04:00 rollover
        assert (await stack.orchestrator.next_card()).counts.new_remaining.vocab == 1

    run_with_database(tmp_path, scenario)


def test_a_limit_of_zero_means_unlimited(tmp_path: Path) -> None:
    async def scenario(db: ProgressDatabase) -> None:
        stack = build_review_stack(tmp_path, db, vocab=[A, B])
        await stack.settings.save(ReviewSettings(new_limits=NewLimits(vocab=0)))
        for _ in range(4):
            await answer(stack, await next_card(stack), Grade.EASY)
        assert (await stack.orchestrator.next_card()).card is None  # all 4 cards introduced

    run_with_database(tmp_path, scenario)


def test_new_cards_alternate_between_types_by_remaining_allowance(tmp_path: Path) -> None:
    async def scenario(db: ProgressDatabase) -> None:
        stack = build_review_stack(
            tmp_path, db, kana=[make_kana("あ", "a"), make_kana("い", "i")], vocab=[A, B]
        )
        seen: list[ItemType] = []
        for _ in range(3):
            card = await next_card(stack)
            seen.append(card.item_type)
            await answer(stack, card)
        # Both types start at 100% of their allowance; ties go to kana, then the type that has
        # used less of its allowance goes first.
        assert seen == [ItemType.KANA, ItemType.VOCAB, ItemType.KANA]

    run_with_database(tmp_path, scenario)


def test_kanji_are_offered_in_level_order_and_unleveled_kanji_never(tmp_path: Path) -> None:
    async def scenario(db: ProgressDatabase) -> None:
        stack = build_review_stack(
            tmp_path,
            db,
            kanji=[
                make_kanji("曜", JlptLevel.N4),
                make_kanji("日", JlptLevel.N5),
                make_kanji("犬", None),
            ],
        )
        result = await stack.orchestrator.next_card()
        card = result.card
        assert card is not None
        assert card.kanji is not None
        assert (card.kanji.char, card.direction) == ("日", CardDirection.KANJI_TO_MEANING)
        assert result.counts.new_remaining.kanji == 6  # 2 leveled kanji x 3 directions

    run_with_database(tmp_path, scenario)


def test_the_active_policy_comes_from_the_settings(tmp_path: Path) -> None:
    async def scenario(db: ProgressDatabase) -> None:
        n4_word = make_vocab("先生", "せんせい", JlptLevel.N4)
        stack = build_review_stack(tmp_path, db, vocab=[A, n4_word])
        await stack.settings.save(
            ReviewSettings(
                new_card_policy=NewCardPolicyName.PINNED_LEVELS, active_levels=["N4"]
            )
        )
        card = await next_card(stack)
        assert card.vocab is not None
        assert card.vocab.id == n4_word.id

    run_with_database(tmp_path, scenario)


def test_a_stale_answer_is_rejected_and_changes_nothing(tmp_path: Path) -> None:
    async def scenario(db: ProgressDatabase) -> None:
        stack = build_review_stack(tmp_path, db, vocab=[A])
        card = await next_card(stack)
        with pytest.raises(StaleReviewError):
            await stack.orchestrator.answer(key_of(card), Grade.GOOD, expected_last_review=START)
        assert await stack.progress.get_card(key_of(card)) is None
        await answer(stack, card)
        with pytest.raises(StaleReviewError):  # a double submit of the same answer
            await answer(stack, card)

    run_with_database(tmp_path, scenario)


def test_answering_an_unknown_item_is_an_error(tmp_path: Path) -> None:
    async def scenario(db: ProgressDatabase) -> None:
        stack = build_review_stack(tmp_path, db, vocab=[A])
        with pytest.raises(UnknownItemError):
            await stack.orchestrator.answer(
                CardKey("vocab:nope:nope", REC), Grade.GOOD, expected_last_review=None
            )

    run_with_database(tmp_path, scenario)


def test_no_content_means_not_ready(tmp_path: Path) -> None:
    async def scenario(db: ProgressDatabase) -> None:
        stack = build_review_stack(tmp_path, db, built=False)
        with pytest.raises(ContentNotReadyError):
            await stack.orchestrator.next_card()
        with pytest.raises(ContentNotReadyError):
            await stack.orchestrator.answer(
                CardKey(A.id, REC), Grade.GOOD, expected_last_review=None
            )

    run_with_database(tmp_path, scenario)


def test_a_content_schema_mismatch_means_not_ready(tmp_path: Path) -> None:
    async def scenario(db: ProgressDatabase) -> None:
        stack = build_review_stack(tmp_path, db, vocab=[A], schema_version="1")
        with pytest.raises(ContentNotReadyError, match="schema_version"):
            await stack.orchestrator.next_card()

    run_with_database(tmp_path, scenario)


def test_a_due_card_whose_item_disappeared_is_skipped_with_a_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    async def scenario(db: ProgressDatabase) -> None:
        stack = build_review_stack(tmp_path, db, vocab=[A])
        scheduler = FSRSScheduler(enable_fuzzing=False)
        orphan = CardKey("vocab:gone:gone", REC)
        before = scheduler.initial(START)
        after = scheduler.schedule(before, Grade.GOOD, START)
        await stack.progress.record_review(
            orphan, before=before, after=after, grade=Grade.GOOD, mode="flip", duration_ms=None
        )
        stack.clock.advance(minutes=11)  # the orphan is now due
        card = await next_card(stack)
        assert card.item_id == A.id
        assert card.is_new is True

    with caplog.at_level(logging.WARNING, logger=LOGGER_NAME):
        run_with_database(tmp_path, scenario)
    assert "review_card_orphaned" in caplog.text
```

Run: `uv run pytest tests/unit/orchestration/test_review_session.py -q` → Expected: FAIL (`ModuleNotFoundError: bunsho.orchestration.review_session`).

- [ ] **Step 5: Implement the orchestrator**

Create `src/bunsho/orchestration/review_session.py`:

```python
"""Review sessions: choosing the next card and recording answers."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, tzinfo

from bunsho.db.progress_repository import ProgressRepository
from bunsho.models.content import Kana, Kanji, Vocab
from bunsho.models.review import (
    CardKey,
    CardSchedule,
    Grade,
    ItemType,
    SchedState,
    StaleReviewError,
    UnknownItemError,
)
from bunsho.models.review_session import (
    CardView,
    GradeIntervals,
    NextCard,
    ReviewCounts,
    TypeCounts,
)
from bunsho.models.review_settings import ReviewSettings
from bunsho.services.content_access import ContentGate
from bunsho.services.content_catalog import ContentCatalog
from bunsho.services.content_repository import ContentRepository
from bunsho.services.protocols import NewCardPolicy, Scheduler
from bunsho.services.review_settings import ReviewSettingsService
from bunsho.services.study_day import study_day_window

REVIEW_MODE = "flip"
_TYPE_ORDER = (ItemType.KANA, ItemType.KANJI, ItemType.VOCAB)
_ORPHAN_SCAN = 50
"""How many due cards to look through for one whose content item still exists."""

Item = Kana | Kanji | Vocab


@dataclass(frozen=True, slots=True)
class _Plan:
    """What is due and what could be introduced right now."""

    settings: ReviewSettings
    introduced: dict[ItemType, int]
    due_counts: dict[ItemType, int]
    new_keys: dict[ItemType, list[CardKey]]

    @property
    def counts(self) -> ReviewCounts:
        return ReviewCounts(
            due=TypeCounts.from_mapping(self.due_counts),
            new_remaining=TypeCounts.from_mapping(
                {item_type: len(keys) for item_type, keys in self.new_keys.items()}
            ),
        )

    def pick_new(self) -> CardKey | None:
        """Pick from the type with the largest remaining share of its daily allowance.

        Ties go to the earlier type in kana, kanji, vocab order. An unlimited type counts
        as a full allowance.
        """
        best: CardKey | None = None
        best_share = -1.0
        for item_type in _TYPE_ORDER:
            keys = self.new_keys[item_type]
            if not keys:
                continue
            limit = self.settings.new_limits.for_type(item_type)
            share = 1.0 if limit == 0 else (limit - self.introduced.get(item_type, 0)) / limit
            if share > best_share:
                best, best_share = keys[0], share
        return best


def _load_item(repo: ContentRepository, key: CardKey) -> Item | None:
    match key.item_type:
        case ItemType.KANA:
            return repo.get_kana(key.item_id)
        case ItemType.KANJI:
            return repo.get_kanji(key.item_id)
        case ItemType.VOCAB:
            return repo.get_vocab(key.item_id)


def _seconds_until(due: CardSchedule, now: datetime) -> int:
    return max(0, round((due.due - now).total_seconds()))


def _view(
    key: CardKey, schedule: CardSchedule, item: Item, scheduler: Scheduler, now: datetime
) -> CardView:
    previews = scheduler.preview(schedule, now)
    return CardView(
        item_id=key.item_id,
        direction=key.direction,
        item_type=key.item_type,
        is_new=schedule.state is SchedState.NEW,
        state=schedule.state,
        expected_last_review=schedule.last_review,
        intervals=GradeIntervals(
            again=_seconds_until(previews[Grade.AGAIN], now),
            hard=_seconds_until(previews[Grade.HARD], now),
            good=_seconds_until(previews[Grade.GOOD], now),
            easy=_seconds_until(previews[Grade.EASY], now),
        ),
        kana=item if isinstance(item, Kana) else None,
        kanji=item if isinstance(item, Kanji) else None,
        vocab=item if isinstance(item, Vocab) else None,
    )


class ReviewSessionOrchestrator:
    """Coordinates settings, content, scheduling and persistence for reviews.

    Stateless between calls: ``next_card`` creates nothing, so an ungraded new card is simply
    offered again, and every call reads the current settings.
    """

    def __init__(
        self,
        *,
        gate: ContentGate,
        progress: ProgressRepository,
        settings: ReviewSettingsService,
        scheduler_factory: Callable[[ReviewSettings], Scheduler],
        policy_factory: Callable[[ReviewSettings], NewCardPolicy],
        tz: tzinfo,
        logger: logging.Logger,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        """Create the orchestrator.

        Args:
            gate: Hands out the usable content repository.
            progress: Card state and review log storage.
            settings: The review settings service.
            scheduler_factory: Builds the scheduler from the current settings.
            policy_factory: Builds the new-card policy from the current settings.
            tz: Timezone in which the study-day rollover hour is read.
            logger: Logger for key=value messages.
            clock: Returns the current UTC time (defaults to the system clock).
        """
        self._gate = gate
        self._progress = progress
        self._settings = settings
        self._scheduler_factory = scheduler_factory
        self._policy_factory = policy_factory
        self._tz = tz
        self._logger = logger
        self._clock = clock or (lambda: datetime.now(UTC))

    async def next_card(self, now: datetime | None = None) -> NextCard:
        """Return the next card to study, plus what is left to do.

        Due cards come first (earliest due); otherwise a new card chosen by the active
        policy within today's per-type limits; otherwise no card and ``next_due_at``.

        Args:
            now: Override the current time (tests).

        Returns:
            The next card, the soonest future due time when there is no card, and the counts.

        Raises:
            ContentNotReadyError: Content is missing, unreadable or has the wrong schema.
        """
        moment = now or self._clock()
        repo = await self._gate.repository()
        settings = await self._settings.load()
        scheduler = self._scheduler_factory(settings)
        plan = await self._plan(moment, repo, settings)
        card = await self._due_view(moment, repo, scheduler)
        if card is None:
            key = plan.pick_new()
            item = None if key is None else await asyncio.to_thread(_load_item, repo, key)
            if key is not None and item is not None:
                card = _view(key, scheduler.initial(moment), item, scheduler, moment)
        next_due_at = None if card is not None else await self._progress.next_due_after(moment)
        return NextCard(card=card, next_due_at=next_due_at, counts=plan.counts)

    async def answer(
        self,
        key: CardKey,
        grade: Grade,
        *,
        expected_last_review: datetime | None,
        duration_ms: int | None = None,
        now: datetime | None = None,
    ) -> ReviewCounts:
        """Grade a card and store the result.

        Args:
            key: The card being answered.
            grade: The grade given.
            expected_last_review: The ``expected_last_review`` from ``next_card`` (``None``
                for a new card). It must match the stored card.
            duration_ms: How long the answer took, if known.
            now: Override the current time (tests).

        Returns:
            Fresh counts after the answer.

        Raises:
            ContentNotReadyError: Content is missing, unreadable or has the wrong schema.
            UnknownItemError: The item id is not in the content database.
            StaleReviewError: The card changed since it was fetched.
        """
        moment = now or self._clock()
        repo = await self._gate.repository()
        if await asyncio.to_thread(_load_item, repo, key) is None:
            raise UnknownItemError(f"unknown item {key.item_id!r} for {key.direction.value}")
        settings = await self._settings.load()
        scheduler = self._scheduler_factory(settings)
        stored = await self._progress.get_card(key)
        before = stored.schedule if stored else scheduler.initial(moment)
        if before.last_review != expected_last_review:
            raise StaleReviewError(
                f"card {key.item_id} ({key.direction.value}) changed since it was fetched"
            )
        after = scheduler.schedule(before, grade, moment)
        await self._progress.record_review(
            key,
            before=before,
            after=after,
            grade=grade,
            mode=REVIEW_MODE,
            duration_ms=duration_ms,
        )
        self._logger.info(
            "review_recorded item=%s direction=%s grade=%s state=%s due=%s",
            key.item_id,
            key.direction.value,
            grade.name,
            after.state.name,
            after.due.isoformat(),
        )
        return (await self._plan(moment, repo, settings)).counts

    async def _due_view(
        self, now: datetime, repo: ContentRepository, scheduler: Scheduler
    ) -> CardView | None:
        for stored in await self._progress.due_cards(now, _ORPHAN_SCAN):
            item = await asyncio.to_thread(_load_item, repo, stored.key)
            if item is not None:
                return _view(stored.key, stored.schedule, item, scheduler, now)
            self._logger.warning(
                "review_card_orphaned item=%s direction=%s",
                stored.key.item_id,
                stored.key.direction.value,
            )
        return None

    async def _plan(self, now: datetime, repo: ContentRepository, settings: ReviewSettings) -> _Plan:
        window = study_day_window(now, settings.rollover_hour, self._tz)
        states = await self._progress.card_states()
        introduced = await self._progress.new_cards_introduced(*window)
        due_counts = await self._progress.due_counts(now)
        policy = self._policy_factory(settings)
        catalog = ContentCatalog(repo)
        new_keys: dict[ItemType, list[CardKey]] = {}
        for item_type in _TYPE_ORDER:
            limit = settings.new_limits.for_type(item_type)
            allowance = None if limit == 0 else max(0, limit - introduced.get(item_type, 0))
            if allowance == 0:
                new_keys[item_type] = []
                continue
            entries = await asyncio.to_thread(catalog.entries, item_type)
            new_keys[item_type] = policy.select(item_type, entries, states, allowance)
        return _Plan(settings, introduced, due_counts, new_keys)
```
The `_plan` signature line exceeds 100 characters as typed; `ruff format` will wrap it.

Run: `uv run pytest tests/unit/orchestration/test_review_session.py -q` → Expected: PASS. If `test_new_cards_alternate...` fails on the third card, print `_plan(...).introduced` and the shares before changing the expectation: after one kana and one vocab card both types have used 1 of 20, so the tie goes to kana.

- [ ] **Step 6: Write the failing statistics tests**

Create `tests/unit/services/test_review_stats.py`:

```python
from datetime import date
from pathlib import Path

from bunsho.db.engine import ProgressDatabase
from bunsho.models.content import JlptLevel
from bunsho.models.review import CardKey, Grade, ItemType
from bunsho.models.review_session import CardView, TypeCounts
from tests.base import make_kanji, make_vocab, run_with_database
from tests.review_stack import build_review_stack

A = make_vocab("日本", "にほん")
B = make_vocab("学生", "がくせい")


def test_an_empty_history_has_zero_counts_and_no_retention(tmp_path: Path) -> None:
    async def scenario(db: ProgressDatabase) -> None:
        stack = build_review_stack(tmp_path, db, vocab=[A, B], kanji=[make_kanji("日")])
        summary = await stack.stats.summary()
        assert summary.reviewed_today == 0
        assert summary.introduced_today == TypeCounts()
        assert summary.retention_30d is None
        assert len(summary.daily_reviews) == 30
        assert all(day.reviews == 0 for day in summary.daily_reviews)
        assert summary.daily_reviews[-1].day == date(2026, 9, 20)
        vocab = summary.by_type[ItemType.VOCAB]
        assert (vocab.total, vocab.learning, vocab.review, vocab.relearning) == (4, 0, 0, 0)
        assert summary.by_type[ItemType.KANJI].total == 3
        assert summary.by_type[ItemType.KANA].total == 0

    run_with_database(tmp_path, scenario)


def test_summary_reflects_reviews_over_several_weeks(tmp_path: Path) -> None:
    async def scenario(db: ProgressDatabase) -> None:
        stack = build_review_stack(tmp_path, db, vocab=[A, B])
        orchestrator = stack.orchestrator

        async def grade_next(grade: Grade) -> CardView:
            card = (await orchestrator.next_card()).card
            assert card is not None
            await orchestrator.answer(
                CardKey(card.item_id, card.direction),
                grade,
                expected_last_review=card.expected_last_review,
            )
            return card

        await grade_next(Grade.EASY)  # A recognition -> Review
        await grade_next(Grade.EASY)  # A recall -> Review
        today = await stack.stats.summary()
        assert today.reviewed_today == 2
        assert today.introduced_today == TypeCounts(kana=0, kanji=0, vocab=2)

        stack.clock.advance(days=25)  # both cards are due (an Easy first review is ~16 days)
        first = await grade_next(Grade.GOOD)  # stays in Review
        second = await grade_next(Grade.AGAIN)  # lapses into Relearning
        assert (first.direction.value, second.direction.value) == ("recognition", "recall")

        summary = await stack.stats.summary()
        assert summary.reviewed_today == 2
        by_day = {d.day: d.reviews for d in summary.daily_reviews}
        assert by_day[date(2026, 9, 20)] == 2
        assert by_day[date(2026, 10, 15)] == 2
        assert summary.retention_30d == 0.5  # one of the two Review-state answers was Again
        vocab = summary.by_type[ItemType.VOCAB]
        assert (vocab.total, vocab.review, vocab.relearning) == (4, 1, 1)
        n5 = next(p for p in summary.by_level if p.item_type is ItemType.VOCAB and p.level == "N5")
        assert (n5.total, n5.introduced, n5.review) == (4, 2, 1)

    run_with_database(tmp_path, scenario)


def test_levels_are_listed_for_kanji_and_vocab_but_not_kana(tmp_path: Path) -> None:
    async def scenario(db: ProgressDatabase) -> None:
        stack = build_review_stack(tmp_path, db, vocab=[A], kanji=[make_kanji("日")])
        summary = await stack.stats.summary()
        pairs = {(p.item_type, p.level) for p in summary.by_level}
        assert pairs == {(t, lvl.label) for t in (ItemType.KANJI, ItemType.VOCAB) for lvl in JlptLevel}

    run_with_database(tmp_path, scenario)
```

Run: `uv run pytest tests/unit/services/test_review_stats.py -q` → Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 7: Implement `ReviewStatsService`**

Create `src/bunsho/services/review_stats.py`:

```python
"""Statistics for the dashboard: today's work, recent history and progress per level."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta, tzinfo

from bunsho.db.progress_repository import ProgressRepository
from bunsho.models.content import JlptLevel
from bunsho.models.review import DIRECTIONS_BY_TYPE, CardKey, Grade, ItemType, SchedState
from bunsho.models.review_session import (
    DayCount,
    LevelProgress,
    StatsSummary,
    TypeCounts,
    TypeProgress,
)
from bunsho.services.content_access import ContentGate
from bunsho.services.content_catalog import ContentCatalog
from bunsho.services.review_settings import ReviewSettingsService
from bunsho.services.study_day import study_date, study_day_window

RETENTION_DAYS = 30


def _count(states: Mapping[CardKey, SchedState], wanted: SchedState) -> int:
    return sum(1 for state in states.values() if state is wanted)


class ReviewStatsService:
    """Builds ``StatsSummary`` from the review log, card states and the content catalogue."""

    def __init__(
        self,
        *,
        gate: ContentGate,
        progress: ProgressRepository,
        settings: ReviewSettingsService,
        tz: tzinfo,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        """Create the service.

        Args:
            gate: Hands out the usable content repository.
            progress: Card state and review log storage.
            settings: The review settings service (for the rollover hour).
            tz: Timezone in which the rollover hour is read.
            clock: Returns the current UTC time (defaults to the system clock).
        """
        self._gate = gate
        self._progress = progress
        self._settings = settings
        self._tz = tz
        self._clock = clock or (lambda: datetime.now(UTC))

    async def summary(self, now: datetime | None = None) -> StatsSummary:
        """Return the statistics as of ``now``.

        Retention is the share of reviews of cards in the Review state, over the last 30 study
        days, that were graded Hard or better; it is ``None`` when there were none.

        Raises:
            ContentNotReadyError: Content is missing, unreadable or has the wrong schema.
        """
        moment = now or self._clock()
        repo = await self._gate.repository()
        rollover = (await self._settings.load()).rollover_hour
        window_start, window_end = study_day_window(moment, rollover, self._tz)
        today = study_date(moment, rollover, self._tz)
        daily = dict.fromkeys(
            [today - timedelta(days=offset) for offset in range(RETENTION_DAYS - 1, -1, -1)], 0
        )
        records = await self._progress.reviews_between(
            window_start - timedelta(days=RETENTION_DAYS + 1), window_end
        )
        answered = passed = 0
        for record in records:
            day = study_date(record.reviewed_at, rollover, self._tz)
            if day not in daily:
                continue
            daily[day] += 1
            if record.state_before is SchedState.REVIEW:
                answered += 1
                if record.grade >= Grade.HARD:
                    passed += 1
        introduced = await self._progress.new_cards_introduced(window_start, window_end)
        states = await self._progress.card_states()
        catalog = ContentCatalog(repo)
        by_type: dict[ItemType, TypeProgress] = {}
        by_level: list[LevelProgress] = []
        for item_type in ItemType:
            entries = await asyncio.to_thread(catalog.entries, item_type)
            directions = DIRECTIONS_BY_TYPE[item_type]
            typed = {key: state for key, state in states.items() if key.item_type is item_type}
            by_type[item_type] = TypeProgress(
                total=len(entries) * len(directions),
                learning=_count(typed, SchedState.LEARNING),
                review=_count(typed, SchedState.REVIEW),
                relearning=_count(typed, SchedState.RELEARNING),
            )
            if item_type is ItemType.KANA:
                continue
            level_of = {entry.item_id: entry.level for entry in entries}
            for level in JlptLevel.study_order():
                in_level = [
                    state for key, state in typed.items() if level_of.get(key.item_id) is level
                ]
                by_level.append(
                    LevelProgress(
                        item_type=item_type,
                        level=level.label,
                        total=sum(1 for e in entries if e.level is level) * len(directions),
                        introduced=len(in_level),
                        review=sum(1 for state in in_level if state is SchedState.REVIEW),
                    )
                )
        return StatsSummary(
            reviewed_today=daily[today],
            introduced_today=TypeCounts.from_mapping(introduced),
            daily_reviews=[DayCount(day=day, reviews=count) for day, count in daily.items()],
            retention_30d=None if answered == 0 else round(passed / answered, 4),
            by_type=by_type,
            by_level=by_level,
        )
```
Run: `uv run pytest tests/unit/services/test_review_stats.py tests/unit/orchestration -q` → Expected: PASS. If `test_summary_reflects_reviews_over_several_weeks` fails because a card is not yet due after 25 days, print `card.due` after the Easy reviews and raise the advance to just past it (keep 30 days of history in view: the first review must stay within the last 30 study days, so the advance must be at most 29 days).

- [ ] **Step 8: Lint and commit**

```bash
uv run pytest tests/unit -q
uv run ruff format . && uv run ruff check . && uv run mypy
git add src/bunsho/models/review_session.py src/bunsho/services/content_access.py src/bunsho/orchestration/review_session.py src/bunsho/services/review_stats.py tests/review_stack.py tests/unit/models/test_review_session.py tests/unit/services/test_content_access.py tests/unit/orchestration/test_review_session.py tests/unit/services/test_review_stats.py
git commit -m "feat: review session orchestrator and statistics" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```
Expected: PASS.

---

## Task 7: Review, statistics and settings endpoints

**Files:**
- Create: `src/bunsho/api/responses.py`, `src/bunsho/api/routers/reviews.py`, `src/bunsho/api/routers/stats.py`, `src/bunsho/api/routers/settings.py`
- Modify: `src/bunsho/api/schemas.py`, `src/bunsho/api/services.py`, `src/bunsho/api/app.py`, `tests/unit/api/conftest.py`
- Test: `tests/unit/api/test_review_routes.py`, `tests/unit/api/test_settings_routes.py`

**Interfaces:**
- Consumes: Tasks 1-6.
- Produces (HTTP, all under `/api/v1`, all require a bearer token):
  - `GET /reviews/next` → `NextCard` (operation id `getNextReview`).
  - `POST /reviews/answer` body `AnswerRequest` → `ReviewCounts` (`answerReview`); 404 unknown item, 409 stale, 503 content not ready, 422 invalid body.
  - `GET /stats/summary` → `StatsSummary` (`getStatsSummary`); 503 when content is not ready.
  - `GET /settings` → `ReviewSettings` (`getSettings`), `PUT /settings` body `ReviewSettings` → `ReviewSettings` (`updateSettings`).
  - `Services.review_settings`, `Services.reviews`, `Services.stats`; `api.responses` constants `UNAUTHORIZED`, `NOT_FOUND`, `CONFLICT`, `TOO_MANY_REQUESTS`, `UNAVAILABLE`; `api.schemas.ErrorResponse`, `api.schemas.AnswerRequest`.

- [ ] **Step 1: Add the API test fixtures**

Append to `tests/unit/api/conftest.py` (extend its imports: `from bunsho.models.content import JlptLevel`, `from tests.base import PASSWORD, StubOrchestrator, make_kana, make_kanji, make_vocab, write_content`):

```python
@pytest.fixture
def review_config(service_config: ServiceConfig) -> ServiceConfig:
    """``service_config`` whose data folder already holds a small ``content.db``."""
    write_content(
        service_config.app.content_db_path,
        kana=[make_kana("あ", "a")],
        kanji=[make_kanji("日", JlptLevel.N5)],
        vocab=[make_vocab("日本", "にほん"), make_vocab("学生", "がくせい", JlptLevel.N4)],
    )
    return service_config


@pytest.fixture
def review_client(review_config: ServiceConfig) -> Iterator[TestClient]:
    """A ``TestClient`` on an app that starts with content already built."""
    with TestClient(create_app(review_config)) as test_client:
        yield test_client


@pytest.fixture
def review_headers(review_client: TestClient) -> dict[str, str]:
    """An ``Authorization`` header for ``review_client``."""
    response = review_client.post(
        "/api/v1/auth/login", json={"username": "james", "password": PASSWORD}
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}
```

- [ ] **Step 2: Write the failing review route tests**

Create `tests/unit/api/test_review_routes.py`:

```python
from typing import Any

import pytest
from fastapi.testclient import TestClient

NEXT = "/api/v1/reviews/next"
ANSWER = "/api/v1/reviews/answer"
STATS = "/api/v1/stats/summary"
SETTINGS = "/api/v1/settings"

Headers = dict[str, str]


def _body(card: dict[str, Any], grade: int = 3) -> dict[str, Any]:
    return {
        "item_id": card["item_id"],
        "direction": card["direction"],
        "grade": grade,
        "expected_last_review": card["expected_last_review"],
    }


@pytest.mark.parametrize(
    ("method", "url"),
    [("get", NEXT), ("post", ANSWER), ("get", STATS), ("get", SETTINGS), ("put", SETTINGS)],
)
def test_every_new_route_requires_a_token(
    review_client: TestClient, method: str, url: str
) -> None:
    response = getattr(review_client, method)(url, **({} if method == "get" else {"json": {}}))
    assert response.status_code == 401
    assert isinstance(response.json()["detail"], str)


def test_next_returns_the_first_card_with_content_and_counts(
    review_client: TestClient, review_headers: Headers
) -> None:
    response = review_client.get(NEXT, headers=review_headers)
    assert response.status_code == 200
    body = response.json()
    card = body["card"]
    assert (card["item_type"], card["direction"]) == ("kana", "glyph_to_sound")
    assert card["is_new"] is True
    assert card["state"] == 0
    assert card["expected_last_review"] is None
    assert card["kana"]["char"] == "あ"
    assert card["kanji"] is None
    assert card["vocab"] is None
    assert set(card["intervals"]) == {"again", "hard", "good", "easy"}
    assert body["next_due_at"] is None
    assert body["counts"] == {
        "due": {"kana": 0, "kanji": 0, "vocab": 0},
        "new_remaining": {"kana": 2, "kanji": 3, "vocab": 4},
    }


def test_answering_records_the_review_and_updates_the_counts(
    review_client: TestClient, review_headers: Headers
) -> None:
    card = review_client.get(NEXT, headers=review_headers).json()["card"]
    response = review_client.post(ANSWER, json=_body(card), headers=review_headers)
    assert response.status_code == 200
    assert response.json()["new_remaining"] == {"kana": 1, "kanji": 3, "vocab": 4}
    following = review_client.get(NEXT, headers=review_headers).json()["card"]
    assert (following["item_id"], following["direction"]) != (card["item_id"], card["direction"])


def test_answering_the_same_card_twice_is_a_conflict(
    review_client: TestClient, review_headers: Headers
) -> None:
    card = review_client.get(NEXT, headers=review_headers).json()["card"]
    body = _body(card)
    assert review_client.post(ANSWER, json=body, headers=review_headers).status_code == 200
    second = review_client.post(ANSWER, json=body, headers=review_headers)
    assert second.status_code == 409
    assert isinstance(second.json()["detail"], str)


def test_answering_an_unknown_item_is_a_404(
    review_client: TestClient, review_headers: Headers
) -> None:
    body = {
        "item_id": "vocab:nope:nope",
        "direction": "recognition",
        "grade": 3,
        "expected_last_review": None,
    }
    response = review_client.post(ANSWER, json=body, headers=review_headers)
    assert response.status_code == 404
    assert isinstance(response.json()["detail"], str)


@pytest.mark.parametrize(
    "change",
    [
        {"grade": 5},
        {"grade": 0},
        {"direction": "sideways"},
        {"duration_ms": -1},
        {"item_id": ""},
        {"expected_last_review": "2026-09-20T12:00:00"},  # no timezone
    ],
)
def test_an_invalid_answer_body_is_a_422(
    review_client: TestClient, review_headers: Headers, change: dict[str, Any]
) -> None:
    card = review_client.get(NEXT, headers=review_headers).json()["card"]
    response = review_client.post(
        ANSWER, json={**_body(card), **change}, headers=review_headers
    )
    assert response.status_code == 422
    assert isinstance(response.json()["detail"], list)


def test_a_missing_expected_last_review_is_a_422(
    review_client: TestClient, review_headers: Headers
) -> None:
    card = review_client.get(NEXT, headers=review_headers).json()["card"]
    body = _body(card)
    del body["expected_last_review"]
    assert review_client.post(ANSWER, json=body, headers=review_headers).status_code == 422


def test_content_that_is_not_built_answers_503(
    stub_client: TestClient, auth_headers: Headers
) -> None:
    for method, url in [("get", NEXT), ("get", STATS)]:
        response = getattr(stub_client, method)(url, headers=auth_headers)
        assert response.status_code == 503
        assert "content" in response.json()["detail"]


def test_stats_reflect_an_answer(review_client: TestClient, review_headers: Headers) -> None:
    card = review_client.get(NEXT, headers=review_headers).json()["card"]
    review_client.post(ANSWER, json=_body(card), headers=review_headers)
    body = review_client.get(STATS, headers=review_headers).json()
    assert body["reviewed_today"] == 1
    assert body["introduced_today"] == {"kana": 1, "kanji": 0, "vocab": 0}
    assert len(body["daily_reviews"]) == 30
    assert body["daily_reviews"][-1]["reviews"] == 1
    assert body["retention_30d"] is None
    assert set(body["by_type"]) == {"kana", "kanji", "vocab"}
    assert body["by_type"]["kana"]["total"] == 2
    assert {p["item_type"] for p in body["by_level"]} == {"kanji", "vocab"}
```

Create `tests/unit/api/test_settings_routes.py`:

```python
from fastapi.testclient import TestClient

from bunsho.models.review_settings import ReviewSettings

SETTINGS = "/api/v1/settings"
Headers = dict[str, str]


def test_settings_default_to_the_documented_values(
    review_client: TestClient, review_headers: Headers
) -> None:
    response = review_client.get(SETTINGS, headers=review_headers)
    assert response.status_code == 200
    assert response.json() == ReviewSettings().model_dump(mode="json")


def test_a_saved_settings_document_is_returned_by_later_reads(
    review_client: TestClient, review_headers: Headers
) -> None:
    document = ReviewSettings().model_dump(mode="json")
    document.update(
        new_card_policy="pinned_levels", active_levels=["N4", "N5"], target_retention=0.85
    )
    document["new_limits"] = {"kana": 0, "kanji": 5, "vocab": 10}
    saved = review_client.put(SETTINGS, json=document, headers=review_headers)
    assert saved.status_code == 200
    assert saved.json() == document
    assert review_client.get(SETTINGS, headers=review_headers).json() == document


def test_invalid_settings_are_rejected_and_nothing_is_saved(
    review_client: TestClient, review_headers: Headers
) -> None:
    good = ReviewSettings(target_retention=0.85).model_dump(mode="json")
    assert review_client.put(SETTINGS, json=good, headers=review_headers).status_code == 200
    bad = {**good, "target_retention": 1.5, "rollover_hour": 30}
    response = review_client.put(SETTINGS, json=bad, headers=review_headers)
    assert response.status_code == 422
    assert isinstance(response.json()["detail"], list)
    assert len(response.json()["detail"]) == 2  # every problem is reported together
    assert review_client.get(SETTINGS, headers=review_headers).json() == good


def test_unknown_settings_fields_are_rejected(
    review_client: TestClient, review_headers: Headers
) -> None:
    body = {**ReviewSettings().model_dump(mode="json"), "surprise": True}
    assert review_client.put(SETTINGS, json=body, headers=review_headers).status_code == 422


def test_a_partial_document_takes_defaults_for_the_rest(
    review_client: TestClient, review_headers: Headers
) -> None:
    review_client.put(SETTINGS, json={"target_retention": 0.8}, headers=review_headers)
    assert review_client.get(SETTINGS, headers=review_headers).json() == {
        **ReviewSettings().model_dump(mode="json"),
        "target_retention": 0.8,
    }
```

Run: `uv run pytest tests/unit/api/test_review_routes.py tests/unit/api/test_settings_routes.py -q` → Expected: FAIL (404 for the new routes).

- [ ] **Step 3: Add the error and request models and the response fragments**

In `src/bunsho/api/schemas.py` change the pydantic import to `from pydantic import AwareDatetime, BaseModel, Field`, add `from bunsho.models.review import CardDirection, Grade`, and append:

```python
class ErrorResponse(BaseModel):
    """Body of every error response except 422: a human-readable message."""

    detail: str


class AnswerRequest(BaseModel):
    """Body of ``POST /reviews/answer``."""

    item_id: str = Field(min_length=1, max_length=255)
    direction: CardDirection
    grade: Grade
    expected_last_review: AwareDatetime | None = Field(
        description=(
            "The card's `expected_last_review` from `GET /reviews/next`, unchanged (null for "
            "a new card). A mismatch means the card changed since it was fetched: 409."
        )
    )
    duration_ms: int | None = Field(default=None, ge=0, le=3_600_000)
```

Create `src/bunsho/api/responses.py`:

```python
"""Documented error responses, shared by the routers so the OpenAPI schema stays uniform."""

from __future__ import annotations

from typing import Any

from bunsho.api.schemas import ErrorResponse

Responses = dict[int | str, dict[str, Any]]

UNAUTHORIZED: Responses = {
    401: {"model": ErrorResponse, "description": "Missing, invalid or expired access token."}
}
NOT_FOUND: Responses = {
    404: {"model": ErrorResponse, "description": "The item or task does not exist."}
}
CONFLICT: Responses = {
    409: {
        "model": ErrorResponse,
        "description": "The request conflicts with the current state (for example a stale card).",
    }
}
TOO_MANY_REQUESTS: Responses = {
    429: {
        "model": ErrorResponse,
        "description": "Too many failed logins; wait for the number of seconds in Retry-After.",
    }
}
UNAVAILABLE: Responses = {
    503: {
        "model": ErrorResponse,
        "description": "Content has not been built, or content.db cannot be used.",
    }
}
```

- [ ] **Step 4: Add the routers**

Create `src/bunsho/api/routers/reviews.py`:

```python
"""Review routes: fetch the next card and answer it."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from bunsho.api.deps import ServicesDep, require_user
from bunsho.api.responses import CONFLICT, NOT_FOUND, UNAUTHORIZED, UNAVAILABLE
from bunsho.api.schemas import AnswerRequest
from bunsho.models.review import CardKey
from bunsho.models.review_session import NextCard, ReviewCounts

router = APIRouter(
    prefix="/reviews",
    tags=["reviews"],
    dependencies=[Depends(require_user)],
    responses={**UNAUTHORIZED, **UNAVAILABLE},
)


@router.get("/next", response_model=NextCard, operation_id="getNextReview")
async def next_review(services: ServicesDep) -> NextCard:
    """The next card to study, or none (with the time the next one comes due).

    Fetching a card creates nothing: an unanswered new card is offered again next time.

    Raises:
        ContentNotReadyError: Mapped to 503 by the app.
    """
    return await services.reviews.next_card()


@router.post(
    "/answer",
    response_model=ReviewCounts,
    operation_id="answerReview",
    responses={**NOT_FOUND, **CONFLICT},
)
async def answer_review(body: AnswerRequest, services: ServicesDep) -> ReviewCounts:
    """Grade a card. Returns the counts of what is left.

    Raises:
        UnknownItemError: Mapped to 404 by the app.
        StaleReviewError: Mapped to 409 by the app.
        ContentNotReadyError: Mapped to 503 by the app.
    """
    return await services.reviews.answer(
        CardKey(body.item_id, body.direction),
        body.grade,
        expected_last_review=body.expected_last_review,
        duration_ms=body.duration_ms,
    )
```

Create `src/bunsho/api/routers/stats.py`:

```python
"""Statistics route."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from bunsho.api.deps import ServicesDep, require_user
from bunsho.api.responses import UNAUTHORIZED, UNAVAILABLE
from bunsho.models.review_session import StatsSummary

router = APIRouter(
    prefix="/stats",
    tags=["stats"],
    dependencies=[Depends(require_user)],
    responses={**UNAUTHORIZED, **UNAVAILABLE},
)


@router.get("/summary", response_model=StatsSummary, operation_id="getStatsSummary")
async def stats_summary(services: ServicesDep) -> StatsSummary:
    """Today's work, 30 days of history, retention and progress per type and level."""
    return await services.stats.summary()
```

Create `src/bunsho/api/routers/settings.py`:

```python
"""Review settings routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from bunsho.api.deps import ServicesDep, require_user
from bunsho.api.responses import UNAUTHORIZED
from bunsho.models.review_settings import ReviewSettings

router = APIRouter(
    prefix="/settings",
    tags=["settings"],
    dependencies=[Depends(require_user)],
    responses=UNAUTHORIZED,
)


@router.get("", response_model=ReviewSettings, operation_id="getSettings")
async def get_settings(services: ServicesDep) -> ReviewSettings:
    """The current review settings (defaults until they are first saved)."""
    return await services.review_settings.load()


@router.put("", response_model=ReviewSettings, operation_id="updateSettings")
async def update_settings(body: ReviewSettings, services: ServicesDep) -> ReviewSettings:
    """Replace the review settings. All fields are validated together; nothing is saved on error.

    Omitted fields take their defaults (this is a full replacement, not a patch).
    """
    return await services.review_settings.save(body)
```

- [ ] **Step 5: Wire the services and the error handler**

In `src/bunsho/api/services.py` add imports:

```python
from bunsho.db.progress_repository import ProgressRepository
from bunsho.factories import (
    create_content_build_orchestrator,
    create_context,
    create_new_card_policy,
    create_scheduler_from_settings,
)
from bunsho.orchestration.review_session import ReviewSessionOrchestrator
from bunsho.services.content_access import ContentGate
from bunsho.services.review_settings import ReviewSettingsService
from bunsho.services.review_stats import ReviewStatsService
from bunsho.services.study_day import resolve_timezone
```
(replace the existing `from bunsho.factories import create_content_build_orchestrator, create_context` line), add the fields to `Services` after `instance_lock`:

```python
    review_settings: ReviewSettingsService
    reviews: ReviewSessionOrchestrator
    stats: ReviewStatsService
```

and in `build_services`, replace the `return Services(...)` block (inside the inner `try`) with:

```python
            progress = ProgressRepository(progress_db)
            review_settings = ReviewSettingsService(progress, logger)
            gate = ContentGate(ctx)
            tz = resolve_timezone(logger=logger)
            return Services(
                config=config,
                ctx=ctx,
                progress_db=progress_db,
                auth=AuthService(config.auth),
                throttle=LoginThrottle(),
                tasks=BuildTaskManager(ctx, factory),
                health=HealthService(progress_db, ctx),
                instance_lock=lock,
                review_settings=review_settings,
                reviews=ReviewSessionOrchestrator(
                    gate=gate,
                    progress=progress,
                    settings=review_settings,
                    scheduler_factory=create_scheduler_from_settings,
                    policy_factory=create_new_card_policy,
                    tz=tz,
                    logger=logger,
                ),
                stats=ReviewStatsService(
                    gate=gate, progress=progress, settings=review_settings, tz=tz
                ),
            )
```

In `src/bunsho/api/app.py`: extend the router import to `from bunsho.api.routers import admin, auth, content, health, reviews, settings, stats, ws`, add `from bunsho.models.review import ContentNotReadyError, ReviewError, StaleReviewError, UnknownItemError`, add the handler next to `_validation_error_handler`:

```python
_REVIEW_ERROR_STATUS: dict[type[ReviewError], int] = {
    ContentNotReadyError: 503,
    UnknownItemError: 404,
    StaleReviewError: 409,
}


async def _review_error_handler(_request: Request, exc: Exception) -> JSONResponse:
    """Map review-engine errors to their HTTP status with a string ``detail``."""
    status_code = next(
        (code for kind, code in _REVIEW_ERROR_STATUS.items() if isinstance(exc, kind)), 500
    )
    return JSONResponse(status_code=status_code, content={"detail": str(exc)})
```

register it and the routers in `create_app` (right after the validation handler and after `content.router`):

```python
    app.add_exception_handler(ReviewError, _review_error_handler)
```
```python
    app.include_router(reviews.router, prefix=API_PREFIX)
    app.include_router(stats.router, prefix=API_PREFIX)
    app.include_router(settings.router, prefix=API_PREFIX)
```

- [ ] **Step 6: Run the API tests, the whole suite, lint, commit**

```bash
uv run pytest tests/unit/api -q
uv run pytest -q
uv run ruff format . && uv run ruff check . && uv run mypy
git add src/bunsho/api/responses.py src/bunsho/api/routers/reviews.py src/bunsho/api/routers/stats.py src/bunsho/api/routers/settings.py src/bunsho/api/schemas.py src/bunsho/api/services.py src/bunsho/api/app.py tests/unit/api/conftest.py tests/unit/api/test_review_routes.py tests/unit/api/test_settings_routes.py
git commit -m "feat: review, statistics and settings endpoints" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```
Expected: PASS, and the whole suite stays green (existing tests build `Services` only through `build_services`).
Things to check if a test fails: (a) a `422` where a `401` is expected means the dependency order changed, so keep `dependencies=[Depends(require_user)]` on the router; (b) a `TypeError` about `Services` fields means another test constructs `Services(...)` directly, so add the missing arguments there.

## Task 8: OpenAPI quality, typed content summary, CORS

**Files:**
- Modify: `src/bunsho/services/content_repository.py`, `src/bunsho/api/schemas.py`, `src/bunsho/api/app.py`, `src/bunsho/api/routers/auth.py`, `health.py`, `admin.py`, `content.py`, `tests/unit/api/test_admin_routes.py`, `tests/unit/api/test_app_startup.py`
- Test: `tests/unit/services/test_content_repository_catalog.py` (append), `tests/unit/api/test_content_routes.py`, `tests/unit/api/test_openapi.py`

**Interfaces:**
- Consumes: Task 7 (`api.responses`, `ErrorResponse`, the new routers), existing routers and `ws` schemas (`WsAuthMessage`, `WsReady`, `WsSnapshot`, `WsEvent`).
- Produces:
  - `ContentRepository.level_counts() -> LevelCounts(vocab_by_level: dict[str, int], kanji_by_level: dict[str, int], unleveled_kanji: int)` (keys `"N5".."N1"`, zeros included).
  - `ContentSummaryResponse` gains `unleveled_kanji: int`, `kanji_by_level: dict[str, int]`, `vocab_by_level: dict[str, int]` (all default empty/0 when not built). `kanji` keeps counting every kanji row (leveled + unleveled).
  - Operation ids: `login`, `refreshToken`, `getHealth`, `getConfigCheck`, `startContentBuild`, `getLatestContentBuild`, `getContentBuild`, `getContentSummary` (plus Task 7's `getNextReview`, `answerReview`, `getStatsSummary`, `getSettings`, `updateSettings`).
  - `/openapi.json` publishes `WsAuthMessage`, `WsReady`, `WsSnapshot`, `WsEvent` under `components.schemas`.
  - CORS allows `GET`, `POST`, `PUT`.

- [ ] **Step 1: Write the failing level-count tests**

Append to `tests/unit/services/test_content_repository_catalog.py`:

```python
def test_level_counts_cover_every_level_and_count_unleveled_kanji(tmp_path: Path) -> None:
    counts = _repo(tmp_path).level_counts()
    assert counts.vocab_by_level == {"N5": 2, "N4": 1, "N3": 0, "N2": 0, "N1": 0}
    assert counts.kanji_by_level == {"N5": 1, "N4": 1, "N3": 0, "N2": 0, "N1": 0}
    assert counts.unleveled_kanji == 1
```
Run: `uv run pytest tests/unit/services/test_content_repository_catalog.py -q` → Expected: FAIL (`AttributeError: ... 'level_counts'`).

- [ ] **Step 2: Implement `level_counts`**

In `src/bunsho/services/content_repository.py` add next to `ContentCounts`:

```python
@dataclass(frozen=True, slots=True)
class LevelCounts:
    """Row counts per JLPT level (``"N5"`` first, every level present)."""

    vocab_by_level: dict[str, int]
    kanji_by_level: dict[str, int]
    unleveled_kanji: int
```

and this method on `ContentRepository` (after `counts`):

```python
    def level_counts(self) -> LevelCounts:
        """Return vocab and kanji counts per JLPT level plus the unleveled kanji count."""
        with self._connect() as con:
            vocab = dict(con.execute("SELECT level, COUNT(*) FROM vocab GROUP BY level").fetchall())
            kanji = dict(
                con.execute(
                    "SELECT level, COUNT(*) FROM kanji WHERE level IS NOT NULL GROUP BY level"
                ).fetchall()
            )
            unleveled = con.execute("SELECT COUNT(*) FROM kanji WHERE level IS NULL").fetchone()[0]
        order = JlptLevel.study_order()
        return LevelCounts(
            vocab_by_level={level.label: vocab.get(int(level), 0) for level in order},
            kanji_by_level={level.label: kanji.get(int(level), 0) for level in order},
            unleveled_kanji=unleveled,
        )
```
Run: `uv run pytest tests/unit/services/test_content_repository_catalog.py -q` → Expected: PASS.

- [ ] **Step 3: Write the failing content-summary route tests and update the old exact-match test**

In `tests/unit/api/test_admin_routes.py`, `test_real_build_finishes_and_makes_content_visible` compares the not-built summary to an exact dict; extend it with the new defaults:

```python
    assert stub_client.get(summary_url, headers=auth_headers).json() == {
        "built": False,
        "kana": 0,
        "kanji": 0,
        "vocab": 0,
        "unleveled_kanji": 0,
        "kanji_by_level": {},
        "vocab_by_level": {},
        "meta": {},
    }
```

Create `tests/unit/api/test_content_routes.py`:

```python
from fastapi.testclient import TestClient

from bunsho.config.service import ServiceConfig
from bunsho.api.app import create_app
from bunsho.models.content import JlptLevel
from tests.base import PASSWORD, make_kana, make_kanji, make_vocab, write_content

SUMMARY = "/api/v1/content/summary"


def test_the_summary_types_leveled_and_unleveled_kanji(service_config: ServiceConfig) -> None:
    write_content(
        service_config.app.content_db_path,
        kana=[make_kana("あ", "a")],
        kanji=[make_kanji("日", JlptLevel.N5), make_kanji("曜", JlptLevel.N4), make_kanji("犬", None)],
        vocab=[make_vocab("日本", "にほん"), make_vocab("学生", "がくせい", JlptLevel.N4)],
    )
    with TestClient(create_app(service_config)) as client:
        token = client.post(
            "/api/v1/auth/login", json={"username": "james", "password": PASSWORD}
        ).json()["access_token"]
        body = client.get(SUMMARY, headers={"Authorization": f"Bearer {token}"}).json()
    assert body["built"] is True
    assert (body["kana"], body["kanji"], body["vocab"]) == (1, 3, 2)  # kanji counts every row
    assert body["unleveled_kanji"] == 1
    assert body["kanji_by_level"] == {"N5": 1, "N4": 1, "N3": 0, "N2": 0, "N1": 0}
    assert body["vocab_by_level"] == {"N5": 1, "N4": 1, "N3": 0, "N2": 0, "N1": 0}
```
(Order the imports so ruff's isort is happy: `bunsho.api.app` before `bunsho.config.service`.)
Run: `uv run pytest tests/unit/api/test_content_routes.py tests/unit/api/test_admin_routes.py -q` → Expected: FAIL (`KeyError: 'unleveled_kanji'`, and the old exact-match test).

- [ ] **Step 4: Type the summary**

In `src/bunsho/api/schemas.py`:

```python
class ContentSummaryResponse(BaseModel):
    """Response of ``GET /content/summary``.

    ``kanji`` counts every kanji row; ``unleveled_kanji`` of them have no JLPT level and are
    not offered as lessons.
    """

    built: bool
    kana: int = 0
    kanji: int = 0
    vocab: int = 0
    unleveled_kanji: int = 0
    kanji_by_level: dict[str, int] = Field(default_factory=dict)
    vocab_by_level: dict[str, int] = Field(default_factory=dict)
    meta: dict[str, str] = Field(default_factory=dict)
```

Replace `src/bunsho/api/routers/content.py` with:

```python
"""Read-only content routes."""

from __future__ import annotations

import asyncio
import sqlite3

from fastapi import APIRouter, Depends

from bunsho.api.deps import ServicesDep, require_user
from bunsho.api.responses import UNAUTHORIZED
from bunsho.api.schemas import ContentSummaryResponse

router = APIRouter(
    prefix="/content",
    tags=["content"],
    dependencies=[Depends(require_user)],
    responses=UNAUTHORIZED,
)


@router.get("/summary", response_model=ContentSummaryResponse, operation_id="getContentSummary")
async def content_summary(services: ServicesDep) -> ContentSummaryResponse:
    """Counts and build metadata for ``content.db``; ``built: false`` if absent or unreadable."""
    repo = services.ctx.content_repo
    if repo is None:
        return ContentSummaryResponse(built=False)
    try:
        counts = await asyncio.to_thread(repo.counts)
        levels = await asyncio.to_thread(repo.level_counts)
        meta = await asyncio.to_thread(repo.meta)
    except (sqlite3.Error, OSError) as exc:
        # Keep paths and driver messages out of the response; /health reports the fault.
        services.ctx.logger.warning(
            "content_summary_unreadable error=%s: %s", type(exc).__name__, exc
        )
        return ContentSummaryResponse(built=False)
    return ContentSummaryResponse(
        built=True,
        kana=counts.kana,
        kanji=counts.kanji,
        vocab=counts.vocab,
        unleveled_kanji=levels.unleveled_kanji,
        kanji_by_level=levels.kanji_by_level,
        vocab_by_level=levels.vocab_by_level,
        meta=meta,
    )
```
Run: `uv run pytest tests/unit/api/test_content_routes.py tests/unit/api/test_admin_routes.py -q` → Expected: PASS.

- [ ] **Step 5: Write the failing OpenAPI guard tests**

Create `tests/unit/api/test_openapi.py`:

```python
import re
from collections.abc import Iterator
from typing import Any

from fastapi.testclient import TestClient

PUBLIC = {
    ("get", "/api/v1/health"),
    ("post", "/api/v1/auth/login"),
    ("post", "/api/v1/auth/refresh"),
}
HTTP_METHODS = {"get", "post", "put", "patch", "delete"}


def _schema(client: TestClient) -> dict[str, Any]:
    return client.get("/openapi.json").json()  # type: ignore[no-any-return]


def _operations(schema: dict[str, Any]) -> Iterator[tuple[str, str, dict[str, Any]]]:
    for path, item in schema["paths"].items():
        for method, operation in item.items():
            if method in HTTP_METHODS:
                yield method, path, operation


def test_every_operation_has_a_unique_explicit_camel_case_id(client: TestClient) -> None:
    ids = [operation["operationId"] for _, _, operation in _operations(_schema(client))]
    assert len(ids) >= 13
    assert len(ids) == len(set(ids))
    for operation_id in ids:
        # FastAPI's generated ids look like get_health_api_v1_health_get.
        assert re.fullmatch(r"[a-z][A-Za-z0-9]*", operation_id), operation_id


def test_every_protected_operation_documents_401(client: TestClient) -> None:
    for method, path, operation in _operations(_schema(client)):
        if (method, path) not in PUBLIC:
            assert "401" in operation["responses"], f"{method} {path}"


def test_documented_errors_use_the_error_model_with_a_string_detail(client: TestClient) -> None:
    schema = _schema(client)
    assert schema["components"]["schemas"]["ErrorResponse"]["properties"]["detail"]["type"] == (
        "string"
    )
    for method, path, operation in _operations(schema):
        for code in ("401", "404", "409", "429", "503"):
            response = operation["responses"].get(code)
            if response is None or (method, path) == ("get", "/api/v1/health"):
                continue
            ref = response["content"]["application/json"]["schema"]["$ref"]
            assert ref.endswith("/ErrorResponse"), f"{method} {path} {code}"


def test_the_expected_status_codes_are_documented(client: TestClient) -> None:
    operations = {
        operation["operationId"]: set(operation["responses"])
        for _, _, operation in _operations(_schema(client))
    }
    assert {"401", "429"} <= operations["login"]
    assert {"401", "404", "409", "503"} <= operations["answerReview"]
    assert {"401", "503"} <= operations["getNextReview"]
    assert {"401", "503"} <= operations["getStatsSummary"]
    assert {"401", "409"} <= operations["startContentBuild"]
    assert {"401", "404"} <= operations["getContentBuild"]
    assert {"200", "503"} <= operations["getHealth"]
    assert "422" in operations["answerReview"]


def test_websocket_messages_are_published_in_the_components(client: TestClient) -> None:
    schemas = _schema(client)["components"]["schemas"]
    for name in ("WsAuthMessage", "WsReady", "WsSnapshot", "WsEvent"):
        assert name in schemas, name
    assert schemas["WsAuthMessage"]["properties"]["type"]["const"] == "auth"
    # References inside the message schemas resolve within the same document.
    snapshot_task = schemas["WsSnapshot"]["properties"]["task"]
    assert snapshot_task["$ref"] == "#/components/schemas/BuildStatusResponse"
    assert "BuildStatusResponse" in schemas


def test_the_schema_is_generated_once(client: TestClient) -> None:
    assert _schema(client) == _schema(client)
```
Run: `uv run pytest tests/unit/api/test_openapi.py -q` → Expected: FAIL (old routers have no explicit ids or documented errors; no `Ws*` components).

- [ ] **Step 6: Give the existing routers operation ids and documented responses**

`src/bunsho/api/routers/auth.py`: add `from bunsho.api.responses import TOO_MANY_REQUESTS, UNAUTHORIZED` and change the two decorators:

```python
@router.post(
    "/login",
    response_model=TokenResponse,
    operation_id="login",
    responses={**UNAUTHORIZED, **TOO_MANY_REQUESTS},
)
```
```python
@router.post(
    "/refresh", response_model=TokenResponse, operation_id="refreshToken", responses=UNAUTHORIZED
)
```

`src/bunsho/api/routers/health.py`:

```python
@router.get(
    "/health",
    response_model=HealthResponse,
    operation_id="getHealth",
    responses={
        503: {
            "model": HealthResponse,
            "description": "A dependency is in error; the body still lists every component.",
        }
    },
)
```

`src/bunsho/api/routers/admin.py`: add `from bunsho.api.responses import CONFLICT, NOT_FOUND, UNAUTHORIZED`, change the router to `APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_user)], responses=UNAUTHORIZED)` and the four decorators:

```python
@router.get("/config-check", response_model=ConfigCheckResponse, operation_id="getConfigCheck")
```
```python
@router.post(
    "/content/build",
    response_model=BuildStatusResponse,
    status_code=status.HTTP_202_ACCEPTED,
    operation_id="startContentBuild",
    responses=CONFLICT,
)
```
```python
@router.get(
    "/content/build",
    response_model=BuildStatusResponse,
    operation_id="getLatestContentBuild",
    responses=NOT_FOUND,
)
```
```python
@router.get(
    "/content/build/{task_id}",
    response_model=BuildStatusResponse,
    operation_id="getContentBuild",
    responses=NOT_FOUND,
)
```
(`content.py` was done in Step 4.)

- [ ] **Step 7: Publish the WebSocket message schemas and allow `PUT` in CORS**

In `src/bunsho/api/app.py` add imports `from typing import Any, cast` (extend the existing `cast` import), `from fastapi.openapi.utils import get_openapi`, and `from bunsho.api.schemas import WsAuthMessage, WsEvent, WsReady, WsSnapshot`; add the helper above `create_app`:

```python
_WS_MESSAGE_MODELS = (WsAuthMessage, WsReady, WsSnapshot, WsEvent)


def _publish_websocket_schemas(app: FastAPI) -> None:
    """Add the WebSocket message models to ``/openapi.json``.

    FastAPI documents only HTTP routes, so without this the typed frontend client could not
    generate types for the messages on ``/ws/tasks``.
    """

    def custom_openapi() -> dict[str, Any]:
        if app.openapi_schema:
            return app.openapi_schema
        schema = get_openapi(
            title=app.title,
            version=app.version,
            description=app.description,
            routes=app.routes,
        )
        components = schema.setdefault("components", {}).setdefault("schemas", {})
        for model in _WS_MESSAGE_MODELS:
            message = model.model_json_schema(ref_template="#/components/schemas/{model}")
            for name, definition in message.pop("$defs", {}).items():
                components.setdefault(name, definition)
            components[model.__name__] = message
        app.openapi_schema = schema
        return schema

    app.openapi = custom_openapi  # type: ignore[method-assign]
```

call `_publish_websocket_schemas(app)` in `create_app` right before `return app`, and change the CORS line to `allow_methods=["GET", "POST", "PUT"],`.

Append to `tests/unit/api/test_app_startup.py`:

```python
def test_cors_allows_put_for_the_settings_endpoint(tmp_path: Path) -> None:
    origin = "http://localhost:5173"
    config = make_service_config(tmp_path, cors_origins=(origin,))
    preflight = {"Origin": origin, "Access-Control-Request-Method": "PUT"}
    with TestClient(create_app(config)) as client:
        response = client.options("/api/v1/settings", headers=preflight)
    assert response.status_code == 200
    assert "PUT" in response.headers["access-control-allow-methods"]
```

- [ ] **Step 8: Run everything, lint, commit**

```bash
uv run pytest tests/unit/api -q
uv run pytest -q
uv run ruff format . && uv run ruff check . && uv run mypy
git add src/bunsho/services/content_repository.py src/bunsho/api/schemas.py src/bunsho/api/app.py src/bunsho/api/routers/auth.py src/bunsho/api/routers/health.py src/bunsho/api/routers/admin.py src/bunsho/api/routers/content.py tests/unit/api/test_admin_routes.py tests/unit/api/test_app_startup.py tests/unit/api/test_content_routes.py tests/unit/api/test_openapi.py tests/unit/services/test_content_repository_catalog.py
git commit -m "feat: typed content summary, explicit OpenAPI operation ids, documented errors, WebSocket schemas" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```
Expected: PASS. If `test_documented_errors_use_the_error_model...` fails on a route that documents a code with the FastAPI default model, add the matching fragment from `bunsho.api.responses` to that route.

---

## Task 9: Real-content simulation, container smoke test and documentation

**Files:**
- Create: `tests/integration/conftest.py`, `tests/integration/test_review_day.py`
- Modify: `tests/integration/test_real_content_build.py`, `scripts/smoke_test.py`, `README.md`, `CHANGELOG.md`, `TODO.md`, `docs/superpowers/specs/2026-09-20-bunsho-2a-review-engine-design.md`

**Interfaces:**
- Consumes: everything above; `tests.review_stack.stack_for_repository`.
- Produces: `real_content` session fixture (`tuple[BuildReport, ContentRepository]`, built once from the real deck; skips when the deck or jamdict is missing, fails instead under `CI`); the review round trip in the container smoke test.

- [ ] **Step 1: Share the real content build between integration tests**

Create `tests/integration/conftest.py`:

```python
"""Fixtures for tests that run against the real deck and the real jamdict database."""

from pathlib import Path

import pytest

from bunsho.config.settings import DEFAULT_DECK_FILENAME, DEFAULT_DECK_SHA256, AppConfig
from bunsho.factories import create_content_build_orchestrator, create_context
from bunsho.orchestration.content_build import BuildReport
from bunsho.services.content_repository import ContentRepository

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session")
def real_content(
    tmp_path_factory: pytest.TempPathFactory,
) -> tuple[BuildReport, ContentRepository]:
    """Build ``content.db`` once per test session from the pinned deck and jamdict-data-fix."""
    config = AppConfig(
        data_dir=tmp_path_factory.mktemp("data"),
        resources_dir=REPO_ROOT / "resources",
        deck_filename=DEFAULT_DECK_FILENAME,
        deck_sha256=DEFAULT_DECK_SHA256,
        jamdict_db=None,
        log_level="INFO",
    )
    if not config.deck_path.is_file():
        pytest.skip(f"deck not present: {config.deck_path}")
    ctx = create_context(config)
    if ctx.kanji_source is None:
        pytest.skip("jamdict-data-fix database unavailable")
    report = create_content_build_orchestrator(ctx).build(config.deck_path, config.content_db_path)
    return report, ContentRepository(config.content_db_path)
```

In `tests/integration/test_real_content_build.py` replace the body of the module-scoped `built` fixture so it reuses the session build (keep the fixture name so the tests do not change):

```python
@pytest.fixture(scope="module")
def built(
    real_content: tuple[BuildReport, ContentRepository],
) -> tuple[BuildReport, ContentRepository]:
    return real_content
```
and delete the imports that became unused (`AppConfig`, `DEFAULT_DECK_FILENAME`, `DEFAULT_DECK_SHA256`, `create_content_build_orchestrator`, `create_context`; keep the others) and the now-unused `REPO_ROOT` if nothing else in the file uses it (check with `grep -n REPO_ROOT`).
Run: `uv run pytest tests/integration/test_real_content_build.py -q` → Expected: PASS (or SKIP on a machine without the deck; under `CI` a skip fails).

- [ ] **Step 2: Write the real-content day simulation**

Create `tests/integration/test_review_day.py`:

```python
from datetime import timedelta
from pathlib import Path

import pytest

from bunsho.db.engine import ProgressDatabase
from bunsho.models.review import CardKey, Grade, ItemType
from bunsho.models.review_settings import ReviewSettings
from bunsho.orchestration.content_build import BuildReport
from bunsho.services.content_repository import ContentRepository
from tests.base import run_with_database
from tests.review_stack import START, stack_for_repository


@pytest.mark.integration
def test_a_study_day_on_the_real_content(
    tmp_path: Path, real_content: tuple[BuildReport, ContentRepository]
) -> None:
    _, repo = real_content
    limits = ReviewSettings().new_limits

    async def scenario(db: ProgressDatabase) -> None:
        stack = stack_for_repository(tmp_path, db, repo)
        orchestrator = stack.orchestrator
        introduced: dict[ItemType, int] = {}
        seen: set[CardKey] = set()
        while (card := (await orchestrator.next_card()).card) is not None:
            key = CardKey(card.item_id, card.direction)
            assert card.is_new, "nothing is due within a single study day after Easy answers"
            assert key not in seen, "a new card must never be offered twice"
            seen.add(key)
            introduced[card.item_type] = introduced.get(card.item_type, 0) + 1
            await orchestrator.answer(
                key, Grade.EASY, expected_last_review=card.expected_last_review
            )

        assert introduced == {
            ItemType.KANA: limits.kana,
            ItemType.KANJI: limits.kanji,
            ItemType.VOCAB: limits.vocab,
        }
        finished = await orchestrator.next_card()
        assert finished.card is None
        assert finished.counts.new_remaining.kana == 0
        assert finished.counts.new_remaining.kanji == 0
        assert finished.counts.new_remaining.vocab == 0
        assert finished.next_due_at is not None
        assert finished.next_due_at >= START + timedelta(days=1)  # Easy graduates to Review

        stack.clock.advance(days=1)  # the next study day: the allowance is back
        tomorrow = await orchestrator.next_card()
        assert tomorrow.card is not None
        assert tomorrow.card.is_new
        assert tomorrow.counts.new_remaining.kana == limits.kana
        assert tomorrow.counts.new_remaining.kanji == limits.kanji
        assert tomorrow.counts.new_remaining.vocab == limits.vocab

        summary = await stack.stats.summary()
        assert summary.reviewed_today == 0
        assert sum(day.reviews for day in summary.daily_reviews) == len(seen)

    run_with_database(tmp_path, scenario)
```
Run: `uv run pytest tests/integration/test_review_day.py -q` → Expected: PASS (SKIP without the deck locally; fails under `CI`). The first card of the day is kana (ties go to kana), and the introduced totals equal the default limits because the real content has more than enough cards of each type.

- [ ] **Step 3: Extend the container smoke test**

In `scripts/smoke_test.py` add these functions after `expect_summary`:

```python
def exercise_reviews(access: str) -> None:
    """Read the settings, answer one new card and check it is recorded exactly once."""
    status, settings = request("GET", "/settings", token=access)
    expect(status == 200, f"settings returned {status}: {settings}")
    expect(settings["new_card_policy"] == "strict_order", f"unexpected settings: {settings}")
    status, first = request("GET", "/reviews/next", token=access)
    expect(status == 200, f"reviews/next returned {status}: {first}")
    card = first["card"]
    expect(card is not None and card["is_new"] is True, f"no new card offered: {first}")
    # Every type starts with a full allowance and ties go to kana.
    expect(card["item_type"] == "kana", f"first new card is {card['item_type']}, not kana")
    body = {
        "item_id": card["item_id"],
        "direction": card["direction"],
        "grade": 3,
        "expected_last_review": card["expected_last_review"],
    }
    status, counts = request("POST", "/reviews/answer", token=access, body=body)
    expect(status == 200, f"answer returned {status}: {counts}")
    status, _ = request("POST", "/reviews/answer", token=access, body=body)
    expect(status == 409, f"a repeated answer returned {status}, not 409")
    expect_reviews_recorded(access)


def expect_reviews_recorded(access: str) -> None:
    """Check ``/stats/summary`` counts exactly one review (robust across the study-day rollover)."""
    status, stats = request("GET", "/stats/summary", token=access)
    expect(status == 200, f"stats returned {status}: {stats}")
    total = sum(day["reviews"] for day in stats["daily_reviews"])
    expect(total == 1, f"expected exactly one recorded review, stats say {total}")
```

In `run()` call them: after the first `expect_summary(tokens["access"])` add

```python
    log("answering one card")
    exercise_reviews(tokens["access"])
```
and after the post-restart `expect_summary(refreshed["access_token"])` add

```python
    expect_reviews_recorded(refreshed["access_token"])  # progress.db survived the restart
```
Update the module docstring's first sentence to "(build, start, log in, build content, review a card, restart)".
Run a syntax check: `uv run python -c "import ast,sys; ast.parse(open('scripts/smoke_test.py', encoding='utf-8').read())"`. If Docker is available run the real smoke test now: `uv run python scripts/smoke_test.py` (Expected: ends with `[smoke] PASS`, about two minutes). If Docker is not available, say so in the PR; CI's `smoke` job runs it.

- [ ] **Step 4: Update the user-facing documentation**

`README.md`: insert this section immediately before the `## Running with Docker` heading (it documents what the API can now do; adjust wording to match the surrounding style, keep the content):

````markdown
### Studying (review API)

After a content build, the API serves flashcards. Every route needs a bearer token.

| Route | What it does |
|---|---|
| `GET /api/v1/reviews/next` | The next card (with its content, and how long each grade would wait), or no card plus `next_due_at`; also the counts still to do. Fetching creates nothing. |
| `POST /api/v1/reviews/answer` | Grade a card: `item_id`, `direction`, `grade` (1 Again, 2 Hard, 3 Good, 4 Easy), `expected_last_review` (copied from the card; `null` for a new card) and optionally `duration_ms`. A card that changed in the meantime (a double submit, or a second device) answers `409`. |
| `GET /api/v1/stats/summary` | Reviews today, the last 30 days, 30-day retention, and progress per type and JLPT level. |
| `GET /api/v1/settings`, `PUT /api/v1/settings` | The review settings (below). `PUT` replaces the whole document. |

A card is an item plus a direction: kana `glyph_to_sound` / `sound_to_glyph`, kanji `kanji_to_meaning` / `kanji_to_reading` / `meaning_to_kanji`, vocabulary `recognition` / `recall`. Item ids are opaque strings taken from the API (`vocab:度:ど#2` exists); do not build or parse them. A card is created the first time it is graded; scheduling uses FSRS with a configurable target retention.

**Settings** (defaults in brackets): `new_card_policy` (`strict_order`: N5 first, then N4 and so on; `mastery_unlock`: the next level also waits until `mastery_threshold` [0.80] of the current level's cards are in the FSRS Review state; `pinned_levels`: only `active_levels` [`["N5"]`]), `new_limits` per type in **cards** per day (kana 20, kanji 15, vocab 20; `0` = unlimited), `target_retention` [0.90, range 0.70-0.99] and `rollover_hour` [4, range 0-23]. Unleveled kanji are never offered.

**Study day and timezone.** Daily limits reset at `rollover_hour` in the server's timezone, read from the `TZ` environment variable (an IANA name such as `America/New_York`). Without `TZ` the study day uses UTC and the service logs a warning. In Docker, put `TZ=America/New_York` in the env file next to the credentials.

**One instance per data folder.** The service takes an exclusive lock (`.bunsho.instance.lock`) in the data folder; a second instance on the same folder refuses to start with an explanatory error. `progress.db` runs in WAL mode, so you will also see `progress.db-wal` and `progress.db-shm` files next to it; back up the folder with the service stopped, or use the timestamped backups in `backups/`.

**Frontend development.** Allow the Vite dev server with `BUNSHO_SERVER__CORS_ORIGINS=http://localhost:5173` (comma-separated for several); CORS is off unless origins are listed, and `GET`, `POST` and `PUT` are allowed.
````

`CHANGELOG.md`: under `## [Unreleased]` → `### Added`, append:

```markdown
- Review engine: FSRS scheduling (`py-fsrs`) with a configurable target retention, cards created
  on first grade, `GET /reviews/next`, `POST /reviews/answer` (stale answers get 409),
  `GET /stats/summary` and `GET`/`PUT /settings`. New cards follow one of three user-selectable
  policies (strict N5-to-N1 order, mastery unlock, pinned levels) within per-type daily limits and
  a study-day rollover hour.
- `GET /content/summary` reports unleveled kanji (`unleveled_kanji`) and per-level counts for
  kanji and vocabulary.
- OpenAPI: explicit operation ids, documented 401/404/409/429/503 responses, and the WebSocket
  message schemas in `components`, so a typed client can be generated.
```
and under `### Changed` (create the heading after `### Added` if it does not exist):

```markdown
- `progress.db` runs in WAL mode with foreign keys enforced, and the service takes an exclusive
  lock on the data folder: a second instance on the same folder refuses to start.
- CORS allows `PUT` in addition to `GET` and `POST` (still off unless origins are configured).
- Startup checks the `content.db` schema version and logs an error when a rebuild is needed.
```

`TODO.md`: (1) replace the "Status:" paragraph at the top with: "Status: Plans 1A, 1B and 1C are merged. Plan 2A (review engine backend) is implemented on `feat/plan-2a-review-engine`; Plan 2B (frontend and delivery) is next. Design: the specs in `docs/superpowers/specs/`. Plans: `docs/superpowers/plans/`."; (2) tick these items (`- [ ]` to `- [x]`) and append " (Plan 2A)" to each: "`Scheduler` interface + `FSRSScheduler`...", "Review/stats endpoints; React 18..." (edit the text to "Review/stats/settings endpoints (Plan 2A); React 18 + Vite + TS frontend (Plan 2B)" and leave it unticked), "Document that content ids are opaque...", "Instance lock for the data folder...", "OpenAPI quality...", "Typed `unleveled_kanji`...", "WAL journal mode...", "Call `ContentRepository.verify_schema()` at startup...", and "Plan 2: `list_kanji()` / `counts().kanji` now include unleveled rows..." (lessons filter them via `ContentRepository.catalog`); (3) edit the "CORS: allow methods beyond GET/POST..." item to "done for `PUT` (Plan 2A); the Vite dev origin is documented as an opt-in setting"; (4) under "Plan 2" add new open items: "- [ ] Sibling burying (hold a new item's other directions until a later day)", "- [ ] `review_log` retention/export before the file grows unwieldy", "- [ ] A Prometheus-style or structured metric for review latency (only if the box gets monitoring)".

Spec: append to `docs/superpowers/specs/2026-09-20-bunsho-2a-review-engine-design.md`:

```markdown
## Implementation notes (added while planning and building)

- The item type is derived from the direction, so an unknown item is a 404 and an unknown
  direction a 422; there is no "invalid pair" case.
- `ContentRepository.catalog(item_type)` returns ids and levels only (unleveled kanji excluded in
  SQL); it replaces the `leveled_only` option on `list_kanji`.
- The hydrated card carries the domain item (`kana`, `kanji` or `vocab`) rather than pre-rendered
  front/back fields; the frontend decides the layout per direction.
- The study-day timezone is `TZ` when set, otherwise UTC with a startup warning; `tzdata` is a
  dependency.
- The startup backup already used the SQLite backup API (WAL-safe); a test now proves it.
- The review settings are one JSON document in `app_setting` (`review_settings`); `PUT` is a full
  replacement.
```

- [ ] **Step 5: Lint, run everything, commit**

```bash
uv run pytest -q
uv run ruff format . && uv run ruff check . && uv run mypy
uv run bandit -c pyproject.toml -r src -q
git add tests/integration/conftest.py tests/integration/test_real_content_build.py tests/integration/test_review_day.py scripts/smoke_test.py README.md CHANGELOG.md TODO.md docs/superpowers/specs/2026-09-20-bunsho-2a-review-engine-design.md
git commit -m "test: real-content study day and container review round trip; docs for the review API" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```
Expected: PASS (integration tests skip locally without the deck).

---

## Task 10: Whole-branch verification and review

**Files:** none (fixes found here are committed as small `fix:` commits).

- [ ] **Step 1: Full local gate**

```bash
unset VIRTUAL_ENV
uv run ruff format --check . && uv run ruff check . && uv run mypy && uv run bandit -c pyproject.toml -r src -q
uv run pytest --cov=src/bunsho --cov-report=term-missing -q
```
Expected: all clean; coverage at least 90% overall. Look at the per-file report for the new modules (`progress_repository`, `review_session`, `review_stats`, `new_card_policies`, `study_day`, `instance_lock`): each should be at or above 90%. Add the missing tests, not `pragma: no cover`, unless the line is a genuine defensive branch.

- [ ] **Step 2: Flake hunt for timing-sensitive tests**

```bash
for i in $(seq 40); do uv run pytest tests/unit/db tests/unit/api tests/unit/orchestration -q -x -p no:cacheprovider || break; done
```
Expected: 40 clean loops. Any failure is a real race (instance lock, WAL writer contention, TestClient teardown); fix the cause.

- [ ] **Step 3: Container smoke test**

`uv run python scripts/smoke_test.py` (needs Docker and the real deck). Expected: `[smoke] PASS`. Also confirm WAL works on the named volume: `docker compose -p bunsho-smoke exec bunsho ls /data` (with `BUNSHO_SMOKE_KEEP=1`) shows `progress.db-wal` while the service runs, then run the stack down with `docker compose -p bunsho-smoke down -v`.

- [ ] **Step 4: Whole-branch review**

Dispatch the final review with the `superpowers:requesting-code-review` skill (a Sonnet review, not Opus: it is enough for this level of work; whole branch against `main`, given the spec, this plan and "Refinements to the spec"). Fix Critical and Important findings with focused commits (`fix: ...`); record deferred Minor findings in `TODO.md`. Ask the reviewer to check specifically: the compare-and-set in `record_review`, that `next_card` never writes, that the daily allowance cannot be exceeded by concurrent answers, timezone handling of `study_date` near the rollover and DST, and that no route leaks paths or exception text.

- [ ] **Step 5: Push and prepare the PR for James**

```bash
git push
gh pr ready   # only when CI is green on ubuntu, windows and macOS
```
Update the draft PR description (keep the attribution line: `🤖 Generated with [Claude Code](https://claude.com/claude-code)`): summary of the endpoints, the six spec refinements, the migration story (none), the new dependencies (`py-fsrs`, `tzdata`), test counts and coverage, and what Plan 2B will build on. James reviews and merges; do not merge.
