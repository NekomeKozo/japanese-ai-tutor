# Phase 11E — Flashcards and existing spaced repetition

## Inspection and scope

Started on `main` at `f5afedc`, with Phase 11D (`acd9494`) present and no tracked modifications. Existing untracked design discovery, mockups and original screenshots were preserved. Read the Phase 11D report and inspected the actual review scheduler, queue, evidence model, APIs, persistence and staging ownership protections. Baselines: 124 frontend tests and 57 Phase 6 review tests passed. This phase changes Flashcards and the existing review integration only; Phase 10 providers/audio architecture is unchanged.

## Scheduling and ratings

Phase 6 uses FSRS 6.3.2 with Again, Hard, Good and Easy, wrapped by existing UTC, confidence, growth, lapse and daily-attempt policy. Previously these labels were derived from graded exercise Evidence. A small explicit recall-rating entry point now shares the very same scheduling body. Self-reports are recorded as such, rather than inventing numerical scores or graded mastery Evidence. Existing graded behavior and replay remain supported.

## Content and interaction

Free Practice retains its 30 authored cards, directions, reveal, navigation, shuffle/restart, completion and optional Japanese TTS. Content moved unchanged into a shared public JSON catalog, validated/cached by the browser and read by the backend adapter. Loading that catalog creates no learning records.

Due Reviews filters the existing learner-specific queue before session selection, preserving its priorities, time allowance, maximum seven items and one dimension per topic per batch. Vocabulary and kanji use Phase 6 authored retrieval prompts/answers for the actual scheduled dimension, including kanji readings in their word context. The curated grammar cards currently cover recognition/understanding of `tai_form`, `particle_ni_destination` and `particle_de_location`. Broader conjugation, は/が contrast, grammar application/production and other unsupported targets remain in Daily Study & Review; the interface reports their count. 猫 and 約束 remain Free Practice with no fabricated review identity.

Flow: choose Due Reviews → load → recall → Reveal → select a rating → save → confirmed count/next card. Audio and Reveal never complete reviews. Controls disable during saving. Unknown save outcomes retain the original rating, version and UUID for explicit retry. Changed/suspended/already-reviewed targets require reload. Navigation cannot imply completion; stale responses after a learner change are ignored. Completed counts belong to the current batch; reload retrieves persistent scheduling/history.

## Persistence, progress and security

Uses existing `review_schedules`, `review_attempts` and `learning_events`; no migration or new scheduling table. A transaction checks ownership, due time, eligibility and schedule version, stores one truthful self-assessment activity event, runs the existing scheduler and saves its receipt/history. Persistent submission IDs make repeated/concurrent retries idempotent and reject conflicting reuse. PostgreSQL uses the existing transaction/serialization adapter; SQLite uses existing `BEGIN IMMEDIATE` conventions. Maintenance replay supports both graded and self-reported attempts.

Recent review history includes both methods. Existing Home/Progress activity views retrieve the saved events and last activity; their normal update invalidation is reused. Self-reports do not alter mastery or skill scores. Existing staging authentication, learner ownership, origin/body protections and submission rate limits apply. Dynamic cards/history use text nodes; no private reference content or credentials enter the public catalog.

## Changed files

- Backend: `app/api/reviews.py`, `app/review/{flashcards,queue,scheduler,service}.py`.
- Frontend: `frontend/{flashcard-catalog.js,flashcard-catalog.json,flashcards.js,flashcard-reviews.js,index.html,shell.js,styles.css}`.
- Tests: `tests/{test_flashcard_reviews.py,test_postgres.py,frontend.test.cjs}`; this report.

## Verification

- Local focused backend regression: **182 passed**, covering the new flow and existing review, staging, curriculum and schema tests. Two additional atomic/not-due checks were then added: final Phase 11E suite **25 passed**. Existing Starlette/httpx deprecation warnings only. Offline fixtures block accidental external provider traffic.
- Final frontend regression: **134 passed**. Covers mode separation, unrevealed answers, double taps, delayed saves, frozen retry identities, changed reviews, stale learners, empty/no-profile/network states, completion, catalog recovery and TTS, alongside Phase 11D and earlier regressions.
- Existing deployment source/history audit, all JavaScript syntax checks and diff whitespace checks passed. Disposable PostgreSQL receipt/restart/replay coverage added to the existing CI suite; local PostgreSQL was not claimed.
- Local browser acceptance used a disposable SQLite learner and disabled providers. Verified Free Practice, scheduled kanji/grammar/vocabulary cards, save/advance, reload persistence (four targets became three), mixed review history, completion, empty queue and matching Progress → History events. No production learner records were manufactured or rated for testing.
- Browser emulation measured CSS widths **320, 390, 430, 768, 1440**: no document overflow; rating buttons approximately 72px high, two columns on narrow phones and four on wider screens; prompt text 20–32px. At 430px all ratings were reachable above fixed navigation. Desktop/mobile captures retained in the task output folder. Existing iPhone screenshots informed clearance/spacing; originals were unchanged. No new physical-phone test claimed.

## Deployment and limitations

Implementation is ready for the existing main → Render workflow. Live deployment and GitHub CI verification will be recorded here after pushing. No Render service recreation, database reset, paid-provider request, or account/billing change is required.

Due Reviews is intentionally limited to accurately mapped authored targets. Self-assessment schedules retrieval and records practice; it is not objective mastery evidence. Optional audio depends on the existing browser Japanese voices. Free Practice and current batch position remain transient. Review history shows the latest 20 attempts; dates use the browser display timezone while scheduling remains backend UTC.

## Phase 11F handover

Reuse the existing receipt/version and scheduler paths. Broader grammar mappings need reviewed content covering their full target before eligibility expands. Any graded mastery integration must use genuine exercise evidence, not reinterpret self-ratings. **Stop after Phase 11E; Phase 11F is not begun.**
