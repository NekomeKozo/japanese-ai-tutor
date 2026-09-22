# Phase 4 completion report

The personalized curriculum engine extends the working Phases 1–3 in place. No external
dependencies were added. Phase 5 has not been started.

## Files added

- `PHASE4_REPORT.md`
- `PHASE4_VERIFICATION.md`
- `app/api/curriculum.py`
- `app/curriculum/__init__.py`
- `app/curriculum/catalog.py`
- `app/curriculum/content.py`
- `app/curriculum/migrations.py`
- `app/curriculum/planner.py`
- `app/curriculum/policy.py`
- `app/curriculum/schemas.py`
- `app/curriculum/service.py`
- `docs/curriculum-design.md`
- `frontend/study.js`
- `package-lock.json`
- `tests/test_curriculum.py`

## Files modified

- `.env.example`
- `README.md`
- `app/assessment/repository.py`
- `app/learner/catalog.py`
- `app/learner/context.py`
- `app/learner/events.py`
- `app/learner/migrations.py`
- `app/learner/reset.py`
- `app/learner/schemas.py`
- `app/learner/service.py`
- `app/main.py`
- `docs/learning-memory.md`
- `frontend/app.js`
- `frontend/assessment.js`
- `frontend/index.html`
- `frontend/learner.js`
- `frontend/styles.css`
- `tests/test_learning_memory.py`

## Database migration and entities

Schema v2 → v3 adds `study_sessions` and `study_activities` in the existing SQLite database,
plus controlled curriculum entries in `learning_topics`. Old placement/profile, events,
preferences, conversation and skill data are preserved. Startup migration is transactional
and idempotent. A partial unique index permits one active study plan per learner. Plans,
activity content, progress, results and submission fingerprints persist across restart.
The developer reset now clears the selected learner's study data as well, retaining
original placement and every other learner. Back up SQLite before upgrading/resetting.

## Catalog and curriculum ranking

The catalog has 63 topics: 26 grammar, 13 vocabulary, 12 kanji, five reading, five sentence
writing and two scripts. Seven review-only entries directly reuse broad Phase 2/3 tags.
The combined fixed memory taxonomy has 78 entries; no uncontrolled model-created tags.

Ranking is deterministic application logic. It combines repeated weak evidence, recent
errors, low accuracy, goal relevance, prerequisite value, review age and underrepresented
skills, then subtracts repeated-topic, difficulty-distance and partial-prerequisite costs.
One error has little influence. Strong sampled kana is not repeatedly selected in balanced
plans unless performance deteriorates. Explanations use reason codes mapped to short text;
internal priority values are not shown in the UI.

## Review/new, prerequisites, difficulty and goals

Review starts around half the budget and increases for weakness, poor recent performance,
low placement confidence and a long study gap. Consistent success allows more new material.
Explicit review/new requests adjust this policy. The actual time split is stored separately
from the target; limited eligible pools produce an explanatory note rather than fake review.

Familiar/strong prerequisites pass. Partial scored evidence or a sufficiently supported
placement prior incurs a penalty. Unknown/weak prerequisites block dependents and raise
foundation priority. Exposure alone does not establish readiness. Manual focus never
overrides gates, while advanced explicit questions remain available in ordinary chat.

Difficulty uses each skill's estimate and repeated recent performance, with small bounded
adjustments. Unassessed skills default to foundations. Known review topics can be simplified;
ambitious goals/preferences never authorize a large automatic level jump. JLPT, travel,
conversation, work and university goals affect topic/skill weights only.

## Time and ordering

Requests accept whole-number lengths from 5–60 minutes. Maximum activity counts scale
from one to seven; 30 minutes permits five. Allocation uses review/new minute targets,
at most 12 minutes per activity, never above the requested budget. Small candidate pools
can leave time unused and display the actual estimate. Easier review precedes new work;
a soft repeated-skill penalty favors useful variety. Durations are approximate self-study
budgets, not tracked time or a scheduler.

## Content generation and Phase 3 events

