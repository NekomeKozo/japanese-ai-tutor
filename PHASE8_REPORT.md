# Phase 8 — Adaptive Japanese Conversation System

Status: implemented, regression-tested and deployed as `5c51e3e`; live flow checks
recorded on 2026-10-01 (Asia/Manila). Provider-log and actual-phone acceptance remain
pending. This report distinguishes local fixtures from
actual provider checks.

## Initial audit and checkpoint

The canonical repository was clean on `main` at Phase 7.5 commit `56ee8f1`, connected
to `NekomeKozo/japanese-ai-tutor`. No existing manual Phase 8 implementation was found.
Private reference/index files and environment files remain ignored. Initial learner
schema was 5; knowledge has its own migration/version handling.

The baseline was 449 backend tests (including six real PostgreSQL tests) and 15
frontend tests. One initial PostgreSQL setup failure was resolved by starting the
disposable local server; the six database tests then passed. No learner reset was used.

Existing architecture: FastAPI serves vanilla frontend files. AssessmentRepository
owns the transactional SQLite/PostgreSQL migration chain through learner, curriculum,
mastery and review migrations. SessionService owns tutor_sessions, conversation_turns,
request replay, optimistic session versions and lifecycle events. TutorService builds
the existing system instructions plus bounded saved history, learner preferences and
learning context. Structured observations enter the existing learner/mastery pipeline.
KnowledgeService inserts bounded low-trust reference messages, guards copying, and
degrades on lookup failure. The common provider handles bounded Gemini-to-Groq failover.
Access cookies, resource ownership, same-origin checks, scope checks, rate limits and
CSP already existed. Tutor UI used one composer, persistent session restoration and
Progress history; these were extended rather than replaced.

The pre-implementation audit proposed an additive state table, application-authored
scenarios, conservative derived difficulty, the existing chat endpoint, and no dashboard
changes. Main risks were partial session creation/completion, duplicate evidence,
cross-worker races, scope bypass and unnecessary model/retrieval calls.

## Architecture and scenarios

New package `app/conversation/` contains schemas, catalog, migration and service.
Eight deterministic scenarios: introductions, restaurant, convenience store, directions,
train station, hotel, coworker and appointment. Each defines key, title, description,
learner/tutor roles, goal, opening line and a suggested minimum level. The minimum is
guidance, never an access restriction. Selection and opening require zero AI calls.

`conversation_states` references existing tutor_sessions and learner_state. It stores
scenario, status, starting level, correction policy and timestamps, without a second
transcript. A partial unique index permits one active practice per learner. Start
creates the session, lifecycle event, practice state and staging ownership in one
transaction. Finish closes both records and writes the existing end event once;
repeated finish is safe. General session close cannot silently abandon active practice.

Learner schema 5→6 is additive and transactional. Old migration modules accept schema
6. SQLite and PostgreSQL tests cover preservation, repeated initialization and rollback
on migration failure, including learner/session/evidence and private knowledge data.
Nothing resets the database or changes extensions, credentials or hosting services.

API additions:

- `GET /api/conversation/scenarios`
- `POST /api/learners/{learner}/conversations`
- `GET /api/learners/{learner}/conversations/active`
- `GET /api/learners/{learner}/conversations/{session}`
- `POST /api/learners/{learner}/conversations/{session}/finish`

Messages still use `POST /api/chat`. The server forces chat semantics for roleplay,
adds the authored opening only to initially empty model history, and layers scenario
instructions onto existing tutor/learner instructions. Stored replies use the existing
schema; exercise is null. Replay avoids another model call, retrieval or observation.
Optimistic commit prevents a response from being saved after another worker finishes.

## Corrections, adaptation and recap

Policies are important_only (meaning-affecting errors), balanced (brief meaningful
grammar/naturalness correction), and every_turn (check notable issues without inventing
errors). Prompts request a short continuation and at most two explanation sentences
when correcting. Global kana, romaji, explanation language and correction style remain.
Conversation policy never rewrites learner preferences.

