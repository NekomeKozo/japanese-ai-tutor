# Phase 3 learning memory design

This describes the Phase 3 foundation. Phase 4 retains these services and adds schema
v3, curriculum topics and source `curriculum`; see [curriculum-design.md](curriculum-design.md).
The current controlled catalog has 78 entries and state retrieval permits 200 topics.
The compact tutor context and original chat observation-catalog limits remain unchanged.

## State and history

The existing assessment repository remains the single SQLite connection boundary.
Schema v2 is additive. `learner_profiles.profile_json` remains the immutable Phase 2
placement snapshot. `learner_state` holds current identity, level, preferences and dates;
`skill_state` holds the placement baseline, current estimate and bounded recent scores.
This keeps tutor retrieval independent of lifetime history size.

`learning_topics` is a fixed 36-entry catalog (including ten generic categories).
`learner_topics` holds encounters, correct/incorrect totals, rolling performance and dates.
Vocabulary words carry readings/meanings; kanji reading and meaning have distinct topic
keys. `mistake_state` aggregates canonical error keys rather than free-text sentences.
`learning_events` is append-only during normal use and retains source and normalized
evidence. `tutor_sessions` owns session lifetime/version; `conversation_turns` stores
each user/reply exchange exactly once. `skill_history` records only changed estimates.

Nine new tables are added to the existing four. No second database, external service,
provider SDK, vector store or dependency is introduced. Current state can be queried
without loading transcripts/events. Events preserve evidence provenance for future
adaptation. The developer reset is the deliberate exception to append-only history.

## Migration and initialization

Startup accepts versions 0, 1 and 2; unknown future versions are refused. Version 0 first
creates Phase 2 schema v1. A `BEGIN IMMEDIATE` transaction creates v2 tables and catalog,
backfills completed placements, and advances `user_version`. If anything fails, v1 data
and schema version remain intact. Profile insertion and Phase 3 initialization for a new
assessment completion also share a transaction. Backfill is idempotent and does not
score placement twice. Existing questions, answers, snapshots and initial profiles are
unchanged. Migration-created event timestamps represent import time, not original study
time. Original assessment timestamps remain in the preserved snapshots.

Unassessed learners receive Beginner as a starting instruction, null ability/overall
scores, zero confidence and no invented strengths. Retaking placement retains Phase 2's
new-learner behavior; merging existing identities is not implemented.

## Evidence boundary

The provider receives `ObservedTutorResponse`, extending the original teaching response
with at most eight observations. Each has type (`performance`, `concept_explained`,
`requested_help`), skill, bounded topic string, nullable score/difficulty and at most five
error tags. Performance requires a score in [0,1]; exposure requires null. Unknown fields,
invalid types/ranges and malformed observations are discarded individually; a valid
teaching response still commits. Malformed teaching JSON never changes stored state.
The original Phase 1 response contract remains unchanged for clients and transcripts.

The application normalizes aliases and deduplicates canonical topics within one reply.
Unknown topics become `other_<skill>` exposures with no score or mistake impact. Only
catalog topics can supply scored evidence. Catalog skill/difficulty override model
classification/difficulty for updates. Error tags are recognized and skill-compatible.
Models cannot set level, confidence, preferences, timestamps, learner identity or table
values. The internal `LearnerService.record(LearningEvent)` boundary supports later quiz
or review modules; no public arbitrary-event ingestion endpoint is exposed.

## Update policy

- Topic window: latest eight scored encounters; exposure doesn't affect correctness.
- Correct: score >= 0.8. Incorrect: score < 0.6. Partial scores remain in the rolling mean.
- `needs_review`: >= 3 scores with mean < 0.6.
- `strong`: >= 4 scores with mean >= 0.8 and last three all >= 0.6.
- `familiar`: >= 3 scores with mean >= 0.7. Otherwise `learning`, or `new` before
  scored evidence (repeated exposure moves new to learning).
- Mistakes aggregate lifetime occurrences and up to 50 recent dates within 30 days;
  three recent errors activate the pattern. Familiar/strong evidence on that topic
  marks its mistake improving. Old patterns are inactive in profile reads and excluded
  from active tutor context. Lifetime counts remain available.
- A saved exchange contributes at most one averaged scored update per skill regardless
  of tag count. Every fifth update considers the last eight scores: mean >= 0.8 at a
  suitable difficulty can add 0.15; mean < 0.4 on sufficiently easy content can subtract
  0.15. Catalog difficulty must be at least estimate−1 to raise and at most estimate+1
  to lower. Estimates are clamped to [0,14] and placement baseline ±1. History rows are
  added only when an estimate changes. No automatic overall level/confidence update.
- Null placement estimates remain null while accumulating recent performance. Script
  recognition labels preserve the sampled placement result. Later calibration/reassessment
  can replace this conservative policy through the service, not model-authored profiles.

## Atomicity, retries and isolation

Saved chat requires a learner ID, an owned session ID and a request UUID. Fingerprints
cover the entire normalized request except request ID. Identical retries replay the
stored validated teaching reply without a second LLM call. Conflicting reuse returns
409. A local busy guard prevents overlap; optimistic session versions protect writes
across processes. A transaction commits the exchange, session version/count, events,
topic/mistake state and skill history together. Failed/cancelled provider calls make no
updates. A failed transaction rolls all components back. A model call can still incur
cost before a conflict/failed commit; only successfully committed replies are replayable.

Read/write queries are scoped to learner/session ownership. IDs are anonymous locators,
not authentication. Legacy temporary conversations cannot switch to a different named
learner. Keep the app on loopback; one worker retains legacy conversation compatibility.
No secrets, complete prompts or provider internals are persisted. Raw user sentences and
validated teaching replies are stored once as conversation turns.

## Context and API contracts

`LearnerService.profile` exposes skills, initial placement, weak/strong/recent topics,
topic memory, common mistakes, recent performance, preferences and timestamps. It reads
at most 50 topic rows (more than the entire current catalog) and 20 mistake rows.
`build_context` deterministically selects up to five weaknesses, five active recent
mistakes, three strengths and five recent topics, plus major skill labels, a 400-character
starting recommendation and preferences. The UTF-8 summary is capped at 4,000 bytes,
dropping lower-priority lists first. No lifetime history is included.

Session retrieval returns the latest 12 exchanges for the UI. Model history uses up to
`MAX_HISTORY_TURNS`, trimmed further to 12,000 characters of complete user/assistant
pairs. Assistant history keeps bounded explanation/message text and practice/correction
context; observations never reappear in conversation history. The new user message is
separately limited to 4,000 characters. Static teaching/schema/catalog instructions are
additional overhead. These caps conservatively limit size, not exact model token counts.
There is no summarizer call or semantic retrieval.

Saved preferences directly drive instruction language, correction style, readings and
romaji. Difficulty preference overrides the estimated starting level. Goals are compact
context only. My learning exposes state and recent activity, not advanced analytics.
Closed sessions can be viewed; a new session is needed to send further messages.

## Future boundary

Phase 4 can read the profile service's `skills`, `weak_topics`, `recent_topics`, recent
performance and preferences to plan curriculum. This phase does not choose lessons,
schedule reviews, promote levels, implement spaced repetition or calculate final mastery.
Authentication, retention policy, identity merging, larger reviewed catalogs and empirical
calibration remain future work. Catalog growth should ship through a new schema/data
migration rather than accepting arbitrary LLM-created rows.