Planning, fixed vocabulary/kanji/script/reading content, resume and recaps require no LLM
call. Grammar/writing content is generated only when reached through the existing provider.
The schema validates topic identity, exact difficulty, bounded fields and answer choices;
malformed output retries once. Content is cached once and rendered using the original
tutor response renderer. The existing assessment evaluator grades answers and accepts
exact semantic references without another call. Answer keys remain server-side until
completion. Generation/grading outages retain the plan and do not count as learner errors.

Opening records exposure. Graded completion atomically saves the activity result and a
Phase 3 performance event with canonical topic, skill, planned difficulty, score, session,
activity type, purpose and grading method. Existing profile update rules then update
learning memory. Skips do not score proficiency. Identical completion retries replay the
saved result; conflicts and stale generation cannot duplicate evidence or reopen skipped
work. The next new plan reads that updated state.

Lesson context is capped at 4,000 UTF-8 bytes and contains only the selected activity,
relevant skill/weakness and preferences. No lifetime conversations/events, complete
placement history or full catalog is sent. Static instructions/schema add overhead; this
is a size budget rather than an exact token count.

## API endpoints added

POST `/api/curriculum/plan` creates or resumes a plan from learner_id, available_minutes,
session_type and optional requested_focus. The remaining paths use
`/api/learners/{learner_id}/study`:

- GET `/active`: current plan or null.
- GET `/{session_id}`: saved plan, progress and recap.
- POST `/{session_id}/start`: start/resume.
- POST `/{session_id}/activities/{activity_id}/open`: prepare/retrieve content.
- POST `/{session_id}/activities/{activity_id}/complete`: answer + submission_id UUID.
- POST `/{session_id}/activities/{activity_id}/skip`: skip without success evidence.
- POST `/{session_id}/complete`: finish after all activities are terminal.
- POST `/{session_id}/abandon`: retain evidence but end the active plan.

## UI changes

Today's Study adds time/focus selection, plan preview with reasons, beginner-profile
onboarding, start/resume/end, existing tutor-style lesson display, choice/free-answer
submission, feedback, skip/continue and recap. Active plans survive refresh/restart and
are not silently replaced by different requests. Learner switching clears study UI state;
only IDs are retained in browser storage. Existing chat/placement/profile screens remain.

## Tests and verification

Added 57 Phase 4 cases. **196 tests pass**, including all 139 prior-phase cases. Python
compilation and all frontend syntax checks passed. Two pre-existing upstream deprecation
warnings remain. Tests include synthetic learners A–D, ranking/focus/goal/prerequisite
behavior, time/variety/difficulty, migration preservation/rollback, restart, result replay,
event rollback, ownership, cancellation, stale generation and two app instances racing
to create the same learner's active plan. The previous migration test now expects v3;
its original-data preservation assertions remain intact.

Browser checks verified migrated placement, meaningful review priorities, fixed offline
content, missing-key recovery, skip, answer feedback, refresh and real-server restart.
A separate offline provider fixture verified generated grammar content through completion
and recap. No live-provider quality claim is made. See `PHASE4_VERIFICATION.md`.

## Limitations and Phase 5 recommendation

Catalog coverage is small, mostly foundations through an N3 sample, with one scored
question per activity and English fixed-template instructions. Scores, duration estimates,
level labels and weights require independent language review and empirical calibration.
Schema checks cannot prove generated Japanese correctness or difficulty. There is no
production authentication, automatic retention policy, complete course, voice, scheduling,
streaming, spaced repetition or final mastery algorithm. Anonymous IDs enforce query
scoping, not secure accounts; keep the app bound to loopback. Existing conservative profile
rules leave unassessed ability scores null; placement improves planning readiness.

Phase 5 should derive calibrated vocabulary/grammar/kanji mastery from topic-identified
performance and provenance now recorded in Phase 3, while preserving original placement.
Improve content coverage and distinguish repeated-template recall from broad understanding.
No Phase 5 work was implemented automatically.

Run instructions are in `README.md`; exact policies and architecture are in
`docs/curriculum-design.md`. Historical Phase 2/3 reports and archives are retained.
