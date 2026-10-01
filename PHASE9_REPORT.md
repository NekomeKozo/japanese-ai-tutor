# Phase 9 — JLPT practice system

Status on 2026-10-01: implementation and local verification complete; deployment
and live acceptance pending. Phase 10 has NOT started. No audio, accounts,
monetization, native mobile stack, or official-score claims were added.

## Initial audit and baseline

The canonical repository is `NekomeKozo/japanese-ai-tutor`, branch `main`; the clean
Phase 8 checkpoint was `7d3c203`. No existing manual Phase 9 implementation was
discarded. Fresh baseline: **488 backend tests including 9 PostgreSQL tests, and
22 frontend tests passed**. Existing schema was 6: placement, learner memory,
curriculum, mastery, review and conversation migrations form an additive chain.
Phase 9 extends that chain to 7.

The pre-implementation audit covered placement banks and normalization, learner
events, mastery processing, review scheduling, curriculum, RAG/provider fallback,
ownership, navigation, progress/history, reusable tests, persistence design,
selection, scoring, bank versioning, mock privacy and rollback. Placement stays
separate. Existing `process_event` remains the learning integration boundary;
there is no parallel learner model or scheduler. Existing same-origin ownership,
access gate, CSP, request/rate limits and scope enforcement cover the new API.
No Render, Supabase, extension or environment changes were needed.

## Architecture and content

`app/jlpt` owns validated schemas, a startup-loaded bank, deterministic selection
and scoring, transactional sessions, additive migrations, topic definitions and
development-only candidate authoring. `app/api/jlpt.py` exposes the learner-owned
routes. `frontend/jlpt.js` adds a lazy-loaded Study subflow using vanilla JavaScript.

Bank version: **jlpt-v1**, 80 original application-authored questions:

| Level | Vocabulary | Kanji | Grammar | Reading | Total |
|---|---:|---:|---:|---:|---:|
| N5 | 10 | 10 | 10 | 10 | 40 |
| N4 | 10 | 10 | 10 | 10 | 40 |

All eight types are represented: vocabulary meaning/usage, kanji reading/meaning,
grammar choice/usage, sentence completion and reading comprehension. Twenty short
original passages cover notices, messages, schedules and everyday contexts.
Multiple choice dominates; three items use fixed accepted reading answers.
The smaller bank prioritizes inspectable content over the suggested 160-item target.
Prompts, distractors, answers and explanations were reviewed during implementation;
there has been **no independent Japanese-teacher review or empirical calibration**.
N4 includes prerequisite structures. This is study content, not official coverage.

Startup rejects duplicate IDs/content, unsupported types, invalid topic/skill or
mastery-dimension mappings, blank/overlong answers, inconsistent choices and missing
passages or required reading context. Only approved items are selected. Stable IDs,
item versions and complete per-session snapshots protect old history from bank edits.

## Sessions, selection and scoring

Schema 7 adds `jlpt_sessions`, `jlpt_session_questions` and `jlpt_attempts`, with
foreign keys, owner queries, uniqueness constraints and one-active-session policy.
SQLite transactions and PostgreSQL advisory locking protect starts, answers and
finishes across workers. Matching request UUIDs replay safely; conflicting retries
are rejected. Answer persistence and learning updates share one transaction.

Quick defaults to 5 questions; standard, focused and weakness modes to 10; mock
to 20. API counts are bounded to 5/10/20 and actual available content. Selection
filters approved level/section items, deprioritizes the last 40 attempted IDs, then
uses deterministic request-seeded ordering. Mixed sessions balance sections.
Weakness mode uses existing topic evidence (at least three recent observations,
average below .6); without meaningful matching evidence it uses balanced practice.
Mock mode groups questions by section.

The backend applies the existing conservative NFKC/whitespace/case/terminal-punctuation
normalization and exact approved choices/readings. No broad free-form AI grading,
partial credit, romaji conversion or inferred alternatives. Results show correct,
total, accuracy, answered count, section breakdown and answer explanations.
Unanswered questions count as incorrect on completion. There is no official scaled
score, JLPT certification, pass prediction or automatic placement promotion.

Optional persisted deadlines allocate 60 seconds per non-reading question and 120
per reading question. Reload does not restart timing. Expiry completes atomically
when next observed by the server. Practice reveals feedback immediately; mock
withholds feedback, scores and mastery/review updates until completion. Abandoning
a mock produces no performance evidence. History is bounded to the last 30 sessions.

## Learning integration and RAG

Each scored answer enters the existing quiz/performance event pipeline exactly once
with stable event identity, topic, JLPT session/question/bank metadata, recognition
or recall context and supported mastery dimensions. Practice updates immediately;
mock completion applies deferred events atomically. Vocabulary/grammar/kanji evidence
updates normal mastery and review scheduling. Reading comprehension updates learning
memory without inventing word mastery. Placement is not rewritten.

