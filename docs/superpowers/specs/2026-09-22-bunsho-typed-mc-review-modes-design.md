# Bunshō: Typed-Answer and Multiple-Choice Review Modes — Design

Status: design approved 2026-09-22 (brainstorming). Next: implementation plan.
Parent designs: `2026-09-20-bunsho-2a-review-engine-design.md` (the review API this extends) and
`2026-09-20-bunsho-2b2-study-loop-design.md` (the `ReviewMode` seam this fills; flip-and-grade is
its only implementation today).

## Scope

`TODO.md`'s "Later sub-projects" item 3: "Typed-answer (romaji -> kana; ぢ/じ and づ/ず share romaji,
accept both) and multiple-choice modes." Both modes are designed together here, since they share the
same data (accepted answers) and the same grading behaviour (auto-graded, no self-report), even though
they will likely still ship as separate implementation-plan tasks.

Covers: typed-answer and multiple-choice on every existing direction (kana both directions; kanji all
three; vocab both directions); a per-item-type setting choosing the mode; the `CardView` and
`ReviewSettings` changes needed; the new `TypedMode` and `ChoiceMode` components; and the card-transition
change in `ReviewPage` that both need.

Out of scope: stroke order/handwriting input; Anki export; sentence/grammar practice (all still
`TODO.md`'s "Later sub-projects"); undo of a grade; study-ahead; changing `FlipMode` itself (it keeps
self-grading, unchanged) or the four-grade scheduler contract.

## Decisions (locked in brainstorming)

| Topic | Decision |
|---|---|
| Modes covered | Both typed-answer and multiple-choice, in one spec. |
| Direction coverage | Both modes apply to every direction, including meaning-based ones. |
| Grading | Fully automatic: correct → Good, wrong → Again. No self-report, no response-time-based Easy, no Hard from a near-miss. `FlipMode`'s full four-grade self-report is untouched and stays available. |
| Typed matching | Exact match after normalization (trim, casefold) against a server-supplied list of accepted strings. No edit-distance/fuzzy tolerance. |
| Meaning matching | Matched against any of the content's known glosses (`kanji.meanings`, `vocab.meaning` + `additional_definitions`), not just one canonical string. |
| Japanese-script input | Requires the OS IME; no romaji-to-kana conversion fallback. Directions whose correct answer is kana/kanji (`sound_to_glyph`, `meaning_to_kanji`, vocab recall) still get typed-answer, just typed via IME. |
| Distractor source | Server-computed, shipped on `CardView` as `choices`, so the client stays dumb about content. |
| Mode selection | Per item type (`kana_mode`, `kanji_mode`, `vocab_mode`), not one global setting and not a per-session toggle. |
| Where grading happens | Client-side, exactly like today's self-grading. `CardView` already ships full back-face content before the learner answers (flip mode needs it to render instantly), so shipping `accepted_answers`/`choices` exposes nothing new; a client that could fabricate a grade today can do so identically either way. No new endpoint, no server round-trip for correctness. |
| Post-answer flow | Grade fires immediately on submit/pick (posts to the server right away), but the learner sees a feedback state — their answer or pick versus the correct one — and advances on their own action (Space/Enter or Continue), not automatically. |

## Data model and API changes

**`CardView`** (`src/bunsho/models/review_session.py`) gains three fields, populated by the
orchestrator's `_view()` helper only when the resolved mode for that card needs them (flip-only
learners cost nothing extra):

```python
class CardView(BaseModel):
    ...
    mode: Literal["flip", "typed", "multiple_choice"]
    accepted_answers: list[str] | None = None
    choices: list[str] | None = None
```

- `mode` is resolved server-side from `ReviewSettings` for the card's `item_type`, so `ReviewPage`
  switches on `card.mode` directly with no second settings fetch.
