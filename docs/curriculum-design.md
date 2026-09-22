# Phase 4 curriculum design

## Integration and authority

`CurriculumService` reads `LearnerService.profile`, existing topic/mistake state and a
bounded recent study distribution. The pure planner determines eligible topics, ranking,
review/new strategy, skill-specific difficulty, ordering and time. It performs no model
calls and uses no randomness. Fixed inputs and an injected clock yield fixed selections.
UUIDs and creation timestamps differ only when a genuinely new plan is saved.

The provider cannot select topics or change the plan. `ContentService` asks the existing
`LLMProvider.generate` for one already selected activity and validates a `Lesson` schema.
The UI renders the resulting teaching material through the Phase 1 `TutorResponse`
renderer. Answers use the existing Phase 2 `AnswerEvaluator`. Completed performance uses
the Phase 3 `process_event` engine. There is no second tutor/provider/progress subsystem.

The modules deliberately consolidate related pure functions in `planner.py` instead of
creating a file per small function. `policy.py` holds tunable policy/goal weights;
`catalog.py`, `schemas.py`, `content.py`, `service.py` and `migrations.py` separate the
content, validation, generation, persistence and upgrade boundaries.

## Catalog and prerequisites

The 63-topic catalog contains 26 grammar topics, 13 vocabulary units, 12 kanji units,
five reading units, five sentence-writing activities and two script foundations. Seven
broader tags bridge existing placement memory directly into review activities and are
not offered as new material. All keys use the Phase 3 canonical topic namespace; the
combined learning catalog now contains 78 bounded entries. Catalog graph validation
rejects missing prerequisite IDs, cycles and invalid fixed answer choices.

Prerequisite classification:

| Evidence | Status and effect |
| --- | --- |
| familiar/strong topic | satisfied |
| needs_review topic | not_satisfied; block dependent topic |
| encountered with scored mean >= .6 | partially_satisfied; allow with priority penalty |
| no reliable topic evidence, but >= 2 placement observations, confidence >= .35 and skill ability >= prerequisite difficulty + 1 | partially_satisfied placement prior |
| otherwise | unknown; block dependent topic |

Exposure alone never satisfies prerequisites. Blocked nearby topics raise the priority
of their missing/weak foundations. Merely placing a prerequisite earlier in today's plan
does not count it as learned; dependents become eligible in a later plan after evidence.
Explicit focus cannot bypass gates. Learners can ask the ordinary tutor about advanced
topics outside this automatic curriculum.

## Difficulty and ranking

Ability comes from the relevant skill's current estimate, not the overall level. A null
estimate conservatively starts at zero. With at least three recent observations, mean
below .5 lowers the planning target .5; mean >= .9 raises it .5. New topics must fit within
target + `maximum_difficulty_jump` (default 1). Previously scored topics may be reviewed
with one additional point of catalog headroom, while their delivered target remains
capped at ability + 1. Struggling topic review is simplified another .5. Difficulty stays
within 0–14. A goal or chat difficulty preference never raises this ceiling.

Candidate priority is an additive heuristic, not a mastery score. Default components:

- Base 1 plus skill/goal weight; goal-specific topics add 2.
- Needs-review adds 4; an active pattern with >= 3 recent mistakes adds 3.
- Low topic performance adds up to 1, scaled by up to three scored encounters; one
  mistake therefore contributes only a small signal. Strong status subtracts 2.
- Review age adds up to 1.5 across 30 days; age alone cannot overwhelm repeated failures.
- A needed foundation adds 1; broad noncatalog skill weakness adds 2.
- A skill with < 15% of completed study minutes during the last seven days adds 1.5.
- Each appearance in the last four started sessions subtracts 1.3. Completed/skipped
  activities count, but merely planned activities do not.
- Difficulty distance costs .2 per point. Each partial prerequisite costs 1.5.

Strong sampled kana is omitted from ordinary balanced plans unless recent scored kana
performance deteriorates; explicit script focus can still request it. Historical broad
placement tags have direct review candidates so they are not lost to the newer catalog.
Goal weights favor grammar/reading/kanji for JLPT, vocabulary and production for
conversation, practical travel topics for travel, and relevant work/university topics.
No goal is a curriculum-level override.

Reasons are machine-readable codes with concise human text. Numeric priorities and
prerequisite scoring internals are not included in public plans. Ranking ties have stable
topic-based ordering. Selected activities receive a soft repeated-skill penalty of 2 to
encourage variety without forcing equal distribution.

## Review strategy and time allocation

Start at .5 target review share, add .05 per weak topic (up to .2), adjust by bounded recent
skill accuracy (+/− .2), add .1 for low placement confidence and .2 after a >= 30-day gap.
Strong recent performance reduces review. New-material requests reduce the ratio .15;
review requests target 1. Other requests clamp to .25–.85. The strategy name is quick,
review-heavy, progression, goal-focused or balanced according to length and evidence.
Long absence uses the last substantive learning event, so opening a chat window does
not erase the gap. No spaced-repetition due dates or retention model is introduced.

Eligible topic exposure determines review versus new material. The planner selects
candidates toward the target ratio, then allocates minutes toward it. Actual review/new
minute shares are persisted separately from the target. If too few eligible review/new
topics exist, the other pool fills the plan and the note explains the shortfall. A fresh
learner cannot receive fabricated review history.

