# Bunshō Plan 2B-2: The Study Loop (Dashboard and Review) — Design

Status: design approved 2026-09-20 (brainstorming). Next: implementation plan.
Parent designs: `2026-09-19-bunsho-foundation-and-review-engine-design.md` (its "Frontend" section),
`2026-09-20-bunsho-2a-review-engine-design.md` (the review API this consumes, merged in PR #9) and
`2026-09-20-bunsho-2b1-frontend-skeleton-design.md` (the app this extends, merged in PR #11).

## Scope and slicing

The four remaining screens are split in two plans:

- **2B-2 (this spec): the study loop.** The dashboard on the Home page (due and new counts, Study now),
  the flip-and-grade review screen (keyboard shortcuts, furigana, session-end states), a Study link
  in the navigation, and route-level code splitting (fixes the 540 kB chunk warning).
- **2B-3 (later, own spec): statistics and settings.** The statistics screen (`GET /stats/summary`)
  and the settings screen (`GET`/`PUT /settings`: new-card policy, daily limits, retention, rollover
  hour, active levels, mastery threshold). The default settings already work, so studying does not
  wait for it.

Out of scope for 2B-2: statistics and settings screens; per-level progress on the dashboard;
typed-answer and multiple-choice modes (the `ReviewMode` seam makes them additive); stroke order;
undo of a grade (the review log is append-only); study-ahead (the API has no such call); the CSP
header; browser end-to-end tests.

## Decisions (locked in brainstorming)

| Topic | Decision |
|---|---|
| Slicing | 2B-2 study loop (dashboard, review, code splitting); 2B-3 statistics and settings. |
| Data flow | One `next` query plus an `answer` mutation; after a grade, refetch `next`. No client-side card queue (the server owns due order, daily limits and new-card policy). |
| Furigana | Hidden on the front of any card that tests the meaning or reading of a kanji word; shown after the flip. A "Show furigana" switch in the review header (remembered in this browser only) also shows it on the front. |
| Modes | Flip and self-grade only, behind a `ReviewMode` component seam. |
| Keyboard | Space or Enter flips; 1 to 4 grade Again, Hard, Good, Easy after the flip. |
| Typography | Hand-written CSS modules for the study surface; Japanese system font stack (as in the 2B-1 theme); `lang="ja"` on every Japanese run. |
| Versions | Same rule as 2B-1: latest stable of everything; any older major needs a recorded reason. |

## Structure

```
frontend/src/
  api/endpoints.ts        + nextReview(), answerReview()   (types from schema.d.ts only)
  api/queries.ts          + queryKeys.reviewNext, useNextReview()
  components/Furigana.tsx (+ Furigana.module.css)          native <ruby> from RubySegment[]
  features/review/
    ReviewPage.tsx        session state machine and layout
    cardFaces.ts          pure: CardView + furigana flag -> {front, back} descriptors
    FlipMode.tsx          ReviewMode implementation: flip, then grade
    GradeBar.tsx          four buttons with key hints and projected intervals
    useReviewShortcuts.ts keyboard hook (guards below)
    useFuriganaPreference.ts   localStorage-backed switch (try/catch around storage)
    ReviewFinished.tsx    the done-for-now and not-built states
    formatInterval.ts     seconds -> "10 m", "4 d" (pure)
    review.module.css     study-surface typography and layout
  features/home/          HomePage gains the dashboard panel (StudyPanel.tsx)
  App.tsx                 lazy routes (Home, Review, Build) behind one Suspense fallback
```

`ReviewMode` is a small props contract: `{ card: CardView; showFurigana: boolean; pending: boolean;
onReveal(): void; onGrade(grade: Grade): void }`. `FlipMode` implements it; `ReviewPage` renders the mode and owns fetching,
timing and errors, so a future typed or multiple-choice mode replaces only the mode component.

## Data flow

- **Query.** `['review','next']` backed by `GET /reviews/next`. Its payload (`NextCard`) carries the
  hydrated card or `null`, the counts (`due` and `new_remaining` per type) and `next_due_at`, so the
  dashboard and the review screen share one cache entry. No tokens ever enter the key or the cache.
- **Answer.** `POST /reviews/answer` with `item_id`, `direction`, `grade`, `expected_last_review` and
  `duration_ms`. `expected_last_review` is an opaque token: it is sent back exactly as received (byte
  for byte, never parsed or reformatted), and `null` for a new card. `duration_ms` is measured from the
  moment the card is shown to the grade, clamped to the API's 0 to 3,600,000 range.
- **After a successful grade** the `next` query is refetched (the mutation's response carries fresh
  counts, which are written to the cache immediately so the dashboard is current while the next card
  loads).
- **Errors** are normalised by the existing `ApiError` and `messageFor`, except where a screen needs its
  own wording:
  - **409 (stale card):** a short notice ("That card changed elsewhere: loading the next one") and a
    refetch of `next`. The Review screen owns this wording; it is not put in the shared `messageFor`
    (the Build screen's 409 has different wording and lives in its own feature).
  - **503 (content not built):** a message with a link to the Build screen.
  - **Network error / 5xx:** the current card stays visible, the grade is not lost, and a retry button
    (and the same shortcut key) re-sends it. Grade buttons are disabled while a request is pending.
  - **422 / 404 and other failures:** the same alert as a network failure (message from `messageFor`,
    the card stays, Try again re-sends the identical request).
- **Query defaults** stay as in 2B-1 (retry only network errors and 5xx; never 4xx). The answer
  mutation never auto-retries (a duplicate grade would double-count).

## The review screen

**States** are derived from the query and the mutation, not stored: loading (skeleton), error (load failed,
with Try again; 503 links to Build), done (no card), and card, where the mode holds flipped or not and
the page shows saving while the answer and the refetch are in flight. `next_due_at` and the counts drive
the done state.

**Card faces** (from a pure `cardFaces(card, showFurigana)`; everything Japanese carries `lang="ja"`):

| Card | Front | Back |
|---|---|---|
| Kana, glyph to sound | The character, large | Romaji; script and group as a small caption |
| Kana, sound to glyph | Romaji | The character |
| Kanji, kanji to meaning | The kanji, large | Meanings; on and kun readings in smaller type |
| Kanji, kanji to reading | The kanji | On and kun readings; meanings |
| Kanji, meaning to kanji | Meanings | The kanji; its readings |
| Vocab, recognition | The word (kanji form) | Reading as furigana over the word; meaning; part of speech; the example sentence with furigana and its English |
| Vocab, recall | The meaning and part of speech | The word with furigana; the reading; the example sentence as above |

The front shows no furigana unless the header switch is on (after the flip the front word shows its
readings in place). A "New" tag marks unseen cards; the card type and JLPT level are a quiet caption on
the front. A missing example sentence simply omits that
block. Furigana renders from the API's `RubySegment` list (`base`, `reading`, `highlighted`) through
one shared `<Furigana>` component using native `<ruby>`/`<rt>` with `<rp>` fallbacks; the highlighted
segment is emphasised.

**Grade bar.** Four buttons (Again, Hard, Good, Easy) in a group, each showing its key and the projected
interval from `intervals` (seconds, formatted by `formatInterval`: seconds, minutes, hours, days, months).
A card is never graded before it is flipped.

**Keyboard** (`useReviewShortcuts`): Space or Enter flips; 1 to 4 grade after the flip. Ignored when a
modifier key is held, when a text field or other interactive control other than the review controls has
focus, during IME composition (`isComposing`), for auto-repeated keydowns (`event.repeat`), and while an
answer is pending. Shortcuts are hinted on the buttons. There is no undo.

**Focus and accessibility.** The flip button takes focus when a card appears, and focus moves to the
grade group after the flip. One persistent polite status region (always mounted, visually hidden, with a
static sentence such as "Card shown" / "Answer shown" / "Answer saved") announces state changes; nothing
in a live region contains a ticking value (lesson from 2B-1). The furigana switch is a labelled control.
The screen works with mouse, touch or keyboard alone. Animations respect `prefers-reduced-motion`.

**Session end.** When no card is available the page shows one finished state, because the API cannot
say why (`new_remaining` only counts cards that could be introduced right now, so "daily limit used up"
and "everything unlocked is already introduced" look the same): "You're done for now", a sentence naming
both possible reasons, the next due time if any, and a Back to the dashboard link. When the content is
not built (503) the page shows the message and a link to the Build screen. (A later API change could add
a reason field; it is in `TODO.md`.)

## The dashboard (Home)

Reads the same `['review','next']` query. Three compact tiles (kana, kanji, vocab) show due now and new
remaining. A single **Study now** button goes to `/review`; when no card is available it is replaced by
"Nothing due" and the next-due time. The existing content summary and the first-run "build your content"
banner stay below. Loading, error (retry) and not-built states follow the Home page's existing patterns.
The navigation gains a **Study** link.

## Delivery

- **Code splitting:** `Home`, `Review` and `Build` become `React.lazy` routes under one Suspense fallback
  (a small centered loader); `Login` and the shell stay in the main bundle. The build's "chunk larger
  than 500 kB" warning must disappear (no raised limit).
- **Backend:** no change. No new API surface; `frontend/openapi.json` and `schema.d.ts` are unchanged
  (a drift check confirms).
- **Docs:** README (the Study section), CHANGELOG, TODO (tick the code-splitting and Plan 2B-2 items,
  add the new follow-ups) and an "Implementation notes" section on this spec.

## Testing

Vitest, React Testing Library and MSW at the network layer; fake timers, no real network.

- `cardFaces`: a table test over all seven directions (front and back content, furigana on/off, missing
  sentence, unleveled kanji).
- `Furigana`: segment rendering, `<rp>` fallbacks, highlighted segment, `lang="ja"`.
- `formatInterval`: boundaries (seconds, minutes, hours, days, months).
- Review flows: flip then grade by mouse and by keyboard; `duration_ms` measured with fake timers and
  clamped; `expected_last_review` sent unchanged; shortcut guards (modifier, repeat, text input, IME
  composition, pending request, not-yet-flipped); no double grade while pending.
- Errors: 409 loads the next card with the notice; network error keeps the card and retries the same
  grade; 503 links to Build; 422/404 generic reload; nothing-due and limit-spent states.
- Furigana switch: hidden on the front, shown after the flip, shown on the front when on; persists;
  blocked storage does not crash.
- Dashboard: loading, due, nothing-due, not-built and error states; Study link.
- Lazy routes render through Suspense; the routing tests from 2B-1 still pass.
- Coverage gate stays at 80% on all four metrics. The container smoke test already covers the review
  round trip through the API, so it does not change.

## Order of work

One branch (`feat/plan-2b2-study-loop`), draft PR opened early, no stacked PRs.

1. Review endpoints, query keys, `useNextReview`, fixtures and the answer mutation (types from the schema).
2. `Furigana`, `cardFaces`, `formatInterval` and the CSS-module typography.
3. `ReviewPage`, `FlipMode`, `GradeBar`, the shortcut hook, the furigana preference and the accessibility wiring.
4. Dashboard tiles and the Study nav link.
5. Lazy routes and the bundle check.
6. Docs, whole-branch verification (frontend gate, Python gate, drift check, smoke test) and the final review.

## Risks

- **Keyboard handling:** IME composition, held keys and focus traps: a small purpose-built hook with
  explicit tests rather than a library's defaults.
- **Japanese fonts:** the system font stack varies by OS. The 2B-1 theme already sets it; check
  rendering in a real browser and keep the option of self-hosting Noto Sans JP if it looks poor.
- **Stale cards (409):** a second tab or an old card is expected and handled by reloading `next`.
- **Duplicate grades:** a retried or double-fired POST would double-count; the mutation never auto-retries
  and the UI blocks input while pending.
- **Browser verification:** the authenticated screens cannot be checked in a browser by the assistant
  (credentials are not typed into login forms); the PR lists what to eyeball (card typography,
  shortcuts, the mobile layout).