- `accepted_answers` is every string that counts as correct for this card's direction:
  - `glyph_to_sound`: the kana's romaji plus known romanization variants (Hepburn/Kunrei — し/shi/si,
    ち/chi/ti, つ/tsu/tu, ふ/fu/hu, じ/ji/zi, and their digraphs). A small variant table, not
    per-card data.
  - `sound_to_glyph`: the kana glyph(s) that romanize to the shown sound — most cards have exactly
    one, but じ/ぢ and ず/づ cards accept both glyphs where they're phonetically identical.
  - `kanji_to_reading`: the on/kun readings shown on the back, in kana (IME input, no romanization).
  - `kanji_to_meaning`, vocab recognition (meaning side): every listed gloss for the item
    (`kanji.meanings`; `vocab.meaning` plus `additional_definitions`).
  - `meaning_to_kanji`: the kanji character.
  - vocab recall: the expression (kana/kanji as stored).
  - Populated only when `mode == "typed"`.
- `choices` is 4 shuffled strings for multiple-choice (the correct answer — one entry from
  `accepted_answers` — plus 3 distractors), populated only when `mode == "multiple_choice"`.

**`ReviewSettings`** (`src/bunsho/models/review_settings.py`) gains:

```python
kana_mode: ReviewModeName = ReviewModeName.FLIP
kanji_mode: ReviewModeName = ReviewModeName.FLIP
vocab_mode: ReviewModeName = ReviewModeName.FLIP
```

`ReviewModeName` is a new `StrEnum` (`flip | typed | multiple_choice`), following the existing
`NewCardPolicyName` pattern. Default is `flip` for all three, so existing installs are unaffected
until a learner opts in.

`POST /reviews/answer` is unchanged: still `item_id`, `direction`, `grade`, `expected_last_review`,
`duration_ms`. Typed/multiple-choice modes compute `grade` client-side and submit through the same
path `FlipMode` uses today.

## Distractor generation

For a card with `mode == "multiple_choice"`, the orchestrator asks `ContentCatalog` for other items of
the same `item_type` (preferring the same direction and active level), takes their would-be
`accepted_answers[0]` text, and picks 3 at random, excluding:

- the current item,
- any distractor whose text matches the correct answer (two different items can share a reading or
  meaning — e.g. two kanji with the same kun reading).

If the level's pool has fewer than 3 distinct candidates, the search widens to all active levels
before falling back to whatever `item_type` overall has. If even that yields fewer than 3, `choices`
still ships with however many are available (correct answer plus 1 or 2) — a thin pool degrades the
question, it never breaks the card. This mirrors the existing content-selection policy pattern
(`policy.select` in `_plan()`), reusing `ContentCatalog` rather than adding a new query path.

## Grading and matching logic

Both modes reduce to the same check: is the learner's typed text (trimmed, casefolded) or their picked
`choices` entry a member of `card.accepted_answers` (also trimmed, casefolded for comparison)? True →
`onGrade(Grade.GOOD)`. False → `onGrade(Grade.AGAIN)`. This is the entire client-side grading logic —
no separate code path for typed versus multiple-choice beyond how the input is collected, and no
edit-distance or partial-credit logic per the locked decision above.

The romanization-variant table and the じ/ぢ・ず/づ equivalence live server-side in the
`accepted_answers` construction (single source of truth, testable in Python), not duplicated as
client-side fuzzy matching.

## New components (same `ReviewMode` contract)

No change to the `ReviewMode` props contract (`card`, `showFurigana`, `pending`, `onReveal`,
`onGrade`) — `TypedMode` and `ChoiceMode` are new implementations of it, exactly like `FlipMode`.

- **`TypedMode`** (`frontend/src/features/review/TypedMode.tsx`): an autofocused text input plus
  submit (Enter or a button). On submit: compute correctness against `card.accepted_answers`, call
  `onGrade` immediately, then render a feedback state — what the learner typed alongside the correct
  answer — with a Continue action (Space/Enter or a button) to advance. `onReveal` fires when the
  feedback state appears (mirrors `FlipMode`'s flip-is-the-reveal timing, used for the screen-reader
  announcement).