Starting level: preferred difficulty, then existing estimate, then beginner. Stored
performance observations are grouped by request/turn ID, so many topic tags on one
answer cannot mimic three answers. The latest three scored turns are averaged. At
least three are required: >=0.85 moves one level up; <0.50 moves one down; otherwise
unchanged. This is anchored to the starting level, bounded beginner…N1, and derived
without modifying placement. At most 24 observations are read (existing eight-per-turn
bound). English-only replies and explicit teaching questions cannot add performance
evidence, although ordinary exposure observations may remain.

Completion recap uses actual saved turn count, topic labels, observation count,
recent scored-turn average and final practice difficulty. It explicitly avoids
proficiency claims. No invented topics, scenario success score or completion AI call.

## RAG and security

Ordinary roleplay skips retrieval. Explicit meaning/grammar/translation/reading
questions use existing retrieval and response-copy checks. Source-dump requests still
go through the existing guard. Grounding safety instructions remain even on skipped
turns. Primary and fallback receive identical assembled context.

Short English answers are allowed only for server-known active scenarios and a bounded
set of simple replies. Injection/unrelated-request checks still run first. A targeted
scenario-override pattern also rejects an instruction to abandon a scenario and become
another kind of assistant, even with a Japanese keyword. Japanese vocabulary questions
about technical topics remain allowed. Ownership checks cover learner and session,
and staging ownership is claimed atomically. No secrets, transcripts, reference chunks
or private paths were added to logs or public APIs.

## Frontend and verification

Tutor now has scenario/correction setup, loading/error/retry state, active goal and
effective difficulty, finish button and recap. It retains the existing composer and
navigation. Conflicting general controls hide during practice. Reload restores the
authored opening exactly once plus the saved transcript. Navigation preserves an
unsent draft; reload retains saved content only. Completed practice is read-only and
remains available through Progress → History.

Local browser verification used a disposable SQLite profile and explicitly fake
provider on port 8012: authored restaurant opening, Japanese send, reload restoration,
Home→Progress→Tutor with retained draft, and deterministic finish/recap passed.
Responsive overrides at 360, 390, 430, 768 and 1280 pixels showed no document horizontal
overflow; the browser's effective CSS viewport was slightly smaller than the override.
Labels and semantic controls appear in the accessibility tree, busy controls disable,
and recap receives focus. Actual-phone/virtual-keyboard acceptance remains deferred by
the owner; browser emulation is not an actual phone test.

Final local regression: **488 backend passed**, including nine PostgreSQL cases,
**22 frontend passed**. Added 39 backend cases and seven frontend checks. Coverage
includes all policies, difficulty boundaries, distinct-turn evidence, English help,
ownership, transactional failures, concurrent start/finish, in-flight generation,
forced chat mode, replay, migration preservation, no-match/available/unavailable RAG
contexts, identical fallback context, scope rejection and normal Japanese requests.
Existing Phase 1–7.5 tests remain. Two existing dependency deprecation warnings persist.
The final full backend run took 40.42 seconds. A stopped local PostgreSQL server and
pytest temporary-directory permissions caused earlier setup failures; a restarted
server and new isolated temporary directory resolved them without product changes.

## Changed files

Added: `app/api/conversation.py`, `app/conversation/{__init__,schemas,catalog,migrations,service}.py`,
`frontend/conversation.js`, `tests/test_conversation.py`, this report.

Modified: main wiring; assessment and learner/curriculum/mastery/review migration or
maintenance compatibility; learner sessions/reset; TutorService and safeguards;
frontend index/app/learner/shell/styles; frontend tests; existing schema-version
assertions in curriculum/learning-memory/mastery/PostgreSQL/review tests; README.

## Deployment and remaining verification

Feature commit `5c51e3e` was pushed normally. GitHub Actions run `36714052899` passed.
The live application displays the new catalog and supports creation/completion of
practice, demonstrating that the additive migration and new routes are running.
Public `/health` returned 200; unauthenticated `/api/health` and `/static/shell.js`
returned 401. Source/history privacy audit, JavaScript syntax and whitespace checks passed.

