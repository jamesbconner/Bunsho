# Bunshō: Typed-Answer and Multiple-Choice Review Modes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a learner answer a card by typing or by picking from four options, graded automatically (correct → Good, wrong → Again), chosen per item type (kana/kanji/vocab) on the Settings page — alongside the existing flip-and-grade mode, which is unchanged.

**Architecture:** Backend: `CardView` gains `mode`, `accepted_answers` and `choices`, resolved by the orchestrator from three new per-item-type `ReviewSettings` fields. A new pure `answer_key` service builds the accepted-answer strings per direction (with a small romanization-variant table and the じ/ぢ・ず/づ equivalence); a new `distractors` service samples plausible wrong options from `content.db` via the existing `ContentCatalog`. No change to `POST /reviews/answer`. Frontend: two new `ReviewMode` implementations (`TypedMode`, `ChoiceMode`) grade client-side by checking the learner's input against `accepted_answers`, and `ReviewPage` gains a held-card feedback step between grading and advancing.

**Tech Stack:** Same as Plan 2B-2/2B-3 (Python 3.13, FastAPI, Pydantic; React 19, Vite 8, TypeScript 6.0.3, Mantine 9, TanStack Query 5, Vitest 5 + React Testing Library + MSW 2). No new dependency.

**Spec:** `docs/superpowers/specs/2026-09-22-bunsho-typed-mc-review-modes-design.md` (parents: `2026-09-20-bunsho-2a-review-engine-design.md`, `2026-09-20-bunsho-2b2-study-loop-design.md`). Read it before starting.

## Global Constraints

Every task's requirements include this section.