- **`ChoiceMode`** (`frontend/src/features/review/ChoiceMode.tsx`): the card's front and 4 choice
  buttons render together from the start — no separate reveal step, since `card.choices` already
  contains the options. Picking one both grades and reveals; same feedback-then-continue pattern as
  `TypedMode`. Buttons follow `GradeBar`'s existing layout pattern (`SimpleGrid`, keyed 1-4).
- Both get their own keyboard hook (Enter to submit typed input; 1-4 to pick a choice; Enter/Space to
  continue), separate from `useReviewShortcuts`'s Again/Hard/Good/Easy keys, since neither mode shows
  the grade bar. Same guards as today: modifier keys, `event.repeat`, IME composition
  (`isComposing`), and ignored while pending.

## `ReviewPage`: the card-transition change

Today, grading and advancing are the same instant: pressing a grade button in `FlipMode` posts the
answer and the next card replaces the current one as soon as the query settles. Typed and
multiple-choice need to hold the just-answered card's feedback on screen *after* grading, while the
next card loads in the background, and only swap in the new card when the learner presses Continue.

This needs new local state in `ReviewPage`: a `revealedAnswer` (or similar) holding the last
submission's correctness and correct-answer text, kept until an explicit "advance" action, decoupled
from whether the next-card fetch has resolved. `FlipMode`'s existing revealed/flip state stays
untouched — this is additive state for the two new modes, not a rework of the existing flow.

## Settings and dashboard

`SettingsPage` gains three new selects (Kana/Kanji/Vocab review mode: Flip / Typed / Multiple choice),
following the existing form pattern (dirtiness by comparison, per Plan 2B-3's lesson). No change to
the dashboard tiles — they read counts, not modes.

## Error handling

- Stale card (409) and pending-submission guards: unchanged, identical to `FlipMode` today.
- A card whose `mode` claims `typed`/`multiple_choice` but is missing `accepted_answers`/`choices`
  (a server bug, not a learner path): render as `FlipMode` for that card rather than a broken screen.
- Fewer than 2 usable `choices`: still renders with whatever is available; never blocks study.
- Network/save failure: same Try again pattern as `FlipMode`'s existing alert — the submitted grade
  is not lost, resend uses the same `submit()` path.

## Testing

- **Backend:** `accepted_answers` construction per direction, with explicit cases for the じ/ぢ and
  づ/ず equivalence and the romanization-variant table; distractor selection and its level-widening
  and thin-pool fallbacks; the three new `ReviewSettings` fields' validation and defaults; `mode`
  resolution on `CardView` per item type.
- **Frontend:** matching/normalization unit tests (case, whitespace, membership against multiple
  accepted answers); `TypedMode` and `ChoiceMode` component tests (submit flow, shortcuts, pending
  guard, screen-reader announcements matching `FlipMode`'s static-text pattern); `ReviewPage`'s new
  feedback-then-continue transition (next card fetched but not shown until Continue); `SettingsPage`'s
  three new fields (following the existing settings test patterns from 2B-3).
- Coverage gate stays at the project's existing threshold on all four metrics.

## Risks

- **Romanization-variant table completeness.** Missing a Kunrei/Hepburn variant reads as a wrong
  answer for a correct one. Build it from the same kana data already in `content.db` and test it
  against every kana row, not a hand-picked subset.
- **Distractor quality.** Random selection can produce an implausibly easy or implausibly similar set
  (e.g., near-homophone kanji as accidental "gotcha" distractors). Acceptable for a first version;
  revisit with smarter selection (same radical, same reading) only if it proves too easy or too hard
  in practice — YAGNI for now.
- **`ReviewPage` state complexity.** The new held-feedback state must not let a stale card's feedback
  leak into the next card's key/identity (the existing `cardKey()` remount pattern should still apply,
  scoped to when Continue is pressed, not when the next-card fetch resolves).
- **Client-side grading trust.** Documented as an accepted, pre-existing trust level (flip mode already
  self-reports), not a new risk introduced by this work.