Live introduction passed: the authored opening appeared, `ミゲルです。` produced a short
natural introduction and follow-up question, and finish showed one saved turn and
one scored observation while keeping difficulty beginner. A new restaurant scenario
then started successfully. After the overnight interruption and a Render cold start,
the restaurant restored its goal, balanced correction policy, beginner difficulty,
one saved exchange and exactly one opening. `二人です。` received a natural invitation
to the table; `水をください。` received a natural continuation asking about the order.
The water reply included a short redundant explanation/example despite the prompt's
preference to omit those for valid replies; it did not become a long lesson.
These checks use a new beginner profile in the in-app
browser, leaving the earlier N5 profile in the other browser untouched.

The deliberately incorrect restaurant sentence hit a connection-style browser error
twice, including a retry with the existing request ID. Public health remained 200;
reload showed exactly the two earlier successful exchanges, with no duplicate turn.
After two other requests succeeded, a fresh correction attempt passed: it suggested
`ラーメンを食べたいです。`, explained the たい/かったです distinction in two sentences,
and continued briefly. The earlier intermittent failure's root cause remains unknown
without service logs. Do not claim it was repaired by a code change.

Live scope check passed: `Write Python code for me.` was rejected by the application,
then `How do I say software engineer in Japanese?` was allowed and the tutor returned
to the restaurant. The explicit question `「お会計お願いします」はどういう意味ですか？`
received a brief, correct bill/check explanation and returned to roleplay. Actual
reference-match status is unverified without retrieval logs; a fluent answer alone
does not prove a source match.

Home→Progress→Tutor preserved the active restaurant and all five saved exchanges
(one opening plus ten learner/tutor messages).

Restaurant finish and completed-state reload passed: the deterministic recap showed five learner turns, five
observations, three scored turns averaging 83%, and beginner difficulty. The two
teaching/help questions did not inflate the scored-turn count.

General Tutor passed after selecting New conversation: a short Japanese greeting
request produced an ordinary lesson/example and exercise, with no restaurant role.

Pending: exact Render
revision and per-request provider/retrieval log checks require dashboard access.
Automatic approval review blocked the Render-to-GitHub login redirect because the
separate authentication destination lacked explicit approval. Approval was requested;
no alternate access method or environment change was attempted. Automated fallback
compatibility is verified; no deliberate live quota exhaustion/outage is planned.

Existing free-tier database round trips and cold starts may dominate latency. Practice
adds state/evidence reads to session retrieval and a UI state refresh after a successful
turn; scenario catalog is cached in-page. No AI calls happen on start/restore/recap.
No unrelated pooling or infrastructure rewrite was introduced.

## Limitations and rollback

AI corrections and extracted observations are provisional. Adaptation requires scored
evidence and may stay unchanged when none is recorded. The small English-answer list
is intentionally conservative; arbitrary English roleplay text may be rejected.
Scenario success is not detected automatically. No speech, streaming, avatars,
cross-device accounts or infinite history. Existing private-alpha authentication and
Phase 7.5 lexical retrieval limitations still apply. **Phase 9 has not begun.**

Original Phase 7.5 checkpoint: `56ee8f1`. Schema-compatible Phase 7.5 rollback checkpoint:
`e2cb29f` (accepts learner schema 6 without changing Phase 7.5 behavior). Do not deploy
the original checkpoint alone after migration because it rejects schema 6.

To roll back, first finish active practices while Phase 8 is deployed if feasible.
On main, inspect `git log --oneline e2cb29f..HEAD`, then use normal `git revert` for
the Phase 8 feature/documentation commits in newest-first order, preserving `e2cb29f`.
While that range contains only Phase 8 commits and the working tree is clean, the
concrete commands are `git revert --no-commit e2cb29f..HEAD`, then
`git commit -m "Rollback Phase 8 application; retain additive database schema"`.
Resolve any documentation conflicts, run regression tests, and push normally to
trigger Render with `git push origin main`. Keep schema version 6 and all additive tables/data; do not drop tables,
reset Supabase, force-push or destructively downgrade. Old UI cannot manage active
practice state, so unfinished roleplays need review before a later re-upgrade.