- **Latest stable versions of every library and tool** (James): this plan adds no dependency.
- Backend: `ruff format`/`ruff check` clean; `mypy` clean; `bandit` clean; Google-style docstrings on every public function, method and class; type annotations everywhere (`list[str]`, `X | None`, no bare `Any`).
- Frontend: strict TypeScript (`strict`, `noUncheckedIndexedAccess`, `erasableSyntaxOnly`: no enums, no parameter properties, no namespaces; use `import type`); ESLint (flat config, `recommendedTypeChecked`, `react-hooks`, `react-refresh`) with zero errors and **no new `eslint-disable` comments**; Prettier (`singleQuote`, `printWidth: 100`, `trailingComma: all`) with `format:check` clean; coverage gate 80% (lines, functions, branches, statements) on both sides (project's existing pytest coverage gate).
- Hand-written frontend API types are forbidden: every request/response type comes from `frontend/src/api/schema.d.ts`, generated from `frontend/openapi.json`, which is itself generated from the FastAPI app (`uv run python scripts/export_openapi.py`, then `npm run gen:api` in `frontend/`). Both generated files are committed. `tests/unit/api/test_openapi_snapshot.py::test_the_committed_snapshot_matches_the_app` fails the build if they drift.
- All UI text is English; every Japanese text run carries `lang="ja"`; the HTML root is `lang="en"`.
- `expected_last_review` is an opaque token: send it back exactly as received, never parse or reformat it (unchanged by this plan; typed/choice modes reuse the existing `AnswerRequest` shape).
- Live regions announce static text only (nothing that changes every second); the review screen has exactly one persistent status region (existing; extend its cases, do not add a second region).
- Port `8192` for the API (never `8000`).
- Commits: conventional commits, stage explicit paths only (never `git add .` / `-A`), trailer as its own paragraph: `git commit -m "<subject>" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"`. Never stage `.gitignore` (the repo-root one is user-owned), `.python-version`, `.superpowers/`. Never merge to `main`; James merges.
- Windows / Git Bash quirks: run `unset VIRTUAL_ENV` before `uv`; quote paths (`Bunshō` contains ō); set `PYTHONIOENCODING=utf-8` when printing Japanese; re-read any file containing Japanese text after writing it.
- Verification commands. Backend (repo root): `uv run ruff format --check . && uv run ruff check . && uv run mypy && uv run bandit -c pyproject.toml -r src -q && uv run pytest -q`. Frontend (`frontend/`): `npm run format:check && npm run lint && npm run build && npm run coverage`.

## Refinements to the spec

Decisions taken while turning the spec into tasks; the spec's body does not yet reflect these.

1. **`ContentRepository.get_item(item_type, item_id)`** is a new thin dispatcher (to `get_kana`/`get_kanji`/`get_vocab`), added so the orchestrator's existing `_load_item` and the new `distractors` service share one lookup instead of duplicating the `match` block.
2. **`Item = Kana | Kanji | Vocab`** moves from `orchestration/review_session.py` to `models/content.py` (a type alias, not behavior), so the new `services/answer_key.py` and `services/distractors.py` can use it without a services-importing-orchestration layering violation. The orchestrator imports it from `models/content` instead of defining it locally.
3. **A card downgrades to `flip` if its content cannot support the configured mode** — for example a kanji with no meanings on file, so `kanji_to_meaning`'s accepted-answers list would be empty. `_answer_fields` (Task 4) checks for this and falls back rather than shipping an unusable typed/choice card. This is the mechanism behind the spec's "missing `accepted_answers`/`choices` → render as `FlipMode`" error handling, implemented server-side instead of as a client-side fallback, since the server already knows the content.
4. **`ReviewModeProps` gains `onContinue(): void`.** The spec's data-flow section undersold this: typed and multiple-choice need to tell `ReviewPage` "the learner is ready for the next card" *after* grading (which happens immediately on submit/pick) but the held feedback is showing. `FlipMode` receives the prop like the other two (one shared contract) but never calls it — grading already advances immediately there.
5. **`TypedMode` needs no custom keyboard hook.** A native `<form onSubmit>` handles Enter-to-submit, and a focused "Continue" button handles Enter/Space natively — Space must not be reinterpreted for a mode with a free-text input (digit keys must reach the input as text, not as shortcuts). `ChoiceMode` (no text input) does get a small `useChoiceShortcuts` hook for digit-key picking, reusing `useReviewShortcuts`'s exported `isForReview` guard.
6. **The "first accepted answer" is the multiple-choice display text and the correct option.** `accepted_answers_for()` returns its list most-preferred-first specifically so `distractors.choices_for()` and the frontend can both treat index 0 as "the" canonical text without a second field.
7. **`accepted_answers` is populated in `multiple_choice` mode too, holding just the correct answer (`[answers[0]]`), not only in `typed` mode as the spec's data-model section says.** `choices` is a *shuffled* list with no separate "which index is correct" marker — the client needs something to compare a pick against, and `accepted_answers[0]` is that comparison target for both modes. This is the only correction to the spec's data model; everything else in that section stands.

## File Structure

Backend, new: `src/bunsho/services/answer_key.py`, `src/bunsho/services/distractors.py`, `tests/unit/services/test_answer_key.py`, `tests/unit/services/test_distractors.py`.
Backend, modified: `src/bunsho/models/content.py` (`Item` alias), `src/bunsho/models/review_settings.py` (`ReviewModeName`, three settings fields), `src/bunsho/models/review_session.py` (`CardView` fields), `src/bunsho/services/content_repository.py` (`get_item`), `src/bunsho/orchestration/review_session.py` (`_answer_fields`, `_view`, `_due_view`, `next_card`), `frontend/openapi.json`; tests: `tests/unit/models/test_review_settings.py`, `tests/unit/models/test_review_session.py` (if present; otherwise a new file — checked in Task 4), `tests/unit/services/test_content_repository.py`, `tests/unit/orchestration/test_review_session.py`.

Frontend, new: `frontend/src/features/review/matchAnswer.ts`, `matchAnswer.test.ts`, `TypedMode.tsx`, `TypedMode.test.tsx`, `useChoiceShortcuts.ts`, `ChoiceMode.tsx`, `ChoiceMode.test.tsx`.
Frontend, modified: `frontend/src/api/schema.d.ts` (generated), `frontend/src/api/endpoints.ts`, `frontend/src/test/fixtures.ts`, `frontend/src/features/review/reviewMode.ts`, `useReviewShortcuts.ts` (export `isForReview`), `FlipMode.tsx` (accept the unused `onContinue` prop), `ReviewPage.tsx`, `ReviewPage.test.tsx`, `frontend/src/features/settings/settingsForm.ts`, `settingsForm.test.ts`, `SettingsPage.tsx`, `SettingsPage.test.tsx`; and `README.md`, `CHANGELOG.md`, `TODO.md` plus this plan's own "Implementation notes".

---

## Task 0: Branch and draft PR

**Files:** none.

- [ ] **Step 1: Confirm the docs PR (spec and this plan) is merged**

Run: `gh pr list --state all --limit 3`
Expected: the `docs/plan-typed-mc-review-modes` PR shows `MERGED`. If it does not, stop and ask James (no stacked branches).

- [ ] **Step 2: Branch from a fresh main**

```bash
git checkout main && git pull
git checkout -b feat/plan-typed-mc-review-modes
```

- [ ] **Step 3: Draft PR after the first commit (Task 1)**

After Task 1's commit: `git push -u origin feat/plan-typed-mc-review-modes`, then `gh pr create --draft --title "Typed-answer and multiple-choice review modes" --body "<summary>\n\n🤖 Generated with [Claude Code](https://claude.com/claude-code)"`. CI then runs on every push.

---

## Task 1: `ReviewModeName` and the per-item-type settings

**Files:**
- Modify: `src/bunsho/models/review_settings.py`, `tests/unit/models/test_review_settings.py`

**Interfaces:**
- Consumes: `ItemType` (`bunsho.models.review`), the existing `ReviewSettings` model.
- Produces: `ReviewModeName` (`StrEnum`: `FLIP`, `TYPED`, `MULTIPLE_CHOICE`); `ReviewSettings.kana_mode`, `.kanji_mode`, `.vocab_mode` (each `ReviewModeName`, default `FLIP`); `ReviewSettings.mode_for(item_type: ItemType) -> ReviewModeName`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/unit/models/test_review_settings.py`:

```python
from bunsho.models.review_settings import NewCardPolicyName, NewLimits, ReviewModeName, ReviewSettings
```

(replace the existing `from bunsho.models.review_settings import ...` import line with the one above), then add:

```python
def test_review_modes_default_to_flip() -> None:
    settings = ReviewSettings()
    assert settings.kana_mode is ReviewModeName.FLIP
    assert settings.kanji_mode is ReviewModeName.FLIP
    assert settings.vocab_mode is ReviewModeName.FLIP


def test_review_modes_are_looked_up_by_item_type() -> None:
    settings = ReviewSettings(
        kana_mode=ReviewModeName.TYPED,
        kanji_mode=ReviewModeName.MULTIPLE_CHOICE,
        vocab_mode=ReviewModeName.FLIP,
    )
    assert [settings.mode_for(t) for t in ItemType] == [
        ReviewModeName.TYPED,
        ReviewModeName.MULTIPLE_CHOICE,
        ReviewModeName.FLIP,
    ]
```

Also add `{"kana_mode": "loud"}` to the `test_invalid_settings_are_rejected` parametrize list, and add `ItemType` to that file's imports (`from bunsho.models.review import ItemType`).

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/models/test_review_settings.py -v`
Expected: FAIL (`ReviewModeName` not defined; `ReviewSettings` has no field `kana_mode`).

- [ ] **Step 3: Write the implementation**

In `src/bunsho/models/review_settings.py`, add after `NewCardPolicyName`:

```python
class ReviewModeName(StrEnum):
    """How a card is answered."""

    FLIP = "flip"
    TYPED = "typed"
    MULTIPLE_CHOICE = "multiple_choice"
```

In `ReviewSettings`, add the three fields after `mastery_threshold` and a lookup method after `levels()`:

```python
    kana_mode: ReviewModeName = ReviewModeName.FLIP
    kanji_mode: ReviewModeName = ReviewModeName.FLIP
    vocab_mode: ReviewModeName = ReviewModeName.FLIP

    def mode_for(self, item_type: ItemType) -> ReviewModeName:
        """Return the configured review mode for ``item_type``."""
        match item_type:
            case ItemType.KANA:
                return self.kana_mode
            case ItemType.KANJI:
                return self.kanji_mode
            case ItemType.VOCAB:
                return self.vocab_mode
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/models/test_review_settings.py -v`
Expected: PASS.

- [ ] **Step 5: Run the backend gate**

Run: `uv run ruff format --check . && uv run ruff check . && uv run mypy && uv run bandit -c pyproject.toml -r src -q && uv run pytest -q`
Expected: all green (a couple of other test files may now fail if they construct a `ReviewSettings` literal by hand elsewhere without `model_validate`'s defaults — Pydantic defaults handle that automatically, so this should not happen; if it does, fix the fixture, not the model).

- [ ] **Step 6: Commit**

```bash
git add src/bunsho/models/review_settings.py tests/unit/models/test_review_settings.py
git commit -m "feat: add ReviewModeName and per-item-type review mode settings" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

Then open the draft PR (Task 0, Step 3).

---

## Task 2: `ContentRepository.get_item` and the accepted-answers builder

**Files:**
- Modify: `src/bunsho/models/content.py`, `src/bunsho/services/content_repository.py`, `src/bunsho/orchestration/review_session.py`, `tests/unit/services/test_content_repository.py`
- Create: `src/bunsho/services/answer_key.py`, `tests/unit/services/test_answer_key.py`

**Interfaces:**
- Consumes: `Kana`, `Kanji`, `Vocab` (`bunsho.models.content`); `CardDirection` (`bunsho.models.review`).
- Produces: `Item` type alias (moved to `bunsho.models.content`); `ContentRepository.get_item(item_type: ItemType, item_id: str) -> Item | None`; `accepted_answers_for(direction: CardDirection, item: Item) -> list[str]` (`bunsho.services.answer_key`), most-preferred answer first, `[]` when the content cannot support a typed/choice answer for that direction.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/services/test_answer_key.py`:

```python
"""Tests for the accepted-answers builder that backs typed-answer and multiple-choice modes."""

from bunsho.models.review import CardDirection
from tests.base import make_kana, make_kanji, make_vocab
from bunsho.services.answer_key import accepted_answers_for


def test_glyph_to_sound_accepts_the_romaji_and_its_known_variants() -> None:
    shi = make_kana("し", "shi")
    assert accepted_answers_for(CardDirection.GLYPH_TO_SOUND, shi) == ["shi", "si"]


def test_glyph_to_sound_with_no_known_variant_accepts_only_the_romaji() -> None:
    a = make_kana("あ", "a")
    assert accepted_answers_for(CardDirection.GLYPH_TO_SOUND, a) == ["a"]


def test_sound_to_glyph_accepts_ji_and_zi_dakuten_kana_interchangeably() -> None:
    ji = make_kana("じ", "ji")
    ji_answers = accepted_answers_for(CardDirection.SOUND_TO_GLYPH, ji)
    assert ji_answers[0] == "じ"
    assert "ぢ" in ji_answers

    chi_dakuten = make_kana("ぢ", "ji")
    assert accepted_answers_for(CardDirection.SOUND_TO_GLYPH, chi_dakuten)[0] == "ぢ"
    assert "じ" in accepted_answers_for(CardDirection.SOUND_TO_GLYPH, chi_dakuten)


def test_sound_to_glyph_with_no_homophone_accepts_only_its_own_glyph() -> None:
    a = make_kana("あ", "a")
    assert accepted_answers_for(CardDirection.SOUND_TO_GLYPH, a) == ["あ"]


def test_kanji_to_meaning_accepts_every_listed_meaning() -> None:
    day = make_kanji("日")  # meanings=("day",) by default
    assert accepted_answers_for(CardDirection.KANJI_TO_MEANING, day) == ["day"]


def test_kanji_to_meaning_is_empty_when_the_kanji_has_no_meanings_on_file() -> None:
    bare = make_kanji("日").model_copy(update={"meanings": ()})
    assert accepted_answers_for(CardDirection.KANJI_TO_MEANING, bare) == []


def test_kanji_to_reading_accepts_on_then_kun_readings() -> None:
    day = make_kanji("日")  # on_readings=("ニチ",), kun_readings=("ひ",) by default
    assert accepted_answers_for(CardDirection.KANJI_TO_READING, day) == ["ニチ", "ひ"]


def test_meaning_to_kanji_accepts_the_character() -> None:
    day = make_kanji("日")
    assert accepted_answers_for(CardDirection.MEANING_TO_KANJI, day) == ["日"]


def test_vocab_recognition_accepts_the_meaning_and_the_additional_definitions() -> None:
    with_extra = make_vocab().model_copy(update={"additional_definitions": "to live on"})
    assert accepted_answers_for(CardDirection.RECOGNITION, with_extra) == [
        "test meaning",
        "to live on",
    ]


def test_vocab_recognition_without_additional_definitions_accepts_only_the_meaning() -> None:
    plain = make_vocab()
    assert accepted_answers_for(CardDirection.RECOGNITION, plain) == ["test meaning"]


def test_vocab_recall_accepts_the_expression() -> None:
    word = make_vocab("食べる", "たべる")
    assert accepted_answers_for(CardDirection.RECALL, word) == ["食べる"]
```

Add to `tests/unit/services/test_content_repository.py` (find the class or module testing `get_kanji`/`get_vocab`/`get_kana` and add alongside):

```python
def test_get_item_dispatches_by_item_type(tmp_path: Path) -> None:
    kana, kanji, vocab = make_kana(), make_kanji(), make_vocab()
    repo = write_content(tmp_path / "content.db", kana=[kana], kanji=[kanji], vocab=[vocab])
    assert repo.get_item(ItemType.KANA, kana.id) == kana
    assert repo.get_item(ItemType.KANJI, kanji.id) == kanji
    assert repo.get_item(ItemType.VOCAB, vocab.id) == vocab
    assert repo.get_item(ItemType.VOCAB, "missing") is None
```

Check the top of `tests/unit/services/test_content_repository.py` for its existing imports (`Path`, `ItemType`, `make_kana`/`make_kanji`/`make_vocab`, `write_content`) and add whichever of these it does not already import.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/services/test_answer_key.py tests/unit/services/test_content_repository.py -v`
Expected: FAIL (`ModuleNotFoundError: bunsho.services.answer_key`; `AttributeError: get_item`).

- [ ] **Step 3: Write the implementation**

In `src/bunsho/models/content.py`, add after the `Vocab` class (before `ImportedDeck`):

```python
Item = Kana | Kanji | Vocab
"""A single piece of study content: one kana character, kanji or vocabulary item."""
```

In `src/bunsho/services/content_repository.py`, add after `get_kana`:

```python
    def get_item(self, item_type: ItemType, item_id: str) -> Item | None:
        """Return the item with this stable ID, dispatching on its type."""
        match item_type:
            case ItemType.KANA:
                return self.get_kana(item_id)
            case ItemType.KANJI:
                return self.get_kanji(item_id)
            case ItemType.VOCAB:
                return self.get_vocab(item_id)
```

Add `Item` to that file's import from `bunsho.models.content` (alongside `Kana`, `Kanji`, `Vocab`).

In `src/bunsho/orchestration/review_session.py`:
- Remove the local `Item = Kana | Kanji | Vocab` line.
- Add `Item` to the `from bunsho.models.content import Kana, Kanji, Vocab` line, making it `from bunsho.models.content import Item, Kana, Kanji, Vocab`.
- Replace `_load_item`'s body with a call to the new dispatcher:

```python
def _load_item(repo: ContentRepository, key: CardKey) -> Item | None:
    return repo.get_item(key.item_type, key.item_id)
```

Create `src/bunsho/services/answer_key.py`:

```python
"""Accepted-answer strings for typed-answer and multiple-choice review modes.

Pure and synchronous: every function here touches only the item it is given, never the
database, so callers never need ``asyncio.to_thread`` for anything in this module.
"""

from __future__ import annotations

from bunsho.models.content import Item, Kana, Kanji
from bunsho.models.review import CardDirection

ROMAJI_VARIANTS: dict[str, tuple[str, ...]] = {
    "shi": ("si",),
    "chi": ("ti",),
    "tsu": ("tu",),
    "fu": ("hu",),
    "ji": ("zi",),
    "zu": ("du",),
    "sha": ("sya",),
    "shu": ("syu",),
    "sho": ("syo",),
    "cha": ("tya",),
    "chu": ("tyu",),
    "cho": ("tyo",),
    "ja": ("zya",),
    "ju": ("zyu",),
    "jo": ("zyo",),
}
"""Hepburn romaji (as stored on ``Kana.romaji``) to its other common romanization spellings."""

_HOMOPHONE_KANA: dict[str, tuple[str, ...]] = {
    "じ": ("ぢ",),
    "ぢ": ("じ",),
    "ず": ("づ",),
    "づ": ("ず",),
}
"""Kana pairs that are phonetically identical in modern Japanese, so either glyph is accepted
for the other's romaji (``sound_to_glyph``)."""


def accepted_answers_for(direction: CardDirection, item: Item) -> list[str]:
    """Every string that counts as a correct typed answer for ``direction``.

    The most-preferred answer is first (also used as the correct multiple-choice option's
    display text). An empty list means this direction has nothing usable to grade against
    (for example a kanji with no meanings on file); callers should fall back to flip mode.

    Args:
        direction: Which way the card asks its question.
        item: The kana, kanji or vocabulary item the card is about.

    Returns:
        Accepted answer strings, most-preferred first.
    """
    if isinstance(item, Kana):
        return _kana_answers(direction, item)
    if isinstance(item, Kanji):
        return _kanji_answers(direction, item)
    return _vocab_answers(direction, item)


def _kana_answers(direction: CardDirection, kana: Kana) -> list[str]:
    if direction is CardDirection.GLYPH_TO_SOUND:
        return [kana.romaji, *ROMAJI_VARIANTS.get(kana.romaji, ())]
    return [kana.char, *_HOMOPHONE_KANA.get(kana.char, ())]


def _kanji_answers(direction: CardDirection, kanji: Kanji) -> list[str]:
    if direction is CardDirection.KANJI_TO_MEANING:
        return list(kanji.meanings)
    if direction is CardDirection.KANJI_TO_READING:
        return [*kanji.on_readings, *kanji.kun_readings]
    return [kanji.char]  # meaning_to_kanji


def _vocab_answers(direction: CardDirection, vocab: object) -> list[str]:
    # `vocab` is a `Vocab`; typed as `object` here only to keep the import list to Kana/Kanji
    # above (Vocab is the only remaining branch of `Item`, so mypy narrows it via elimination
    # once this function's caller has ruled out Kana and Kanji).
    from bunsho.models.content import Vocab

    assert isinstance(vocab, Vocab)
    if direction is CardDirection.RECOGNITION:
        answers = [vocab.meaning]
        if vocab.additional_definitions != "":
            answers.append(vocab.additional_definitions)
        return answers
    return [vocab.expression]  # recall
```

Reconsider the `_vocab_answers` workaround above: it exists only to avoid importing `Vocab` at module scope while every other branch already imports `Kana`/`Kanji` there. There is no real reason to avoid that import — **do not use the `object`/`assert isinstance` workaround**; instead import `Vocab` at the top alongside `Kana` and `Kanji` and type `_vocab_answers(direction: CardDirection, vocab: Vocab) -> list[str]` directly, matching `_kana_answers` and `_kanji_answers`. Write it that way from the start.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/services/test_answer_key.py tests/unit/services/test_content_repository.py -v`
Expected: PASS.

- [ ] **Step 5: Run the backend gate**

Run: `uv run ruff format --check . && uv run ruff check . && uv run mypy && uv run bandit -c pyproject.toml -r src -q && uv run pytest -q`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add src/bunsho/models/content.py src/bunsho/services/content_repository.py src/bunsho/services/answer_key.py src/bunsho/orchestration/review_session.py tests/unit/services/test_answer_key.py tests/unit/services/test_content_repository.py
git commit -m "feat: add ContentRepository.get_item and the accepted-answers builder" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Task 3: Multiple-choice distractor selection

**Files:**
- Create: `src/bunsho/services/distractors.py`, `tests/unit/services/test_distractors.py`

**Interfaces:**
- Consumes: `Item`, `Kana` (`bunsho.models.content`); `CardKey`, `ItemType` (`bunsho.models.review`); `ReviewSettings` (`bunsho.models.review_settings`); `ContentCatalog`, `ContentRepository` (Task 2's `get_item`); `accepted_answers_for` (Task 2).
- Produces: `choices_for(key: CardKey, item: Item, settings: ReviewSettings, repo: ContentRepository, rng: random.Random | None = None) -> list[str]` — 1 to 4 shuffled strings, the correct answer plus up to 3 distinct distractors. Blocking (SQLite via `ContentCatalog`/`ContentRepository`); callers use `asyncio.to_thread`.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/services/test_distractors.py`:

```python
"""Tests for multiple-choice distractor selection."""

import random
from pathlib import Path

from bunsho.models.content import JlptLevel
from bunsho.models.review import CardDirection, CardKey, ItemType
from bunsho.models.review_settings import ReviewSettings
from bunsho.services.distractors import choices_for
from tests.base import make_kanji, write_content

MEANING = CardDirection.KANJI_TO_MEANING


def _repo(tmp_path: Path, kanji: list) -> object:
    return write_content(tmp_path / "content.db", kanji=kanji)


def test_choices_include_the_correct_answer_and_up_to_three_distractors(tmp_path: Path) -> None:
    kanji = [
        make_kanji("日").model_copy(update={"meanings": ("day",)}),
        make_kanji("月").model_copy(update={"meanings": ("moon",)}),
        make_kanji("火").model_copy(update={"meanings": ("fire",)}),
        make_kanji("水").model_copy(update={"meanings": ("water",)}),
    ]
    repo = _repo(tmp_path, kanji)
    key = CardKey(kanji[0].id, MEANING)
    choices = choices_for(key, kanji[0], ReviewSettings(), repo, rng=random.Random(0))
    assert len(choices) == 4
    assert "day" in choices
    assert set(choices) == {"day", "moon", "fire", "water"}


def test_choices_degrade_gracefully_when_the_pool_is_too_small(tmp_path: Path) -> None:
    kanji = [
        make_kanji("日").model_copy(update={"meanings": ("day",)}),
        make_kanji("月").model_copy(update={"meanings": ("moon",)}),
    ]
    repo = _repo(tmp_path, kanji)
    key = CardKey(kanji[0].id, MEANING)
    choices = choices_for(key, kanji[0], ReviewSettings(), repo, rng=random.Random(0))
    assert choices == ["day", "moon"] or choices == ["moon", "day"]


def test_choices_never_include_the_target_item_itself(tmp_path: Path) -> None:
    kanji = [make_kanji("日").model_copy(update={"meanings": ("day",)})]
    repo = _repo(tmp_path, kanji)
    key = CardKey(kanji[0].id, MEANING)
    assert choices_for(key, kanji[0], ReviewSettings(), repo, rng=random.Random(0)) == ["day"]


def test_choices_never_include_a_duplicate_of_the_correct_text(tmp_path: Path) -> None:
    kanji = [
        make_kanji("日").model_copy(update={"meanings": ("day",)}),
        make_kanji("陽").model_copy(update={"meanings": ("day",), "level": JlptLevel.N5}),
        make_kanji("月").model_copy(update={"meanings": ("moon",)}),
    ]
    repo = _repo(tmp_path, kanji)
    key = CardKey(kanji[0].id, MEANING)
    choices = choices_for(key, kanji[0], ReviewSettings(), repo, rng=random.Random(0))
    assert choices.count("day") == 1


def test_choices_prefer_the_same_level_before_widening(tmp_path: Path) -> None:
    kanji = [
        make_kanji("日", level=JlptLevel.N5).model_copy(update={"meanings": ("day",)}),
        make_kanji("愛", level=JlptLevel.N3).model_copy(update={"meanings": ("love",)}),
        *[
            make_kanji(char, level=JlptLevel.N5).model_copy(update={"meanings": (word,)})
            for char, word in [("月", "moon"), ("火", "fire"), ("水", "water")]
        ],
    ]
    repo = _repo(tmp_path, kanji)
    key = CardKey(kanji[0].id, MEANING)
    choices = choices_for(key, kanji[0], ReviewSettings(), repo, rng=random.Random(0))
    assert "love" not in choices  # the N3 item loses to three same-level N5 candidates
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/services/test_distractors.py -v`
Expected: FAIL (`ModuleNotFoundError: bunsho.services.distractors`).

- [ ] **Step 3: Write the implementation**

Create `src/bunsho/services/distractors.py`:

```python
"""Multiple-choice distractor selection, sourced from ``content.db``."""

from __future__ import annotations

import random
from collections.abc import Sequence

from bunsho.models.content import Item, JlptLevel, Kana
from bunsho.models.review import CardKey, CatalogEntry
from bunsho.models.review_settings import ReviewSettings
from bunsho.services.answer_key import accepted_answers_for
from bunsho.services.content_catalog import ContentCatalog
from bunsho.services.content_repository import ContentRepository

_WANTED = 3
"""How many distractors to look for, alongside the correct answer."""


def _level_of(item: Item) -> JlptLevel | None:
    return None if isinstance(item, Kana) else item.level


def _ranked_pool(
    entries: Sequence[CatalogEntry],
    exclude_item_id: str,
    level: JlptLevel | None,
    active: frozenset[JlptLevel],
) -> list[CatalogEntry]:
    """``entries`` split into same-level, other-active-level and everything-else bands.

    Kana (``level is None``) always land in the same-level band together, since kana are
    never leveled; that mirrors how the rest of the app treats kana as one pool.
    """
    same_level: list[CatalogEntry] = []
    active_level: list[CatalogEntry] = []
    rest: list[CatalogEntry] = []
    for entry in entries:
        if entry.item_id == exclude_item_id:
            continue
        if entry.level == level:
            same_level.append(entry)
        elif entry.level is None or entry.level in active:
            active_level.append(entry)
        else:
            rest.append(entry)
    return same_level + active_level + rest


def choices_for(
    key: CardKey,
    item: Item,
    settings: ReviewSettings,
    repo: ContentRepository,
    rng: random.Random | None = None,
) -> list[str]:
    """Shuffled multiple-choice options for ``key``: the correct answer plus up to 3 distractors.

    Distractors are other content of the same item type, preferring the same JLPT level, then
    any level in ``settings.active_levels``, then anything else. Kana have no level and are
    treated as one pool. A thin content pool is not an error: the result may have fewer than 4
    entries (a minimum of 1, the correct answer itself).

    Blocking (SQLite via ``ContentCatalog``/``ContentRepository``); call it through
    ``asyncio.to_thread`` from async code.

    Args:
        key: The card being answered.
        item: The card's content item (already loaded).
        settings: The current review settings (for the active-levels fallback).
        repo: The content repository to sample distractors from.
        rng: Source of randomness (a fixed seed makes tests deterministic).

    Returns:
        The correct answer and its distractors, shuffled together.
    """
    rng = rng or random.Random()
    answers = accepted_answers_for(key.direction, item)
    correct = answers[0]
    catalog = ContentCatalog(repo)
    entries = catalog.entries(key.item_type)
    pool = _ranked_pool(entries, key.item_id, _level_of(item), settings.levels())

    seen = {correct}
    distractors: list[str] = []
    for entry in pool:
        if len(distractors) >= _WANTED:
            break
        candidate = repo.get_item(entry.item_type, entry.item_id)
        if candidate is None:
            continue
        candidate_answers = accepted_answers_for(key.direction, candidate)
        if not candidate_answers or candidate_answers[0] in seen:
            continue
        seen.add(candidate_answers[0])
        distractors.append(candidate_answers[0])

    choices = [correct, *distractors]
    rng.shuffle(choices)
    return choices
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/services/test_distractors.py -v`
Expected: PASS.

- [ ] **Step 5: Run the backend gate**

Run: `uv run ruff format --check . && uv run ruff check . && uv run mypy && uv run bandit -c pyproject.toml -r src -q && uv run pytest -q`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add src/bunsho/services/distractors.py tests/unit/services/test_distractors.py
git commit -m "feat: add multiple-choice distractor selection" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Task 4: Wire `mode`, `accepted_answers` and `choices` into `CardView`

**Files:**
- Modify: `src/bunsho/models/review_session.py`, `src/bunsho/orchestration/review_session.py`, `tests/unit/orchestration/test_review_session.py`
- Regenerate: `frontend/openapi.json`

**Interfaces:**
- Consumes: `ReviewModeName` (Task 1), `accepted_answers_for` (Task 2), `choices_for` (Task 3).
- Produces: `CardView.mode: ReviewModeName`, `.accepted_answers: list[str] | None`, `.choices: list[str] | None`; the orchestrator's `_answer_fields(key, item, settings, repo) -> tuple[ReviewModeName, list[str] | None, list[str] | None]`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/unit/orchestration/test_review_session.py` (near the other `next_card`-based tests; it already imports `CardKey`, `Grade`, `ItemType`, `SchedState`, `ReviewSettings`, `make_kana`, `make_kanji`, `make_vocab`, `build_review_stack`):

```python
from bunsho.models.review_settings import ReviewModeName


def test_a_flip_card_ships_no_answer_data(tmp_path: Path) -> None:
    async def scenario(db: ProgressDatabase) -> None:
        stack = build_review_stack(tmp_path, db, vocab=[A, B])
        card = await next_card(stack)
        assert card.mode is ReviewModeName.FLIP
        assert card.accepted_answers is None
        assert card.choices is None

    run_with_database(tmp_path, scenario)


def test_a_typed_card_ships_accepted_answers_and_no_choices(tmp_path: Path) -> None:
    async def scenario(db: ProgressDatabase) -> None:
        stack = build_review_stack(tmp_path, db, vocab=[A, B])
        await stack.settings.save(ReviewSettings(vocab_mode=ReviewModeName.TYPED))
        card = await next_card(stack)
        assert card.mode is ReviewModeName.TYPED
        assert card.accepted_answers == ["test meaning"]
        assert card.choices is None

    run_with_database(tmp_path, scenario)


def test_a_multiple_choice_card_ships_choices_and_the_correct_answer(tmp_path: Path) -> None:
    async def scenario(db: ProgressDatabase) -> None:
        stack = build_review_stack(tmp_path, db, vocab=[A, B])
        await stack.settings.save(ReviewSettings(vocab_mode=ReviewModeName.MULTIPLE_CHOICE))
        card = await next_card(stack)
        assert card.mode is ReviewModeName.MULTIPLE_CHOICE
        assert card.accepted_answers == ["test meaning"]
        assert card.choices is not None
        assert "test meaning" in card.choices

    run_with_database(tmp_path, scenario)


def test_a_card_downgrades_to_flip_when_its_content_has_no_usable_answer(tmp_path: Path) -> None:
    async def scenario(db: ProgressDatabase) -> None:
        bare = make_kanji("日").model_copy(update={"meanings": ()})
        stack = build_review_stack(tmp_path, db, kanji=[bare])
        await stack.settings.save(ReviewSettings(kanji_mode=ReviewModeName.TYPED))
        card = await next_card(stack)
        if card.direction.value == "kanji_to_meaning":
            assert card.mode is ReviewModeName.FLIP
            assert card.accepted_answers is None

    run_with_database(tmp_path, scenario)


def test_a_due_cards_mode_is_resolved_too(tmp_path: Path) -> None:
    async def scenario(db: ProgressDatabase) -> None:
        stack = build_review_stack(tmp_path, db, vocab=[A, B])
        await answer(stack, await next_card(stack))
        await stack.settings.save(ReviewSettings(vocab_mode=ReviewModeName.TYPED))
        stack.clock.advance(minutes=11)
        due = await next_card(stack)
        assert due.mode is ReviewModeName.TYPED
        assert due.accepted_answers is not None

    run_with_database(tmp_path, scenario)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/orchestration/test_review_session.py -v`
Expected: FAIL (`AttributeError: 'CardView' object has no attribute 'mode'`).

- [ ] **Step 3: Write the implementation**

In `src/bunsho/models/review_session.py`, add the import and the three fields to `CardView`:

```python
from bunsho.models.review_settings import ReviewModeName
```

(add alongside the existing imports), then in `CardView`:

```python
class CardView(BaseModel):
    """A card ready to show: identity, scheduling facts and the content item.

    Exactly one of ``kana``, ``kanji`` and ``vocab`` is set, matching ``item_type``. Send
    ``expected_last_review`` back exactly as received when answering. ``accepted_answers`` holds
    every correct typed answer when ``mode`` is ``typed``, or just the one correct answer (for
    checking a pick against) when ``mode`` is ``multiple_choice``; ``choices`` is set only when
    ``mode`` is ``multiple_choice``. A card whose content cannot support the settings' configured
    mode is served as ``flip`` instead, with both left unset.
    """

    item_id: str
    direction: CardDirection
    item_type: ItemType
    is_new: bool
    state: SchedState
    expected_last_review: AwareDatetime | None = Field(
        description=(
            "An opaque token (null for a new card): send it back exactly as received, byte for "
            "byte, in `POST /reviews/answer`. Never parse or reformat it; a client that "
            "re-serialises the timestamp can lose microseconds and get a permanent 409."
        )
    )
    intervals: GradeIntervals
    mode: ReviewModeName
    accepted_answers: list[str] | None = None
    choices: list[str] | None = None
    kana: Kana | None = None
    kanji: Kanji | None = None
    vocab: Vocab | None = None
```

In `src/bunsho/orchestration/review_session.py`:

Add imports:

```python
from bunsho.models.review_settings import ReviewModeName, ReviewSettings
from bunsho.services.answer_key import accepted_answers_for
from bunsho.services.distractors import choices_for
```

(the `ReviewSettings` import already exists — extend that line rather than duplicating it).

Add a new function after `_seconds_until` and before `_view`:

```python
async def _answer_fields(
    key: CardKey, item: Item, settings: ReviewSettings, repo: ContentRepository
) -> tuple[ReviewModeName, list[str] | None, list[str] | None]:
    """Resolve the review mode and its supporting data for ``key``.

    Downgrades to ``flip`` when the configured mode has nothing to grade against (for example
    a kanji with no meanings on file), so a card never ships broken. In ``multiple_choice`` mode,
    ``accepted_answers`` still carries the single correct answer (``choices`` is shuffled and
    otherwise gives the client nothing to check a pick against).
    """
    mode = settings.mode_for(key.item_type)
    if mode is ReviewModeName.FLIP:
        return ReviewModeName.FLIP, None, None
    answers = accepted_answers_for(key.direction, item)
    if not answers:
        return ReviewModeName.FLIP, None, None
    if mode is ReviewModeName.TYPED:
        return ReviewModeName.TYPED, answers, None
    choices = await asyncio.to_thread(choices_for, key, item, settings, repo)
    return ReviewModeName.MULTIPLE_CHOICE, [answers[0]], choices
```

Change `_view`'s signature to take the resolved fields instead of computing nothing:

```python
def _view(
    key: CardKey,
    schedule: CardSchedule,
    item: Item,
    scheduler: Scheduler,
    now: datetime,
    mode: ReviewModeName,
    accepted_answers: list[str] | None,
    choices: list[str] | None,
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
        mode=mode,
        accepted_answers=accepted_answers,
        choices=choices,
        kana=item if isinstance(item, Kana) else None,
        kanji=item if isinstance(item, Kanji) else None,
        vocab=item if isinstance(item, Vocab) else None,
    )
```

Update `_due_view` to accept `settings` and resolve the fields before calling `_view`:

```python
    async def _due_view(
        self, now: datetime, repo: ContentRepository, scheduler: Scheduler, settings: ReviewSettings
    ) -> CardView | None:
        for stored in await self._progress.due_cards(now, _ORPHAN_SCAN):
            item = await asyncio.to_thread(_load_item, repo, stored.key)
            if item is not None:
                mode, answers, choices = await _answer_fields(stored.key, item, settings, repo)
                return _view(
                    stored.key, stored.schedule, item, scheduler, now, mode, answers, choices
                )
            self._logger.warning(
                "review_card_orphaned item=%s direction=%s",
                stored.key.item_id,
                stored.key.direction.value,
            )
        return None
```

Update `next_card` (both the `_due_view` call and the new-card branch):

```python
        plan = await self._plan(moment, repo, settings)
        card = await self._due_view(moment, repo, scheduler, settings)
        if card is None:
            key = plan.pick_new()
            item = None if key is None else await asyncio.to_thread(_load_item, repo, key)
            if key is not None and item is not None:
                mode, answers, choices = await _answer_fields(key, item, settings, repo)
                card = _view(
                    key, scheduler.initial(moment), item, scheduler, moment, mode, answers, choices
                )
        next_due_at = None if card is not None else await self._progress.next_due_after(moment)
        return NextCard(card=card, next_due_at=next_due_at, counts=plan.counts)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/orchestration/test_review_session.py -v`
Expected: PASS.

- [ ] **Step 5: Regenerate the OpenAPI snapshot and check for drift**

```bash
uv run python scripts/export_openapi.py
uv run pytest tests/unit/api/test_openapi_snapshot.py -v
```

Expected: PASS. Do not hand-edit `frontend/openapi.json`.

- [ ] **Step 6: Run the backend gate**

Run: `uv run ruff format --check . && uv run ruff check . && uv run mypy && uv run bandit -c pyproject.toml -r src -q && uv run pytest -q`
Expected: all green. This is the last backend task — if anything elsewhere in the suite constructed a `CardView` by hand without the new required `mode` field (grep for `CardView(` outside `review_session.py`/`_view`), fix it here.

- [ ] **Step 7: Commit**

```bash
git add src/bunsho/models/review_session.py src/bunsho/orchestration/review_session.py tests/unit/orchestration/test_review_session.py frontend/openapi.json
git commit -m "feat: resolve review mode, accepted answers and choices onto CardView" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Task 5: Frontend types, endpoints and fixtures

**Files:**
- Regenerate: `frontend/src/api/schema.d.ts`
- Modify: `frontend/src/api/endpoints.ts`, `frontend/src/test/fixtures.ts`

**Interfaces:**
- Consumes: the regenerated schema's `CardView`, `ReviewModeName`, `ReviewSettings`, `ReviewSettingsInput` types.
- Produces: `endpoints.ts` re-exports `ReviewModeName`; `fixtures.ts`'s `makeKanaCard`/`makeKanjiCard`/`makeVocabCard` default to `mode: 'flip'`, `accepted_answers: null`, `choices: null`.

- [ ] **Step 1: Regenerate the schema**

```bash
cd frontend && npm run gen:api
```

Expected: `src/api/schema.d.ts` changes to add `mode`, `accepted_answers`, `choices` to `CardView`'s schema and `kana_mode`/`kanji_mode`/`vocab_mode` plus a `ReviewModeName` enum schema to `ReviewSettings`/`ReviewSettings-Input`. Do not hand-edit this file.

- [ ] **Step 2: Run the existing frontend tests to see what the new required fields break**

Run (in `frontend/`): `npx vitest run src/api src/test src/features/review src/features/settings`
Expected: FAIL — `makeKanaCard`/`makeKanjiCard`/`makeVocabCard` build `CardView` object literals missing the now-required `mode` field, so every test using them fails a type check at build time (`npm run build` would fail too) or, if Vitest's esbuild transform does not type-check, the JSON shape is simply incomplete for later tests. Either way, fixtures need the new fields before anything downstream is written.

- [ ] **Step 3: Update the fixtures**

In `frontend/src/test/fixtures.ts`, add `mode: 'flip', accepted_answers: null, choices: null,` to each of `makeKanaCard`, `makeKanjiCard`, `makeVocabCard`'s returned object, placed after `intervals: INTERVALS,` and before `kana:`/`kanji:`/`vocab:` respectively (matching `CardView`'s field order). For example, `makeKanaCard` becomes:

```typescript
export function makeKanaCard(overrides: Partial<CardView> = {}): CardView {
  return {
    item_id: 'kana:あ',
    direction: 'glyph_to_sound',
    item_type: 'kana',
    is_new: true,
    state: 0,
    expected_last_review: null,
    intervals: INTERVALS,
    mode: 'flip',
    accepted_answers: null,
    choices: null,
    kana: { id: 'kana:あ', char: 'あ', romaji: 'a', script: 'hira', kind: 'basic', group: 'a' },
    kanji: null,
    vocab: null,
    ...overrides,
  };
}
```

Apply the same three added lines (`mode`, `accepted_answers`, `choices`) to `makeKanjiCard` and `makeVocabCard`, unchanged otherwise.

In `frontend/src/api/endpoints.ts`, add one re-export alongside the other `CardView`-adjacent types:

```typescript
export type ReviewModeName = Schemas['ReviewModeName'];
```

(place it near `export type Grade = Schemas['Grade'];`).

- [ ] **Step 4: Run the tests to verify they pass**

Run (in `frontend/`): `npx vitest run src/api src/test src/features/review src/features/settings`
Expected: PASS (no behavior changed yet — this task only makes the existing suite build against the new schema).

- [ ] **Step 5: Run the frontend gate**

Run (in `frontend/`): `npm run format:check && npm run lint && npm run build && npm run coverage`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/api/schema.d.ts frontend/src/api/endpoints.ts frontend/src/test/fixtures.ts
git commit -m "feat: generate mode/answer types and update card fixtures" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Task 6: Matching logic and `TypedMode`

**Files:**
- Create: `frontend/src/features/review/matchAnswer.ts`, `matchAnswer.test.ts`, `TypedMode.tsx`, `TypedMode.test.tsx`
- Modify: `frontend/src/features/review/reviewMode.ts`, `FlipMode.tsx`

**Interfaces:**
- Consumes: `CardView`, `Grade` (Task 5); `cardFaces`, `ReviewCard` (existing, Plan 2B-2).
- Produces: `matches(given: string, accepted: readonly string[]): boolean`; `ReviewModeProps` gains `onContinue(): void`; `<TypedMode {...ReviewModeProps} />`.

- [ ] **Step 1: Write the failing tests**

Create `frontend/src/features/review/matchAnswer.test.ts`:

```typescript
import { describe, expect, it } from 'vitest';

import { matches } from './matchAnswer';

describe('matches', () => {
  it('matches exactly, ignoring case', () => {
    expect(matches('Shi', ['shi', 'si'])).toBe(true);
    expect(matches('SHI', ['shi'])).toBe(true);
  });

  it('trims surrounding whitespace', () => {
    expect(matches('  shi  ', ['shi'])).toBe(true);
  });

  it('matches any of several accepted answers', () => {
    expect(matches('si', ['shi', 'si'])).toBe(true);
    expect(matches('zi', ['shi', 'si'])).toBe(false);
  });

  it('does not do partial or fuzzy matching', () => {
    expect(matches('shii', ['shi'])).toBe(false);
    expect(matches('sh', ['shi'])).toBe(false);
  });

  it('is false against an empty accepted list', () => {
    expect(matches('shi', [])).toBe(false);
  });
});
```

Create `frontend/src/features/review/TypedMode.test.tsx`:

```tsx
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { describe, expect, it } from 'vitest';

import { makeKanaCard } from '../../test/fixtures';
import { renderWithProviders } from '../../test/render';
import { TypedMode } from './TypedMode';

function renderMode(overrides: Partial<Parameters<typeof TypedMode>[0]> = {}) {
  const onGrade = vi.fn();
  const onReveal = vi.fn();
  const onContinue = vi.fn();
  const view = renderWithProviders(
    <TypedMode
      card={makeKanaCard({ accepted_answers: ['a'] })}
      showFurigana={false}
      pending={false}
      onReveal={onReveal}
      onGrade={onGrade}
      onContinue={onContinue}
      {...overrides}
    />,
  );
  return { onGrade, onReveal, onContinue, ...view };
}

describe('TypedMode', () => {
  it('shows the front and a focused text input', () => {
    renderMode();
    expect(screen.getByText('あ')).toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: 'Your answer' })).toHaveFocus();
  });

  it('grades Good and shows feedback when the typed answer matches', async () => {
    const user = userEvent.setup();
    const { onGrade, onReveal } = renderMode();
    await user.type(screen.getByRole('textbox', { name: 'Your answer' }), 'a{Enter}');
    expect(onGrade).toHaveBeenCalledWith(3);
    expect(onReveal).toHaveBeenCalledTimes(1);
    expect(screen.getByText(/Correct/i)).toBeInTheDocument();
  });

  it('grades Again and shows the correct answer when it does not match', async () => {
    const user = userEvent.setup();
    const { onGrade } = renderMode();
    await user.type(screen.getByRole('textbox', { name: 'Your answer' }), 'zzz{Enter}');
    expect(onGrade).toHaveBeenCalledWith(1);
    expect(screen.getByText('a')).toBeInTheDocument(); // the correct answer, shown as feedback
  });

  it('matches case-insensitively and trims whitespace', async () => {
    const user = userEvent.setup();
    const { onGrade } = renderMode();
    await user.type(screen.getByRole('textbox', { name: 'Your answer' }), '  A  {Enter}');
    expect(onGrade).toHaveBeenCalledWith(3);
  });

  it('advances focus to Continue after grading, and calls onContinue when pressed', async () => {
    const user = userEvent.setup();
    const { onContinue } = renderMode();
    await user.type(screen.getByRole('textbox', { name: 'Your answer' }), 'a{Enter}');
    const button = screen.getByRole('button', { name: 'Continue' });
    expect(button).toHaveFocus();
    await user.click(button);
    expect(onContinue).toHaveBeenCalledTimes(1);
  });

  it('ignores submission while pending', async () => {
    const user = userEvent.setup();
    const { onGrade } = renderMode({ pending: true });
    await user.type(screen.getByRole('textbox', { name: 'Your answer' }), 'a{Enter}');
    expect(onGrade).not.toHaveBeenCalled();
  });

  it('disables the input once graded, so a second submit cannot re-grade', async () => {
    const user = userEvent.setup();
    const { onGrade } = renderMode();
    await user.type(screen.getByRole('textbox', { name: 'Your answer' }), 'a{Enter}');
    expect(screen.getByRole('textbox', { name: 'Your answer' })).toBeDisabled();
    expect(onGrade).toHaveBeenCalledTimes(1);
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run (in `frontend/`): `npx vitest run src/features/review/matchAnswer.test.ts src/features/review/TypedMode.test.tsx`
Expected: FAIL (modules not found).

- [ ] **Step 3: Write the implementation**

Create `frontend/src/features/review/matchAnswer.ts`:

```typescript
function normalize(text: string): string {
  return text.trim().toLowerCase();
}

/**
 * Whether `given` matches any of `accepted`, ignoring case and surrounding whitespace. Exact
 * match only after normalization — no partial or fuzzy matching, by design (a near-miss typo
 * is simply wrong).
 */
export function matches(given: string, accepted: readonly string[]): boolean {
  const normalized = normalize(given);
  return accepted.some((answer) => normalize(answer) === normalized);
}
```

In `frontend/src/features/review/reviewMode.ts`, add the new callback:

```typescript
import type { CardView, Grade } from '../../api/endpoints';

/**
 * What a way of answering a card (flip and self-grade; typed answer; multiple choice) receives.
 * A mode shows the card, decides when it is answered, and reports a grade; the page owns
 * fetching, timing and errors.
 */
export interface ReviewModeProps {
  card: CardView;
  showFurigana: boolean;
  /** An answer is being saved (or the next card is loading): ignore input. */
  pending: boolean;
  /** The learner has seen the answer (used for the screen-reader announcement). */
  onReveal: () => void;
  onGrade: (grade: Grade) => void;
  /**
   * The learner is ready for the next card, after seeing feedback. Flip mode never calls this
   * (grading already advances immediately there) but still receives it, since all three modes
   * share one contract.
   */
  onContinue: () => void;
}
```

`FlipMode` must still type-check against `ReviewModeProps` now that it carries `onContinue`, but `FlipMode` never calls it. Leave the existing destructured parameter list in `frontend/src/features/review/FlipMode.tsx` untouched — do not add `onContinue` to it. A prop the function's parameter type declares but the destructuring pattern omits is not an unused variable (nothing was bound to a name), so this needs no rename, no disable comment and no lint exception.

Create `frontend/src/features/review/TypedMode.tsx`:

```tsx
import { Button, Stack, Text, TextInput } from '@mantine/core';
import { useRef, useState } from 'react';
import type { FormEvent } from 'react';

import { cardFaces } from './cardFaces';
import { matches } from './matchAnswer';
import { ReviewCard } from './ReviewCard';
import type { ReviewModeProps } from './reviewMode';

interface Outcome {
  correct: boolean;
  typed: string;
  correctAnswer: string;
}

/** Type the answer, then see whether it was right. Mount it with a new `key` for every card. */
export function TypedMode({ card, showFurigana, pending, onReveal, onGrade, onContinue }: ReviewModeProps) {
  const [value, setValue] = useState('');
  const [outcome, setOutcome] = useState<Outcome | null>(null);
  const continueRef = useRef<HTMLButtonElement>(null);
  const accepted = card.accepted_answers ?? [];

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (outcome !== null || pending) return;
    const correct = matches(value, accepted);
    setOutcome({ correct, typed: value, correctAnswer: accepted[0] ?? '' });
    onReveal();
    onGrade(correct ? 3 : 1);
    // Focus moves to Continue once it renders; a microtask keeps this after that render.
    queueMicrotask(() => {
      continueRef.current?.focus();
    });
  };

  const faces = cardFaces(card, { showFurigana, revealed: outcome !== null });

  return (
    <div data-review-controls>
      <ReviewCard face={faces.front} />
      <form onSubmit={submit}>
        <Stack gap="sm" mt="md">
          <TextInput
            label="Your answer"
            value={value}
            onChange={(event) => {
              setValue(event.currentTarget.value);
            }}
            disabled={outcome !== null || pending}
            autoFocus
            autoComplete="off"
          />
          {outcome === null && (
            <Button type="submit" fullWidth size="md" disabled={pending}>
              Submit
            </Button>
          )}
        </Stack>
      </form>
      {outcome !== null && (
        <Stack gap="sm" mt="md">
          <Text fw={500} c={outcome.correct ? 'teal' : 'red'}>
            {outcome.correct ? 'Correct' : 'Not quite'}
          </Text>
          {!outcome.correct && (
            <Text size="sm">
              You typed: {outcome.typed || '(nothing)'} — Correct: {outcome.correctAnswer}
            </Text>
          )}
          <Button ref={continueRef} fullWidth size="md" onClick={onContinue} disabled={pending}>
            Continue
          </Button>
        </Stack>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run (in `frontend/`): `npx vitest run src/features/review/matchAnswer.test.ts src/features/review/TypedMode.test.tsx src/features/review/FlipMode.test.tsx`
Expected: PASS (`FlipMode.test.tsx` needs its own `renderMode` helper's default props updated with an `onContinue: vi.fn()` — check it after this task's Step 2 run; if it fails only for a missing prop, add `onContinue: vi.fn()` to that test file's default props object rather than treating it as a new failure to chase down separately).

- [ ] **Step 5: Run the frontend gate**

Run (in `frontend/`): `npm run format:check && npm run lint && npm run build && npm run coverage`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/features/review/matchAnswer.ts frontend/src/features/review/matchAnswer.test.ts frontend/src/features/review/TypedMode.tsx frontend/src/features/review/TypedMode.test.tsx frontend/src/features/review/reviewMode.ts frontend/src/features/review/FlipMode.tsx frontend/src/features/review/FlipMode.test.tsx
git commit -m "feat: add typed-answer review mode" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Task 7: `ChoiceMode`

**Files:**
- Create: `frontend/src/features/review/useChoiceShortcuts.ts`, `ChoiceMode.tsx`, `ChoiceMode.test.tsx`
- Modify: `frontend/src/features/review/useReviewShortcuts.ts`

**Interfaces:**
- Consumes: `ReviewModeProps` (Task 6); `cardFaces`, `ReviewCard` (existing).
- Produces: `isForReview` exported from `useReviewShortcuts.ts`; `useChoiceShortcuts({ picked, pending, count, onPick, onContinue })`; `<ChoiceMode {...ReviewModeProps} />`.

- [ ] **Step 1: Write the failing tests**

Create `frontend/src/features/review/ChoiceMode.test.tsx`:

```tsx
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { makeKanaCard } from '../../test/fixtures';
import { renderWithProviders } from '../../test/render';
import { ChoiceMode } from './ChoiceMode';

function renderMode(overrides: Partial<Parameters<typeof ChoiceMode>[0]> = {}) {
  const onGrade = vi.fn();
  const onReveal = vi.fn();
  const onContinue = vi.fn();
  const view = renderWithProviders(
    <ChoiceMode
      card={makeKanaCard({ choices: ['a', 'i', 'u', 'e'] })}
      showFurigana={false}
      pending={false}
      onReveal={onReveal}
      onGrade={onGrade}
      onContinue={onContinue}
      {...overrides}
    />,
  );
  return { onGrade, onReveal, onContinue, ...view };
}

describe('ChoiceMode', () => {
  it('shows the front and all four options as buttons, keyed 1 to 4', () => {
    renderMode();
    expect(screen.getByText('あ')).toBeInTheDocument();
    for (const [index, label] of ['a', 'i', 'u', 'e'].entries()) {
      expect(screen.getByRole('button', { name: new RegExp(label) })).toHaveAttribute(
        'aria-keyshortcuts',
        String(index + 1),
      );
    }
  });

  it('grades Good and reveals when the correct option is picked', async () => {
    const user = userEvent.setup();
    const { onGrade, onReveal } = renderMode();
    await user.click(screen.getByRole('button', { name: /^a$/ }));
    expect(onGrade).toHaveBeenCalledWith(3);
    expect(onReveal).toHaveBeenCalledTimes(1);
    expect(screen.getByText(/Correct/i)).toBeInTheDocument();
  });

  it('grades Again when a wrong option is picked, and highlights the correct one', async () => {
    const user = userEvent.setup();
    const { onGrade } = renderMode();
    await user.click(screen.getByRole('button', { name: /^i$/ }));
    expect(onGrade).toHaveBeenCalledWith(1);
    expect(screen.getByText(/Not quite/i)).toBeInTheDocument();
  });

  it('picks with the 1-4 number keys', async () => {
    const user = userEvent.setup();
    const { onGrade } = renderMode();
    await user.keyboard('1');
    expect(onGrade).toHaveBeenCalledWith(3);
  });

  it('ignores a pick while pending, and a second pick after the first', async () => {
    const user = userEvent.setup();
    const { onGrade } = renderMode({ pending: true });
    await user.click(screen.getByRole('button', { name: /^a$/ }));
    expect(onGrade).not.toHaveBeenCalled();
  });

  it('calls onContinue on click and on Enter once an option is picked', async () => {
    const user = userEvent.setup();
    const { onContinue } = renderMode();
    await user.click(screen.getByRole('button', { name: /^a$/ }));
    await user.keyboard('{Enter}');
    expect(onContinue).toHaveBeenCalledTimes(1);
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run (in `frontend/`): `npx vitest run src/features/review/ChoiceMode.test.tsx`
Expected: FAIL (module not found).

- [ ] **Step 3: Write the implementation**

In `frontend/src/features/review/useReviewShortcuts.ts`, export the guard function instead of keeping it private:

```typescript
export function isForReview(target: EventTarget | null): boolean {
```

(only the `function` → `export function` change; the body and JSDoc above it are unchanged).

Create `frontend/src/features/review/useChoiceShortcuts.ts`:

```typescript
import { useEffect } from 'react';

import { isForReview } from './useReviewShortcuts';

interface ChoiceShortcuts {
  /** An option has already been picked (feedback is showing). */
  picked: boolean;
  pending: boolean;
  count: number;
  onPick: (index: number) => void;
  onContinue: () => void;
}

/**
 * Before a pick, digit keys 1 through `count` choose an option. After a pick, Space or Enter
 * continues. Same guards as `useReviewShortcuts`: modifier keys, auto-repeated keydowns, IME
 * composition, and input outside the review controls are all ignored, as is any input while
 * pending.
 */
export function useChoiceShortcuts({
  picked,
  pending,
  count,
  onPick,
  onContinue,
}: ChoiceShortcuts): void {
  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.repeat || event.isComposing) return;
      if (event.ctrlKey || event.metaKey || event.altKey || event.shiftKey) return;
      if (event.defaultPrevented || pending || !isForReview(event.target)) return;

      if (!picked) {
        const index = Number(event.key) - 1;
        if (Number.isInteger(index) && index >= 0 && index < count) {
          event.preventDefault();
          onPick(index);
        }
        return;
      }
      if (event.key === ' ' || event.key === 'Enter') {
        event.preventDefault();
        onContinue();
      }
    }
    window.addEventListener('keydown', onKeyDown);
    return () => {
      window.removeEventListener('keydown', onKeyDown);
    };
  }, [picked, pending, count, onPick, onContinue]);
}
```

Create `frontend/src/features/review/ChoiceMode.tsx`. `card.choices` is shuffled server-side (no index reliably marks the correct one), so correctness is decided by comparing the picked option's **text** against `card.accepted_answers?.[0]` — the single correct answer the orchestrator ships in multiple-choice mode too (Refinement 7 above):

```tsx
import { Button, SimpleGrid, Stack, Text } from '@mantine/core';
import { useEffect, useRef, useState } from 'react';

import { cardFaces } from './cardFaces';
import { ReviewCard } from './ReviewCard';
import type { ReviewModeProps } from './reviewMode';
import { useChoiceShortcuts } from './useChoiceShortcuts';

/** Pick the answer from four options. Mount it with a new `key` for every card. */
export function ChoiceMode({ card, showFurigana, pending, onReveal, onGrade, onContinue }: ReviewModeProps) {
  const [pickedIndex, setPickedIndex] = useState<number | null>(null);
  const continueRef = useRef<HTMLButtonElement>(null);
  const choices = card.choices ?? [];
  const correctChoice = card.accepted_answers?.[0] ?? choices[0];
  const picked = pickedIndex !== null;
  const chosenText = pickedIndex === null ? null : choices[pickedIndex];
  const isCorrect = picked && chosenText === correctChoice;

  const pick = (index: number) => {
    if (picked || pending) return;
    setPickedIndex(index);
    onReveal();
    onGrade(choices[index] === correctChoice ? 3 : 1);
  };

  useChoiceShortcuts({
    picked,
    pending,
    count: choices.length,
    onPick: pick,
    onContinue,
  });

  useEffect(() => {
    if (picked) continueRef.current?.focus();
  }, [picked]);

  const faces = cardFaces(card, { showFurigana, revealed: picked });

  return (
    <div data-review-controls>
      <ReviewCard face={faces.front} />
      <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="xs" mt="md">
        {choices.map((choice, index) => (
          <Button
            key={choice}
            variant={picked && choice === correctChoice ? 'filled' : 'light'}
            color={picked && index === pickedIndex && !isCorrect ? 'red' : undefined}
            disabled={picked || pending}
            aria-keyshortcuts={String(index + 1)}
            onClick={() => {
              pick(index);
            }}
          >
            {index + 1}. {choice}
          </Button>
        ))}
      </SimpleGrid>
      {picked && (
        <Stack gap="sm" mt="md">
          <Text fw={500} c={isCorrect ? 'teal' : 'red'}>
            {isCorrect ? 'Correct' : 'Not quite'}
          </Text>
          <Button ref={continueRef} fullWidth size="md" onClick={onContinue} disabled={pending}>
            Continue
          </Button>
        </Stack>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run (in `frontend/`): `npx vitest run src/features/review/ChoiceMode.test.tsx src/features/review/useReviewShortcuts.test.ts`
Expected: PASS.

- [ ] **Step 5: Run the frontend gate**

Run (in `frontend/`): `npm run format:check && npm run lint && npm run build && npm run coverage`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/features/review/useChoiceShortcuts.ts frontend/src/features/review/ChoiceMode.tsx frontend/src/features/review/ChoiceMode.test.tsx frontend/src/features/review/useReviewShortcuts.ts
git commit -m "feat: add multiple-choice review mode" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Task 8: `ReviewPage` — mode dispatch and the held-feedback transition

**Files:**
- Modify: `frontend/src/features/review/ReviewPage.tsx`, `ReviewPage.test.tsx`

**Interfaces:**
- Consumes: `TypedMode` (Task 6), `ChoiceMode` (Task 7), `FlipMode` (existing); `CardView.mode`.
- Produces: no new exports — `ReviewPage` now renders the mode matching `card.mode` and holds the just-answered card on screen until the mode calls `onContinue`.

- [ ] **Step 1: Write the failing tests**

Add to `frontend/src/features/review/ReviewPage.test.tsx` (alongside the existing flip-mode tests; check its current imports for `renderWithProviders`, `server`/`http`/`HttpResponse` from MSW, and the fixtures already in use):

```tsx
it('renders TypedMode for a typed card and ChoiceMode for a multiple-choice card', async () => {
  server.use(
    http.get('/api/v1/reviews/next', () =>
      HttpResponse.json(
        makeNextCard(makeKanaCard({ mode: 'typed', accepted_answers: ['a'] })),
      ),
    ),
  );
  renderWithProviders(<ReviewPage />);
  expect(await screen.findByRole('textbox', { name: 'Your answer' })).toBeInTheDocument();
});

it('holds the answered card on screen with feedback until Continue is pressed', async () => {
  const user = userEvent.setup();
  let call = 0;
  server.use(
    http.get('/api/v1/reviews/next', () => {
      call += 1;
      const card = call === 1 ? makeKanaCard({ mode: 'typed', accepted_answers: ['a'] }) : null;
      return HttpResponse.json(makeNextCard(card));
    }),
    http.post('/api/v1/reviews/answer', () =>
      HttpResponse.json({ due: { kana: 0, kanji: 0, vocab: 0 }, new_remaining: { kana: 0, kanji: 0, vocab: 0 } }),
    ),
  );
  renderWithProviders(<ReviewPage />);
  await user.type(await screen.findByRole('textbox', { name: 'Your answer' }), 'a{Enter}');
  // Feedback is showing; the next fetch (call 2, resolving to "nothing due") has already
  // happened in the background, but the answered card's feedback must still be on screen.
  expect(await screen.findByText(/Correct/i)).toBeInTheDocument();
  expect(screen.queryByText(/you're done/i)).not.toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: 'Continue' }));
  expect(await screen.findByText(/you're done/i)).toBeInTheDocument();
});
```

Check `ReviewPage.test.tsx`'s existing "done for now" screen wording (from `ReviewFinished.tsx`) before writing the last assertion above and match it exactly rather than guessing `/you're done/i`.

- [ ] **Step 2: Run the tests to verify they fail**

Run (in `frontend/`): `npx vitest run src/features/review/ReviewPage.test.tsx`
Expected: FAIL (`TypedMode` is not rendered — `ReviewPage` still always renders `FlipMode`).

- [ ] **Step 3: Write the implementation**

In `frontend/src/features/review/ReviewPage.tsx`:

Add the imports:

```typescript
import { ChoiceMode } from './ChoiceMode';
import { TypedMode } from './TypedMode';
```

Add a small mode lookup near the top-level helpers (after `cardKey`):

```typescript
const MODE_COMPONENTS = {
  flip: FlipMode,
  typed: TypedMode,
  multiple_choice: ChoiceMode,
} as const;
```

Inside `ReviewPage`, replace the `data`/`card`/`key` derivation and add the held-card state:

```typescript
  const data = next.data;
  const freshCard = data?.card ?? null;
  const [heldCard, setHeldCard] = useState<CardView | null>(null);
  const card = heldCard ?? freshCard;
  const key = card === null ? null : cardKey(card);
```

Update the `grade` callback to hold the card when its mode is not `flip`, and add a `continueToNext` callback:

```typescript
  const grade = useCallback(
    (value: Grade) => {
      if (freshCard === null) return;
      const duration = Math.min(Math.max(Date.now() - shownAt.current, 0), MAX_DURATION_MS);
      if (freshCard.mode !== 'flip') setHeldCard(freshCard);
      submit({
        item_id: freshCard.item_id,
        direction: freshCard.direction,
        grade: value,
        expected_last_review: freshCard.expected_last_review,
        duration_ms: duration,
      });
    },
    [freshCard, submit],
  );

  const continueToNext = useCallback(() => {
    setHeldCard(null);
  }, []);
```

`card` (used everywhere below in the existing render, including `card === null` checks, `<Stack>`'s `key={key}`, and the mode component's `card={card}` prop) now means "what to display", separate from `freshCard` ("what the query currently has"), so the rest of the JSX and the `announcement()` call, which already reference the local `card`/`key` variables, need no further edits beyond what Step 3 below covers for the mode dispatch itself.

Replace the `<FlipMode ... />` element with a dynamic mode component. Resolve the *effective* mode defensively: the orchestrator guarantees a `typed`/`multiple_choice` card always carries its supporting data (Refinement 3), but the page still falls back to `flip` if that guarantee is ever violated, rather than rendering a broken mode component:

```tsx
        const effectiveMode =
          (card.mode === 'typed' && card.accepted_answers === null) ||
          (card.mode === 'multiple_choice' && card.choices === null)
            ? 'flip'
            : card.mode;
        const Mode = MODE_COMPONENTS[effectiveMode];
        body = (
          <Stack gap="md">
            <Mode
              key={key}
              card={card}
              showFurigana={showFurigana}
              pending={busy}
              onReveal={reveal}
              onGrade={grade}
              onContinue={continueToNext}
            />
```

(`const Mode = ...` goes just above the existing `body = (` assignment in the `card !== null` branch; the rest of that branch, including the failed-save alert below `<Mode ...>`, is unchanged.)

Add `CardView` to the file's type-only import from `../../api/endpoints` (it already imports `AnswerRequest`, `Grade`, `ReviewCounts` from there — add `CardView` alongside them).

- [ ] **Step 4: Run the tests to verify they pass**

Run (in `frontend/`): `npx vitest run src/features/review/ReviewPage.test.tsx`
Expected: PASS. Also re-run the full review suite to catch a regression in the untouched flip-mode tests: `npx vitest run src/features/review`.

- [ ] **Step 5: Run the frontend gate**

Run (in `frontend/`): `npm run format:check && npm run lint && npm run build && npm run coverage`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/features/review/ReviewPage.tsx frontend/src/features/review/ReviewPage.test.tsx
git commit -m "feat: dispatch review modes on ReviewPage and hold feedback until Continue" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Task 9: Settings page — per-item-type mode selection

**Files:**
- Modify: `frontend/src/features/settings/settingsForm.ts`, `settingsForm.test.ts`, `SettingsPage.tsx`, `SettingsPage.test.tsx`

**Interfaces:**
- Consumes: `ReviewModeName`, `ReviewSettings`, `ReviewSettingsInput` (Task 5).
- Produces: `SettingsFormValues` gains `kana_mode`, `kanji_mode`, `vocab_mode`; `toFormValues`/`toRequest`/`canonical` handle them; three new `NativeSelect`s on the settings page.

- [ ] **Step 1: Write the failing tests**

Add to `frontend/src/features/settings/settingsForm.test.ts` (check its existing structure for `toFormValues`/`toRequest`/`isSettingsDirty` round-trip tests and add alongside them):

```typescript
it('round-trips the three review modes through the form', () => {
  const settings: ReviewSettings = {
    ...RECOMMENDED_SETTINGS,
    kana_mode: 'typed',
    kanji_mode: 'multiple_choice',
    vocab_mode: 'flip',
  };
  const values = toFormValues(settings);
  expect(values.kana_mode).toBe('typed');
  expect(values.kanji_mode).toBe('multiple_choice');
  expect(toRequest(values).kana_mode).toBe('typed');
});

it('treats a changed review mode as dirty', () => {
  const initial = toFormValues(RECOMMENDED_SETTINGS);
  const changed = { ...initial, kana_mode: 'typed' as const };
  expect(isSettingsDirty(changed, initial)).toBe(true);
});
```

Update `RECOMMENDED_SETTINGS` in `settingsForm.test.ts`'s own imports if the test file defines its own copy rather than importing the one from `settingsForm.ts`; if it imports `RECOMMENDED_SETTINGS` from `settingsForm.ts`, no separate test-file update is needed (Step 3 updates the source of truth).

Add to `frontend/src/features/settings/SettingsPage.test.tsx` (find its existing "renders the loaded settings into the form" style test and add a new one alongside):

```tsx
it('shows the three review-mode selects and saves a changed one', async () => {
  const user = userEvent.setup();
  renderSettingsPage(); // use this file's existing helper that seeds a loaded settings query
  const kanaSelect = await screen.findByLabelText('Kana review mode');
  await user.selectOptions(kanaSelect, 'Typed answer');
  await user.click(screen.getByRole('button', { name: 'Save' }));
  await waitFor(() => {
    expect(screen.getByText('Settings saved')).toBeInTheDocument();
  });
});
```

Check `SettingsPage.test.tsx`'s existing render helper name and MSW setup before writing this (it already has one for the other fields' save-round-trip tests — reuse it rather than duplicating server setup).

- [ ] **Step 2: Run the tests to verify they fail**

Run (in `frontend/`): `npx vitest run src/features/settings`
Expected: FAIL (`toFormValues` does not return `kana_mode`; no "Kana review mode" label in the DOM).

- [ ] **Step 3: Write the implementation**

In `frontend/src/features/settings/settingsForm.ts`:

Add `ReviewModeName` to the import from `../../api/endpoints`.

Add the three fields to `SettingsFormValues`:

```typescript
export interface SettingsFormValues {
  new_card_policy: NewCardPolicyName;
  new_limits: { kana: number | string; kanji: number | string; vocab: number | string };
  target_retention_percent: number;
  rollover_hour: number;
  active_levels: Level[];
  mastery_threshold_percent: number | string;
  kana_mode: ReviewModeName;
  kanji_mode: ReviewModeName;
  vocab_mode: ReviewModeName;
}
```

Add them to `RECOMMENDED_SETTINGS`:

```typescript
export const RECOMMENDED_SETTINGS: ReviewSettings = {
  new_card_policy: 'strict_order',
  new_limits: { kana: 20, kanji: 15, vocab: 20 },
  target_retention: 0.9,
  rollover_hour: 4,
  active_levels: ['N5'],
  mastery_threshold: 0.8,
  kana_mode: 'flip',
  kanji_mode: 'flip',
  vocab_mode: 'flip',
};
```

Add a shared list of options, used by the three selects:

```typescript
export const REVIEW_MODES: readonly { value: ReviewModeName; label: string }[] = [
  { value: 'flip', label: 'Flip and grade yourself' },
  { value: 'typed', label: 'Typed answer' },
  { value: 'multiple_choice', label: 'Multiple choice' },
];
```

Add the three fields to `toFormValues`:

```typescript
export function toFormValues(settings: ReviewSettings): SettingsFormValues {
  return {
    new_card_policy: settings.new_card_policy,
    new_limits: { ...settings.new_limits },
    target_retention_percent: toPercent(settings.target_retention),
    rollover_hour: settings.rollover_hour,
    active_levels: LEVELS.filter((level) => settings.active_levels.includes(level)),
    mastery_threshold_percent: toPercent(settings.mastery_threshold),
    kana_mode: settings.kana_mode,
    kanji_mode: settings.kanji_mode,
    vocab_mode: settings.vocab_mode,
  };
}
```

And to `toRequest`:

```typescript
export function toRequest(values: SettingsFormValues): ReviewSettingsInput {
  return {
    new_card_policy: values.new_card_policy,
    new_limits: {
      kana: Number(values.new_limits.kana),
      kanji: Number(values.new_limits.kanji),
      vocab: Number(values.new_limits.vocab),
    },
    target_retention: toFraction(values.target_retention_percent),
    rollover_hour: values.rollover_hour,
    active_levels: LEVELS.filter((level) => values.active_levels.includes(level)),
    mastery_threshold: toFraction(Number(values.mastery_threshold_percent)),
    kana_mode: values.kana_mode,
    kanji_mode: values.kanji_mode,
    vocab_mode: values.vocab_mode,
  };
}
```

And to the `canonical()` dirtiness comparison:

```typescript
function canonical(values: SettingsFormValues): string {
  return JSON.stringify([
    values.new_card_policy,
    String(values.new_limits.kana),
    String(values.new_limits.kanji),
    String(values.new_limits.vocab),
    values.target_retention_percent,
    values.rollover_hour,
    LEVELS.filter((level) => values.active_levels.includes(level)),
    String(values.mastery_threshold_percent),
    values.kana_mode,
    values.kanji_mode,
    values.vocab_mode,
  ]);
}
```

`validateSettings` needs no change (a `NativeSelect` bound to a closed enum cannot produce an invalid value). `SERVER_FIELDS` (used by `placeServerErrors`) gains three entries:

```typescript
const SERVER_FIELDS: Readonly<Record<string, string>> = {
  new_card_policy: 'new_card_policy',
  kana: 'new_limits.kana',
  kanji: 'new_limits.kanji',
  vocab: 'new_limits.vocab',
  target_retention: 'target_retention_percent',
  rollover_hour: 'rollover_hour',
  active_levels: 'active_levels',
  mastery_threshold: 'mastery_threshold_percent',
  kana_mode: 'kana_mode',
  kanji_mode: 'kanji_mode',
  vocab_mode: 'vocab_mode',
};
```

In `frontend/src/features/settings/SettingsPage.tsx`, add `NativeSelect` is already imported (used for `rollover_hour`); add `REVIEW_MODES` to the import from `./settingsForm`. Add a new section after "Study day" (before the `general !== null &&` error block):

```tsx
        <Stack gap="md">
          <Title order={3}>How you answer</Title>
          <NativeSelect
            label="Kana review mode"
            data={REVIEW_MODES.map((mode) => ({ value: mode.value, label: mode.label }))}
            value={values.kana_mode}
            onChange={(event) => {
              form.setFieldValue('kana_mode', event.currentTarget.value as SettingsFormValues['kana_mode']);
            }}
          />
          <NativeSelect
            label="Kanji review mode"
            data={REVIEW_MODES.map((mode) => ({ value: mode.value, label: mode.label }))}
            value={values.kanji_mode}
            onChange={(event) => {
              form.setFieldValue('kanji_mode', event.currentTarget.value as SettingsFormValues['kanji_mode']);
            }}
          />
          <NativeSelect
            label="Vocabulary review mode"
            data={REVIEW_MODES.map((mode) => ({ value: mode.value, label: mode.label }))}
            value={values.vocab_mode}
            onChange={(event) => {
              form.setFieldValue('vocab_mode', event.currentTarget.value as SettingsFormValues['vocab_mode']);
            }}
          />
        </Stack>
```

- [ ] **Step 4: Run the tests to verify they pass**

Run (in `frontend/`): `npx vitest run src/features/settings`
Expected: PASS.

- [ ] **Step 5: Run the frontend gate**

Run (in `frontend/`): `npm run format:check && npm run lint && npm run build && npm run coverage`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/features/settings/settingsForm.ts frontend/src/features/settings/settingsForm.test.ts frontend/src/features/settings/SettingsPage.tsx frontend/src/features/settings/SettingsPage.test.tsx
git commit -m "feat: per-item-type review mode settings on the Settings page" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Task 10: Docs and whole-branch verification

**Files:**
- Modify: `README.md`, `CHANGELOG.md`, `TODO.md`, this plan's own "Implementation notes" (below)

- [ ] **Step 1: Update README**

In the "Studying in the browser" section (or wherever `README.md` documents the review screen — search for "grade yourself"), add a short paragraph after the existing flip-mode description:

```markdown
Typed-answer and multiple-choice are two more ways to answer, chosen per item type (kana,
kanji, vocabulary) on the Settings page. Both grade automatically — correct is graded Good,
wrong is graded Again — and show what the right answer was before you continue to the next
card.
```

- [ ] **Step 2: Update CHANGELOG**

Add an "Added" entry under the unreleased section (check the file's existing heading convention and match it):

```markdown
- Typed-answer and multiple-choice review modes, alongside the existing flip-and-grade mode,
  chosen per item type on the Settings page.
```

- [ ] **Step 3: Update TODO.md**

Check off `- [ ] Typed-answer and multiple-choice review modes plug into the ReviewMode contract` and the "Later sub-projects" line `- [ ] 3. Typed-answer (romaji -> kana; ぢ/じ and づ/ず share romaji, accept both) and multiple-choice modes` (mark both `- [x]`). Add any new follow-ups noticed while implementing (for example, if the romanization-variant table's coverage was found incomplete against the real `content.db` kana set during Task 2, or if `ChoiceMode`'s distractor quality looked too easy/too hard during manual testing) under a new bullet, following the existing "Study loop hardening and test follow-ups" style.

- [ ] **Step 4: Run both full gates one more time**

Backend (repo root): `uv run ruff format --check . && uv run ruff check . && uv run mypy && uv run bandit -c pyproject.toml -r src -q && uv run pytest -q`
Frontend (`frontend/`): `npm run format:check && npm run lint && npm run build && npm run coverage`
Expected: all green. If either coverage gate is short, add the missing test rather than lowering the gate.

- [ ] **Step 5: Commit and mark the PR ready**

```bash
git add README.md CHANGELOG.md TODO.md docs/superpowers/plans/2026-09-22-bunsho-typed-mc-review-modes.md
git commit -m "docs: typed-answer and multiple-choice modes in README, changelog and TODO" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
git push
gh pr ready
```

Then hand back to James for review and merge — never merge to `main` directly.

## Implementation notes

- `answer_key.py`'s `_vocab_answers` imports `Vocab` at module scope alongside `Kana`/`Kanji` and
  types its parameter directly as `Vocab`, per the brief's own explicit correction — not the
  `vocab: object` + local import + `assert isinstance` workaround the brief's draft code showed.
- `distractors.py`'s `_ranked_pool` needs one narrowly-scoped `noqa: S311 # nosec B311` on
  `random.Random()`: it is shuffling quiz choices, not doing anything security-sensitive.
- Regenerating the OpenAPI schema in Task 5 made `kana_mode`/`kanji_mode`/`vocab_mode` *required*
  fields on `ReviewSettings`/`ReviewSettingsInput` — a consequence of Tasks 1-4 that the plan's
  Task 5 file list and "Produces" section did not anticipate. Fixing only the three card fixtures
  left `npm run build` and the settings round-trip test broken, so Task 5 also threaded the three
  fields (all defaulting to `'flip'`, matching the backend default) through
  `settingsForm.ts`'s `RECOMMENDED_SETTINGS`/`SettingsFormValues`/`toFormValues`/`toRequest` and
  `fixtures.ts`'s `makeSettings`, with no settings-page UI added yet (that stayed Task 9's job).
- `ChoiceMode`'s option buttons were built with a plain `{choice}` label, not the brief's
  numeric-prefixed `"1. {choice}"`: the prefix broke the brief's own anchored accessible-name test
  regexes (e.g. `getByRole('button', { name: /^a$/ })`). A later fix (`ddd433a`) restored the
  visible key numbering as an `aria-hidden` `.key` span (the same pattern `GradeBar.tsx` already
  used), keeping the digit out of the accessible name while showing it to sighted keyboard users —
  `aria-keyshortcuts` alone is not rendered visually by any browser.
- `TypedMode` needs no custom keyboard hook (a native `<form onSubmit>` plus a focused Continue
  button covers Enter-to-submit and Enter/Space-to-continue); `ChoiceMode` gets a small
  `useChoiceShortcuts` hook for digit-key picking, reusing `useReviewShortcuts`'s exported
  `isForReview` guard, exactly as the "Refinements to the spec" section anticipated.
- The romanization-variant table (`ROMAJI_VARIANTS`) and the じ/ぢ・ず/づ homophone table were
  unit-tested against the fixture kana in Task 2's tests only, not walked against the full real
  `content.db` kana set by hand; no gap was reported by any task, so none is called out as a
  follow-up, but this is worth a spot check against the built deck if a learner ever reports a
  typed kana answer being wrongly marked incorrect.