Maximum activity counts: one for 5–9 minutes, two for 10–14, three for 15–24, five for
25–44, seven for 45–60. A plan uses at most 12 minutes per activity and never exceeds
available minutes. Small candidate pools can leave some requested time unused; the UI
shows the actual estimate. Review is ordered before new material, with easier work first.
This offers a warm-up without manufacturing an extra activity or duplicate evidence.
If eligibility yields nothing, a safe introductory foundation is used, with an honest
note. A sentence-writing focus may first receive basic grammar when prerequisites are
missing. This is a foundation fallback, not an advanced-topic bypass.

## Database v3 and lifecycle

Startup's existing transaction advances v1 → v2 → v3 as needed. Schema v3 inserts
controlled topic entries and adds two tables; old tables/rows are preserved:

- `study_sessions`: learner ownership, planned/in_progress/completed/abandoned state,
  immutable serialized validated plan/request, catalog version, lifecycle timestamps.
- `study_activities`: structured topic/skill/type/difficulty/duration, order, state,
  generated lesson once, result, unique submission ID/fingerprint and completion time.

A partial unique index permits one planned/in-progress session per learner. Duplicate
planning requests—including different time/focus requests—resume that plan. End/abandon
it explicitly to plan again. Reads do not regenerate or re-rank. UUID-scoped ownership
checks apply to every session/activity operation; they remain anonymous local identity,
not production authentication. The developer reset now clears the selected learner's
study rows as well as learning memory and preserves original placement/other learners.

Activities advance in order. Opening cached content costs no model call. Opening fresh
content commits its lesson and an exposure event together. Only after a valid answer is
graded does completion atomically save the result, performance event, topic/mistake/skill
updates and lifecycle event. Skips create lifecycle evidence only, never success/failure.
Finishing requires every activity completed or skipped; recap derives only from those
results. Abandoning preserves already completed evidence. Session plan JSON stays stable.

Identical completion retries replay saved results; conflicting reuse returns 409.
Busy guards prevent same-process overlapping content/grading requests. Transactions
recheck session/activity state after provider calls, preventing stale generation or
grading from reopening a skipped/abandoned activity. Cross-process planning races return
the winner's plan. Cancellation releases guards without committing partial evidence.
Model cost may still occur before a conflict/failed commit; only committed content/results
can be replayed. Migration failure rolls back to the preceding schema and data.

## Content, grading and event provenance

Fixed vocabulary, kanji, script and reading templates use deterministic choice scoring.
Grammar/writing use one on-demand generated lesson, not a generated curriculum. Required
fields include exact topic/difficulty, bounded explanation/examples, one question, choices
or semantic reference answers, and post-answer feedback. Wrong topic/difficulty, invalid
answer-choice relationships, empty list entries and oversized output are rejected.
Malformed output permits one retry (two calls total); transport/provider failures return
immediately with the plan intact. A valid schema cannot establish linguistic correctness.

Answer keys and post-answer feedback stay server-side until graded completion. The
existing evaluator accepts exact semantic reference answers without another LLM call and
grades alternate free responses through its structured output contract. Unavailable
grading leaves the activity open and records no performance. Scores are evidence from
one activity, not complete mastery of its topic/unit.

Performance events retain source `curriculum`, the selected canonical topic, skill,
application-selected difficulty, score and session ID. Metadata includes activity ID,
activity type, purpose, grading method and normalized error provenance. Original prompts,
API keys and provider internals are not stored. Learning state is updated by the Phase 3
engine with its existing conservative rules; this phase does not introduce mastery scores.

## Token and data limits

Planning, fixed templates, resume, skip and recap use zero LLM calls. Generated lesson
context is capped at 4,000 UTF-8 bytes: only selected topic/title, skill/level, difficulty,
duration/type/purpose, supported preferences and a relevant-weakness boolean. It contains
no conversations, placement answers, full profile, lifetime events or all-topic catalog.
Static generation instructions and response schema add overhead; the cap is not an exact
tokenizer count. Raw lesson output is limited to 14,000 characters, with smaller field
bounds; the existing configured provider output/timeout limits still apply.

Ordinary Phase 3 chat keeps its original small observation-tag vocabulary and existing
history/context caps. Learner profile state retrieval is bounded to 200 topic rows to
cover the expanded controlled catalog; compact tutor selection limits remain unchanged.
Study distribution is aggregated by SQL; only counts/minutes and the latest substantive
learning timestamp are returned, not an event-history dump.

## Validation, limitations and next phase

Offline tests cover cold start, Phase 2-only and mature memory, synthetic learners A–D,
weakness/recency/repetition/goal weights, prerequisites, uneven skills, time/variety,
schema v2 preservation/rollback, idempotent resume and results, ownership, atomic failure,
provider/schema failure, cancellation and concurrency. Browser tests exercise fixed and
mock-generated lessons. See `PHASE4_VERIFICATION.md` for the completed run.

The prototype has one scored question per activity, a small catalog with sparse upper
levels, English fixed-template instructions, approximate time allocation, and uncalibrated
heuristics. The application checks labels/contracts but cannot prove model content quality
or prevent all accidental solution hints. No real-provider call was made without a key.
Raw learner answers to study activities are not retained; the saved result/reference and
hashed submission identity are sufficient for this phase's replay and performance history.

Phase 5 can derive richer vocabulary/grammar/kanji mastery from these topic-identified
events and evidence provenance. It should improve calibration/content coverage before
claiming mastery. No Phase 5 scoring, spaced repetition, flashcards, daily schedule,
voice, conversation scenarios or advanced analytics is implemented here.
