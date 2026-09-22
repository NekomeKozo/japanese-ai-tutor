# Phase 5 completion report

Phase 5 adds persistent, deterministic vocabulary, grammar and kanji mastery to the
existing learner-event pipeline. It preserves placement, learning memory, curriculum
and provider infrastructure. There is no Phase 6 scheduling in this release.

## 1. Files added

- `PHASE5_REPORT.md`
- `PHASE5_VERIFICATION.md`
- `app/api/mastery.py`
- `app/mastery/__init__.py`
- `app/mastery/calculator.py`
- `app/mastery/catalog.py`
- `app/mastery/context.py`
- `app/mastery/maintenance.py`
- `app/mastery/migrations.py`
- `app/mastery/normalizer.py`
- `app/mastery/policy.py`
- `app/mastery/schemas.py`
- `app/mastery/service.py`
- `docs/mastery-design.md`
- `frontend/mastery.js`
- `tests/test_mastery.py`

## 2. Files modified

- `README.md`
- `app/assessment/repository.py`
- `app/curriculum/content.py`
- `app/curriculum/migrations.py`
- `app/curriculum/planner.py`
- `app/curriculum/policy.py`
- `app/curriculum/schemas.py`
- `app/curriculum/service.py`
- `app/learner/catalog.py`
- `app/learner/events.py`
- `app/learner/initialization.py`
- `app/learner/migrations.py`
- `app/learner/reset.py`
- `app/learner/sessions.py`
- `app/main.py`
- `frontend/index.html`
- `frontend/learner.js`
- `frontend/styles.css`
- `tests/test_curriculum.py`
- `tests/test_learning_memory.py`

Compared against the final Phase 4.5 archive. No prior source file was removed. Gemini,
OpenAI, provider configuration, tutor core, assessment scoring/selection and temporary
chat memory are unchanged. Temporary verification scripts/databases remain outside the
release folder and are not application dependencies.

## 3. Database migrations

Additive SQLite schema v4 runs within existing initialization transactions. New canonical
items are seeded; eligible historical performance events are conservatively normalized.
Migration neither rewrites original events nor replaces existing profiles. Actual local
upgrade preserved 146 original rows across 15 tables; backup and integrity checks passed.
Migration, rollback and idempotency are also covered on synthetic databases.

## 4. Mastery entities

- `mastery_evidence`: event-linked normalized observations, unique per event/topic/dimension.
- `topic_mastery`: learner/topic state containing overall estimate, separate confidence,
  dimension states, counts, timestamps, stability, status and algorithm version.
- `mastery_history`: meaningful versioned snapshots, not one row for every small change.

Canonical topics reuse the existing catalog. No duplicate learner/profile system exists.
Event and mastery updates commit atomically, and retry IDs cannot duplicate evidence.

## 5. Mastery Algorithm v1

For each dimension: historical posterior H=(1+sum(weight*score))/(2+sum(weight)); recent
posterior R uses the same prior over the latest six observations. Target=.7H+.3R. Replay
from .5 with a maximum .08 change per new observation. No evidence gives null.

Overall=.8*(dimension-weighted scores)+.2*(weakest dimension). Unknown slots use a neutral
.5 prior only for aggregation; their displayed scores stay null. An entirely unknown topic
has null overall score. This is not a percentage-correct formula or recall probability.
See `docs/mastery-design.md` for the complete equations and edge cases.

## 6. Evidence weighting

Weight=type*source*difficulty_modifier*hint_factor*quality/(1+prior_same_context_count)^2.
Type weights: recognition .55, recall .80, comprehension .75, application .90, production 1.
Source weights: placement .40, chat .55, quiz .80, exercise .85, curriculum 1, manual .80.
Difficulty modifier is clamped to .8–1.2. Positive hinted evidence uses .5; unknown hints
use .85. Legacy missing dimensions use .35 quality and weak recognition only. Explicit
correct-mode production uses .7 quality. Exposure/revealed positive answers do not establish
mastery. Partial credit is preserved. Duplicate events and paired recognition rows never
inflate overall encounter counts.

## 7. Confidence

Confidence=(1-exp(-effective_weight/12))*consistency*task_diversity*date_distribution*
min(1,independent_contexts/5). Consistency=max(.4,1-2*weighted_variance). Task diversity
and date distribution are bounded multipliers documented in the formula guide.
Recognition-only cap=.45; placement-only cap=.35. Overall confidence also multiplies
by .5+.5*measured_dimension_fraction. This stays separate from score and accuracy.

## 8. Vocabulary dimensions

Recognition .15, meaning .25, reading .20, production .40. Individual words are distinct
from group labels and component kanji. Recognition cannot fill production automatically.

## 9. Grammar dimensions

