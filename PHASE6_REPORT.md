# Phase 6 completion report

The daily loop now includes persistent, dimension-specific spaced reviews, time-bounded
queues and review-aware study plans. Timing is deterministic application logic. Existing
learner memory, mastery and study sessions are extended, not replaced. Phase 7 has not begun.

## 1–3. Algorithm, library and rationale

Use the maintained **fsrs==6.3.2** Python library behind `ReviewScheduler`. It fits Python
3.12/3.14, supports explicit UTC review times and JSON persistence, and allows random
fuzzing to be disabled. We retain FSRS model weights and add conservative application
policy limits. This is real FSRS with application policy version 1, not a custom algorithm
misrepresented as FSRS. Desired retention is .90; it is a model target, not a guarantee.

Sources: [PyPI](https://pypi.org/project/fsrs/6.3.2/) and
[maintainer documentation](https://github.com/open-spaced-repetition/py-fsrs).
The only FSRS import is in the adapter; curriculum and learner systems call application
interfaces. This permits replacing the scheduler without replacing the daily study loop.

## 4. Files added

- `PHASE6_REPORT.md`
- `PHASE6_VERIFICATION.md`
- `app/api/reviews.py`
- `app/review/__init__.py`
- `app/review/clock.py`
- `app/review/composition.py`
- `app/review/content.py`
- `app/review/maintenance.py`
- `app/review/migrations.py`
- `app/review/policy.py`
- `app/review/queue.py`
- `app/review/ratings.py`
- `app/review/scheduler.py`
- `app/review/service.py`
- `docs/review-design.md`
- `frontend/reviews.js`
- `tests/test_reviews.py`

## 5. Files modified

- `README.md`
- `app/assessment/repository.py`
- `app/curriculum/content.py`
- `app/curriculum/migrations.py`
- `app/curriculum/schemas.py`
- `app/curriculum/service.py`
- `app/learner/events.py`
- `app/learner/migrations.py`
- `app/learner/reset.py`
- `app/main.py`
- `app/mastery/maintenance.py`
- `app/mastery/migrations.py`
- `frontend/index.html`
- `frontend/study.js`
- `requirements-lock.txt`
- `requirements.txt`
- `tests/test_curriculum.py`
- `tests/test_learning_memory.py`
- `tests/test_mastery.py`

Compared with the final Phase 5 ZIP. All prior source files remain. Provider/configuration,
assessment scoring/selection, tutor core and Phase 5 scoring/policy/normalization are unchanged.
Temporary preview, simulation and backup scripts live outside the release source folder.

## 6. Database migration

Additive schema v5 adds review schedules/attempts and indexes in the existing migration
transaction. Existing measured dimensions receive staggered initial targets. Earlier
migration guards and scoped reset are updated for v5. The actual upgrade preserved all
172 original rows across 18 tables, with a private backup and successful integrity/FK
checks. No qualifying historical mastery existed locally, so no schedules were invented.
Populated-data bootstrap, rollback and repeat migration are tested on synthetic databases.

## 7. New entities

`review_schedules`: unique learner/topic/dimension, schedule ID, indexed due_at, suspension,
optimistic version and JSON state with FSRS card, interval, review/lapse counts, persistent
difficulty, timestamps and algorithm versions.

`review_attempts`: unique schedule/source-event pair, reviewed time, structured evidence,
mastery snapshot and previous/result state. It preserves score, rating, intervals and
lapse transitions without copying full conversations or learner answers into these tables.

## 8. Review states

Unseen catalog material has no schedule. First eligible retrieval creates Learning or
Review according to FSRS. A lapse from Review enters Relearning. Suspension is a separate
flag preserving the card; resume re-enables its existing due time. Difficult items are
not automatically suspended. Unsupported handwriting/reading targets are excluded from
executable queues rather than silently converted to different skills.

## 9. Rating mapping

Score <.45 → Again; .45–.69 → Hard; >=.70 → Good unless Easy gates all pass. Hints or
revealed metadata cap credit at Hard. Easy requires >=.90, explicitly unaided evidence,
quality>=.7, production/recall/application, appropriate known challenge, mastery>=.68
and confidence>=.35. Recognition and unknown hint metadata cannot yield Easy. No response
time penalty exists. Raw partial score remains in attempt/evidence history.

## 10. Interval and stability behavior

FSRS calculates the model state and proposed interval. Application v1 caps first intervals
at 3 days; low-confidence intervals at 7 days; needs-review at 1 day. Later daily growth
is capped at 1.2× Hard, 2.5× Good, 3× Easy; recognition at 1.6×. Stable per-target ±5%
spreading applies to intervals >=2 days; the final hard cap is 365 days. These are ceilings,
not guarantees. Minimum spacing is 15 minutes. Details and ordering are documented in
`docs/review-design.md`. FSRS stability/difficulty remain distinct from mastery estimates.

## 11. Lapses and relearning

Again from Review increments lapse_count and enters Relearning, preserving historical
mastery. Failed learning/relearning can return after 15 minutes in a later plan. Three
scored encounters in one UTC day require at least a day before returning. Four lifetime
lapses or four consecutive failures signal persistent difficulty and avoid minute-by-minute
repetition. Phase 4 receives a re-teaching signal; the lifetime-lapse flag is durable in v1.

## 12. Dimension-level scheduling

Vocabulary recognition/meaning/reading/production, grammar recognition/understanding/
application/production, and kanji recognition/meaning/on-reading/kun-reading have separate
targets. No untested dimension inherits another dimension's schedule. Contextual kanji
readings use reviewed word examples. Word production and reading can be graded locally;
grammar and meaning paraphrases reuse the existing semantic evaluator when needed.

## 13. Backlog and session capacity

Priority combines bounded overdue time, foundation/prerequisite value, goals, weakness,
confidence, lapses and persistent difficulty. It does not sort only by oldest date.
Queues use persisted indexed state, never the entire event history. They interleave
content types, avoid duplicate topics in a single plan, and fit estimated 2–4-minute tasks
within the requested budget and existing seven-activity plan limit. Remaining targets stay
due. Backlogs of 20+ raise the review allocation to .8 in balanced plans. Long absence
does not automatically mark mastery as failed.

## 14. Existing mastery bootstrap

Only measured dimensions with stored evidence qualify. Bootstrap seeds one conservative
card without pretending that many reviews occurred. Strong/high-confidence dimensions
start no earlier than UTC day four; other targets start the next UTC day. A deterministic
ten-target-per-day allocation spreads load, with 23-minute slots from 09:00 UTC. Original
last-seen time is retained, review_count starts at zero and no fake attempt is created.
Re-running startup is idempotent. Local dates are shown to the learner.

## 15. Phase 3 integration

The existing event transaction records the learning event and original memory updates,
then updates mastery, then scheduling and attempt history. Eligible ordinary learning
retrieval can establish schedules too. Ambiguous quality<.5 chat/history signals do not
act as live retrieval trials. Existing event fingerprints and submission IDs prevent
duplicate processing. Any storage failure rolls back all related changes.

## 16. Phase 4 integration

StudySession remains the sole session system. Optional review target/version fields on
planned activities preserve old plan parsing. The planner uses due targets first and
fills remaining time through its existing curriculum. Requested focus and active plans
are respected. Opening/grading rechecks target versions and suspension; stale plans cannot
double-reschedule a target already changed by other practice. Skip remains due. Provider
failure preserves the plan and schedule for retry.

## 17. Phase 5 integration

Scheduling consumes normalized evidence and compact dimension score/confidence/status.
It never changes mastery itself or asks the LLM to set mastery/timing. Existing mastery
version/formula is unchanged. Review completion feeds the same evidence pipeline, with
actual target dimension and tested reading context. The review's next date is saved in
the same transaction as the activity result.

## 18. APIs and maintenance

GET `/api/learners/{id}/reviews/due?minutes=10&skill=grammar` and GET
`/api/learners/{id}/reviews/forecast?timezone=Asia/Manila` expose compact queue/forecast
information, not FSRS stability/difficulty. Existing curriculum plan/start/open/answer/
skip/complete endpoints execute reviews; no duplicate session API is introduced.

The local-only maintenance CLI can rebuild one learner/topic from stored attempt inputs,
or suspend/resume one dimension. Replay retains original attempts/events and suspension
while invalidating stale plans. Bootstrap-only cards without attempts remain unchanged.
Timezone-aware UTC storage and explicit clocks are used throughout scheduling; forecast
uses the supplied IANA timezone and the browser formats dates locally.

## 19. UI additions

Today's Study has a Daily Review card, per-kind counts, a time budget, manageable selected
load and local today/tomorrow forecast. Start Review resumes or creates the existing study
session flow. Activities show progress and dimension, feedback shows next review, and the
existing recap records successes, struggles and skips. Production headings use English
cues to avoid giving away the Japanese answer. No product redesign was introduced.

## 20. Tests added

57 cases cover ratings, partial credit, hints, source-quality gates, deterministic FSRS,
bounded growth, lapse/relearning, persistent difficulty, same-day caps, independent
dimensions, synthetic A–F cases, queue priorities/capacity, long absence, suspension,
retry/restart, transaction rollback, content/grading failures, stale submissions,
bootstrap/migration/rollback, timezone/day boundaries, answer secrecy and prompt variety.
Existing schema-version expectations now target v5.

## 21. Test results

Final actual-environment run: **355 passed** on Python 3.14, 66.76s, two pre-existing
Starlette/AnyIO warnings. The final Python 3.12 suite also passed all 355 tests in 26.37s.
Python compilation and JavaScript syntax checks passed. Isolated browser
verification completed a correct production answer, incorrect kanji reading and a skip,
confirming due counts, next dates and recap. No paid model calls were made in Phase 6.

The 42-day simulation of 100 targets introduced 10/day produced 219 subsequent reviews,
with a peak of 14 reviews/day. This checks load stability for that synthetic pattern;
it is not a real retention study. See `PHASE6_VERIFICATION.md` for detailed scope.

## 22. Known limitations

FSRS weights, rating gates and policy caps are not calibrated on this tutor's learners.
The desired-retention target is not a measured guarantee. Phase 5's small catalog and
conservative confidence may hold some intervals below 7.35 days for a long time. Fixed
content has modest prompt variety; semantic grading can err. Current same-day retries
require a later study plan rather than modifying an active plan. Unsupported handwriting
and unreviewed readings are not executable. No automatic parameter optimizer runs.
The existing local prototype has learner-ID scoping, not production authentication.

## 23. Recommended Phase 7 work

Polish the daily learning journey, review/new-material navigation, responsive layouts,
accessibility and progress presentation using these stable APIs. Expand reviewed exercise
variety and calibrate evidence confidence/retention before making strong learning claims.
Retain deterministic scheduling and transaction/idempotency protections. No Phase 7 work,
notifications, social/payment features, voice or listening SRS was implemented.
