# Phase 3 completion report

Phase 3 extends the existing tutor and placement system in place. No Phase 4 features
were implemented and no dependencies were added.

## Files added

- `PHASE3_REPORT.md`
- `PHASE3_VERIFICATION.md`
- `app/api/learner.py`
- `app/learner/__init__.py`
- `app/learner/catalog.py`
- `app/learner/context.py`
- `app/learner/events.py`
- `app/learner/initialization.py`
- `app/learner/migrations.py`
- `app/learner/observations.py`
- `app/learner/reset.py`
- `app/learner/schemas.py`
- `app/learner/service.py`
- `app/learner/sessions.py`
- `docs/learning-memory.md`
- `frontend/learner.js`
- `tests/test_learning_memory.py`

## Files modified

- `.env.example`
- `README.md`
- `app/assessment/repository.py`
- `app/main.py`
- `app/memory/conversation.py`
- `app/tutor/schemas.py`
- `app/tutor/service.py`
- `frontend/app.js`
- `frontend/assessment.js`
- `frontend/index.html`
- `frontend/styles.css`

## Migration and entities

SQLite schema v1 → v2 adds nine tables: `learner_state`, `skill_state`, `learning_topics`,
`learner_topics`, `mistake_state`, `learning_events`, `tutor_sessions`, `conversation_turns`,
and `skill_history`. It uses the existing database and connection boundary. Migration
and backfill are transactional and idempotent. Existing assessments, answers, questions
and initial profile rows are preserved. Back up the database before upgrading.

Completed Phase 2 placement initializes current level/score/confidence and each skill's
baseline. Recognized placement topics seed exposure without updating skill scores twice.
The original placement JSON remains immutable and visible. New unassessed learners have
null scores and no fabricated strengths. All persisted learner state survives restart.

## Events, topics and mistakes

The model supplies typed observations; application code validates, normalizes and applies
them. Performance has a score; explanations/help record exposure only. Unknown tags map
to bounded unscored categories. Event IDs and request fingerprints prevent replay from
double-counting. A saved exchange, events, state changes and transcript commit together.

A fixed topic catalog supports vocabulary, grammar and kanji exposure, with separate
kanji reading/meaning keys. Per-learner state tracks encounters, correctness totals,
dates and eight recent scores. Weakness requires at least three observations with mean
below 0.6; strength requires at least four with mean at least 0.8 and no recent failure.
Later successes can recover weak topics. Mistakes aggregate canonical keys and activate
after three recent occurrences; recovered topics improve their mistake status.

Skill state receives at most one scored update per skill per exchange. Every fifth
observation can move an estimate by 0.15 within placement ±1, with difficulty checks.
Meaningful changes create skill-history rows. Overall level/confidence are not promoted
automatically; unassessed skill estimates remain null while recording performance.

## Tutor context and token control

The context builder selects current level, major skills, preferences, up to five weak
topics, five active recent mistakes, three strengths and five recent topics. The profile
summary is capped at 4,000 UTF-8 bytes. Prior conversation context is limited to
MAX_HISTORY_TURNS complete exchanges and 12,000 characters; the current message is
separately capped at 4,000 characters. Full events, assessment history, vocabulary lists
and lifetime transcripts are not sent. Bounds are sizes, not exact tokenizer counts.

## Added APIs

- POST `/api/learners`: unassessed learner.
- GET `/api/learners/{id}/profile`: current state and initial placement.
- PATCH `/api/learners/{id}/preferences`: preferences/goal.
- GET `/api/learners/{id}/activity`: bounded recent activity.
- POST and GET `/api/learners/{id}/sessions`: create/list saved sessions.
- GET `/api/learners/{id}/sessions/{session_id}`: latest saved exchanges.
- POST `/api/learners/{id}/sessions/{session_id}/close`: close without deleting.

Existing `/api/chat` accepts an idempotent `request_id` for saved sessions. Original
temporary-session and assessment endpoints remain operational. Learning-event recording
is an internal service, not a public endpoint that accepts fabricated evidence.

## UI

My learning displays skills, strengths/weaknesses, mistake patterns, vocabulary/grammar/
kanji memory, original placement, recent activity and session history. Preferences and
goals persist and influence subsequent tutor requests. Browser storage holds identifiers
only; transcripts are restored from SQLite. New session retains learning memory. Saved
learner IDs can be reopened; temporary chat remains available. Developer reset is a
separate CLI requiring a repeated UUID, preserving original placement and other learners.

## Tests and results

Added 37 Phase 3 cases; **139 tests pass**, including all 102 prior cases. Tests cover
migration preservation/rollback, restart, preferences, normalization, exposure, recovery,
stable skill updates, malformed observations, context budgets, replay, ownership, failed
writes/provider calls, stale writers, bounded per-turn evidence and scoped reset.
Python compilation and JavaScript syntax checks passed. Browser checks verified upgraded
placement handoff, preference persistence, restored conversations, repeated mistake
display and closed-session viewing. See `PHASE3_VERIFICATION.md` for details.

## Limitations and recommended Phase 4

Live LLM observation/teaching quality remains unverified without an API key. The catalog
and thresholds are deliberately small and provisional. Topic labels are learning signals,
not mastery certification. Confidence remains placement confidence. No automatic data
retention, authentication, identity merging, streaming or advanced retrieval is provided.
Learner/session ownership checks prevent accidental mixing but IDs are not credentials;
keep the prototype bound to loopback. Two existing upstream test deprecation warnings
remain. Reset is destructive and should be used only after stopping and backing up SQLite.

Phase 4 should consume the profile service's skills, weaknesses, recent performance,
exposure and goals to select study priorities, difficulty and review/new-content balance.
Curriculum sequencing, daily lesson plans, mastery algorithms and spaced repetition have
not been started. See `README.md` and `docs/learning-memory.md` for usage and design.