Viewing results makes no AI call. An explicit explanation follow-up records at most
one non-performance exposure event, prepares Tutor text, and preserves any existing
draft. Sending it uses the existing Tutor/provider/RAG path. Browser testing found
and fixed a draft-loss race while Tutor initialized its saved session.

The development-only `scripts/author_jlpt_candidate.py` reuses KnowledgeService,
provider factory, bounded low-trust retrieval context and copying protections.
It validates canonical topics and duplicates, forces candidate status, and saves
private provenance under ignored `knowledge_base/jlpt_candidates/`. It refuses
staging use and path redirection. No candidate is automatically published. Offline
tests used synthetic retrieval/provider fixtures; no real private-reference candidate
generation or authoring API quota was consumed. See `docs/jlpt.md` for review steps.

## Frontend and accessibility

Study offers Personalized study / JLPT practice without another main navigation item.
Setup, answer input, feedback, results, history and resume use existing styles. Native
radio groups, fieldsets, text labels, focus handling and status/error announcements
support keyboard use; the timer avoids per-second screen-reader announcements.
Failed answers retain input and retry identifiers. Learner changes clear cached state.
Reload restores submitted progress; section navigation also preserves unsent drafts.

## Validation completed locally

- **526 backend tests passed, including all 13 PostgreSQL tests**, using the existing
  disposable local PostgreSQL cluster. Two existing deprecation warnings remained.
- **29 frontend tests passed**, plus JavaScript syntax and whitespace checks.
- After the final reading-topic label adjustment, 10 relevant bank, integration and
  authoring cases passed again. The Tutor handoff repair has frontend regression coverage.
- Source and full Git-history deployment audit passed with no secret/private-file findings.
- Added coverage includes bank validation/coverage, mode selection, weak/recent topics,
  all section/level evidence mappings, ownership, malformed requests, replay, persisted
  timing, hidden mock feedback, snapshot history, abandonment, additive migration and
  injected rollback failures. PostgreSQL covers concurrent start/answer/finish and atomicity.

Local browser acceptance used a disposable learner and fake Tutor provider: completed
N5 quick (4/5), full timed N4 mock (5/20), reload after answers and during timer,
all feedback/results/history flows, fixed reading normalization, retained unsent input,
standard/weakness setup, abandonment, reading passage and early completion, and an
explanation-to-Tutor send. Mock screens were checked for feedback leakage before finish.
Progress retained its beginner placement estimate.

Emulated phone/tablet/desktop sizes were exercised. Actual observed content widths
299, 368, 738 and 1240 CSS pixels matched document scroll widths: no horizontal
overflow in checked question/results views. Choices, Japanese passages, timer, answer
button, navigation and review remained usable. **No Phase 9 actual-device phone test
has been claimed**; the owner's prior phone acceptance concerned Phase 8.

## Deployment and live verification

Pending at this checkpoint. Existing Render service and Supabase database will be
retained. No settings or credentials need changing. Live checks and CI evidence will
be recorded here after the normal push and deployment.

## Performance and limitations

Bank validation happens once on startup. Selection/scoring/restore/results make zero
model calls; history uses a bounded aggregate query. The UI caches the catalog, loads
JLPT lazily and uses a local display timer without second-by-second server polling.
No numerical load-test or production latency improvement is claimed.

Bank size limits variety; independent editorial review and expanded coverage remain
future improvements. Timings and levels are approximate study aids. History shows the
latest 30 sessions. Deadlines finalize on interaction rather than a background task.
Fixed free-input normalization is intentionally narrow. Existing browser-owned staging
access remains, without cross-device accounts. No audio or N3–N1 content was added.

## Changed files and rollback

Added: `app/jlpt/` (schemas, bank, two JSON banks, selection, scoring, migrations,
service, topics, authoring), `app/api/jlpt.py`, `frontend/jlpt.js`,
`scripts/author_jlpt_candidate.py`, `tests/test_jlpt.py`, `docs/jlpt.md`, this report.
Modified: `.gitignore`, `app/main.py`, `app/assessment/repository.py`, existing
learner/curriculum/mastery/review/conversation migration compatibility guards,
learner catalog/reset, mastery/review maintenance guards, frontend index/shell/styles,
README, frontend tests and existing schema-version/PostgreSQL tests.

Checkpoints: original Phase 8 `7d3c203`; schema-tolerant checkpoint `5a88d20`;
**rollback-compatible Phase 8 checkpoint `09db650`**, also retaining new canonical
topics; backend/bank checkpoint `9787ce3`. Revert later application commits normally,
retaining additive schema-7 tables and topic identities. Do not destructively downgrade
the database, delete learner records, reset Supabase, or force-push. The older Phase 8
checkpoint alone cannot safely interpret the newly persisted topic identities.

**Phase 10 has NOT started.**