Recognition .15, understanding .20, application .25, production .40. Correction evidence
and focused curriculum exercises identify production explicitly; old ambiguous evidence
does not become production retroactively.

## 10. Kanji dimensions

Recognition .15, meaning .25, on-reading .25, kun-reading .25, production .10. Untested
production remains null. Reading evidence requires its tested context, displayed in UI.
Knowing 学生 does not grant general mastery of every reading of 学 or independent 生 mastery.
Production has no handwriting or stroke-order implementation.

## 11. Status logic

New means unassessed. Strong requires score>=.85, confidence>=.65 and >=8 independent
contexts; familiar requires .68/.35 and >=5 contexts; developing requires score>=.45
and >=3 contexts; otherwise learning. Overall strong also requires dimension coverage
and no measured dimension below .68. These are minimum gates, not guarantees after eight
answers. Kanji does not require production at the coverage gate, but its neutral unknown
slot makes the overall strong threshold especially conservative; review this during
calibration before Phase 6.

Needs-review identifies decline: >=8 observations, historical posterior>=.68, recent
weighted mean<.5 and >=3 failures in the latest four observations. Any declining dimension
can flag the overall topic. One error cannot trigger it; subsequent success can recover.

## 12. Placement initialization

Question/task metadata identifies actual tested dimensions. Placement remains low-weight
evidence with capped confidence. Existing placement results are immutable; historical
metadata gaps remain unknown and cannot manufacture production mastery.

## 13. Phase 3 integration

`process_event` accepts server metadata and updates affected mastery topics in the existing
transaction after original memory updates. Correct-mode evaluated text can contribute
production. Other chat observations remain conservative. Original fingerprints, context
limits, learner state, transcript storage and recent-practice semantics are preserved.

## 14. Phase 4 integration

The existing planner receives compact stored state, with bounded priority additions for
low mastery and decline. Supported weak dimensions select vocabulary reading/production,
grammar application/production or the existing kanji on-reading exercise. Fixed content
uses local templates; semantic content uses the existing provider and validation. Missing
mastery falls back to original planning. No review dates or scheduler are added.

## 15. UI

My learning now contains Japanese Knowledge with content/status filters, pagination, topic
details, separate dimension labels, confidence, last practice, reading contexts and recent
meaningful changes. Unknown skills say Not enough evidence. Existing practice summaries
remain available and are labeled as recent practice, not the new mastery measure.

## 16. API and maintenance

Read-only GET `/api/learners/{learner_id}/mastery` supports type/status/limit/offset;
GET `/api/learners/{learner_id}/mastery/{topic_id}` returns detail and history. Existing
local learner scoping is preserved; learner IDs are not authentication credentials.
The local `app.mastery.maintenance` CLI rebuilds derived state/history from normalized
evidence. No public mutation or debug endpoint is introduced. Query helpers expose
dimensions, review needs, low confidence, last seen and history for future phases.

## 17. Tests added

48 mastery cases cover the algorithm, all dimensions, synthetic A–D learners, hints,
partial credit, difficulty/source quality, repetition/diversity, unknown evidence,
placement, independent kanji/vocabulary identity, integration, retries, transactions,
API scoping, persistence/recompute equality, migration, reset and curriculum fallback.
Two existing schema-version assertions were advanced to v4.

## 18. Test results

All 298 tests passed in Python 3.12 (20.39s) and the actual app Python 3.14 (55.00s).
Both runs had two upstream deprecation warnings. Python compilation and JavaScript syntax
checks passed. Browser checks verified filtered lists, vocabulary dimensions and unknown
kanji dimensions using an isolated synthetic database. Actual local database preservation
and startup health passed with the existing configured Gemini provider. No paid model
calls were needed in Phase 5. See `PHASE5_VERIFICATION.md` for scope and limitations.

## 19. Known limitations

The 57-topic catalog, fixed prompts, weights and thresholds need Japanese-teacher review
and real-learner calibration. Independent contexts are a heuristic. Confidence is not a
statistical guarantee; upstream LLM grading can err. Many dimensions lack enough existing
content to establish high confidence. Kanji readings pool tested contexts within each
dimension, while retaining context provenance. No passive time-decay occurs. Maintenance
history replay is quadratic per topic and suitable for this small local prototype.
The prior local-only access/security limitations remain. Unknown prior slots conservatively
lower aggregate mastery; they do not indicate an observed failure.

## 20. Recommended Phase 6 work

Review and calibrate this formula first, especially prior strength, confidence thresholds,
dimension coverage, unknown kanji production and decline/recovery. Add diverse reviewed
questions and better hint/reveal instrumentation before relying on mastery for intervals.
Then design a separate scheduling layer consuming explicit versioned evidence and
uncertainty, with migration and deterministic scheduling tests. Do not reinterpret the
current heuristic stability as FSRS stability without validation. Phase 6 has not begun.
