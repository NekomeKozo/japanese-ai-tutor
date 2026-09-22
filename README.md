# Adaptive AI Japanese Tutor

**Current phase: Phase 6 — Spaced Repetition & Intelligent Review Scheduler.** Gemini and OpenAI use
one provider interface; Gemini is the default for new development setups. This preserves the existing
tutor, adaptive placement and persistent learning memory in place. Today's Study builds
and saves an evidence-based plan for 5–60 minutes. Application code selects topics,
prerequisites, order and difficulty; the LLM supplies selected lesson content only.
Japanese Knowledge now tracks evidence-based mastery and confidence separately for each
skill dimension. The calculator is deterministic and makes no model calls.

## Daily Review

In **Today's Study → Daily Review**, choose a time budget and start reviewing. Only
previously assessed material becomes scheduled. Due reviews target specific skills such
as vocabulary production or kanji on-reading. Remaining items stay available for later;
skipping does not count as failure. Existing active study plans are resumed safely.

Phase 6 uses the maintained **FSRS 6.3.2 Python library**, behind an application-owned
adapter with deterministic policy limits and retention target .90. Application code
decides dates and priority with zero model calls. Models may still generate grammar
exercises or grade open answers. See [scheduler design](docs/review-design.md) for exact
rating gates, interval caps, bootstrap, UTC/local-time semantics and known limitations.

Startup adds SQLite schema **v5**, preserving existing records and staggering schedules
for measured mastery dimensions. Never-seen items remain unscheduled. Back up your database
before upgrading and install updated dependencies in your existing environment:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
.\.venv\Scripts\python.exe -m pytest -q tests/test_reviews.py
```

Review states are learning, review, relearning, with suspension stored independently.
Partial scores map to Again/Hard/Good/Easy. Lapses shorten intervals without erasing
mastery. Repeated difficulty calls for deeper practice; same-day retries have a minimum
spacing and an attempt safeguard. Backlogs increase the review share of Phase 4 plans.

Read-only queue/forecast routes:

- `GET /api/learners/{learner_id}/reviews/due?minutes=10`
- `GET /api/learners/{learner_id}/reviews/forecast?timezone=Asia/Manila`

Forecast timezone is supplied by the browser; the example is not a hard-coded default.
All review activity submissions reuse the existing study-session API.

For developer maintenance, stop the server and back up first:

```powershell
.\.venv\Scripts\python.exe -m app.review.maintenance --database data/assessment.sqlite3 --learner-id YOUR-LEARNER-UUID --topic vocab_taberu --action rebuild
```

Use `--action suspend` or `--action resume` with `--dimension production` to manage a
specific target. These operations are deliberately absent from the ordinary UI.
See [Phase 6 report](PHASE6_REPORT.md) and [verification](PHASE6_VERIFICATION.md).
Phase 7 product/UI work has not begun.

## Japanese Knowledge

Open **My learning → Japanese Knowledge**, filter by content or knowledge status, and
select a topic to see its dimensions, confidence, last practice and meaningful changes.
“Not enough evidence” means unassessed; it is not a zero score. Recognition does not
establish production. The existing recent-practice summaries remain separate.

Mastery Algorithm v1 combines 70% weighted lifetime evidence with 30% of the latest six
observations, using a neutral prior and limiting each dimension update to 0.08. Overall
mastery combines 80% of the dimension-weighted score with 20% of the weakest dimension.
Untested slots contribute a neutral prior only to this aggregate; their own scores stay
null. Confidence separately reflects evidence weight, consistency, independent contexts,
varied task types and dates. See [the exact formula](docs/mastery-design.md) before using
these provisional estimates for future scheduling.

Phase 5 introduced SQLite schema **v4**, extended to v5 by Phase 6. Three derived
tables preserve normalized evidence, mastery state and meaningful history. Original
events, placement, preferences and conversations are retained. Back up the database
before upgrading. Historical events without reliable dimensions receive only weak
recognition evidence; broad vocabulary groups cannot imply mastery of individual words.

Read-only endpoints:

- `GET /api/learners/{learner_id}/mastery?type=vocabulary&status=learning&limit=20&offset=0`
- `GET /api/learners/{learner_id}/mastery/{topic_id}`

Types are `vocabulary`, `grammar`, `kanji`. Statuses are `new`, `learning`, `developing`,
`familiar`, `strong`, `needs_review`. Optional filters can be omitted. Detail responses
include dimensions and up to 20 meaningful history records, not raw event payloads.

For local maintenance, stop the server and back up the database, then run from this folder:

```powershell
.\.venv\Scripts\python.exe -m app.mastery.maintenance --database data/assessment.sqlite3 --learner-id YOUR-LEARNER-UUID
```

This rebuilds derived state/history from normalized evidence without modifying original
learning events. It is not a public API. Policy parameters live in `app/mastery/policy.py`;
future formula changes should increment the algorithm version and be explicitly recomputed.
See [Phase 5 report](PHASE5_REPORT.md) and [verification](PHASE5_VERIFICATION.md).

## Features

- Existing text chat, corrections, grammar/vocabulary explanations, examples, exercises
  and quizzes, using the same replaceable LLM provider interface.
- Adaptive placement from a validated bank of 68 original prototype questions.
- Separate estimates for hiragana, katakana, vocabulary, grammar, particles, verb
  conjugation, adjective conjugation, kanji, reading and sentence construction.
- Deterministic fixed-answer scoring; structured LLM evaluation only when semantics
  require it, including partial credit and acceptable alternate answers.
- Application-controlled difficulty, skill coverage, confidence and stopping.
- Persistent, resumable assessments and initial profiles in SQLite.
- A learner profile screen with recent performance, strengths, weaknesses, mistake
  patterns, vocabulary/grammar/kanji exposure, activity and saved sessions.
- Persistent conversations, safe retry IDs, compact tutor context and preferences/goals.
- Conservative skill updates with immutable placement and a developer-only reset command.
- Deterministic curriculum ranking, prerequisites, review/new balance, goal weighting,
  skill-sensitive difficulty and repetition/underexposure adjustments.
- Saved study plans, on-demand lessons, answer feedback, skip/resume and session recaps.
- No accounts, voice, listening, scheduling, gamification or later-phase systems.

## Requirements and setup

Python **3.11+** (tested with 3.12). No Node.js runtime, frontend build step or separate
SQLite installation is required. Runtime dependencies remain FastAPI, Uvicorn, HTTPX,
Pydantic and Pydantic Settings. SQLite uses Python's standard library. pytest is used
for tests.

Open a terminal in this `japanese-tutor` directory. Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
```

Do not overwrite an existing `.env` when upgrading from Phase 1 or 2. If `python` points to
an MSYS build without pip/venv, use a standard Windows installation or `py -3.12`.

macOS/Linux:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
cp .env.example .env
```

Set the selected provider's key in `.env` for real tutoring and semantic assessment grading.
Never put keys in frontend code or commit `.env`. Environment variables override `.env`.
Restart the server after changing configuration. For the exact tested dependencies,
install `requirements-lock.txt` instead. For runtime only, use `requirements.txt`.

### Select Gemini or OpenAI

Gemini (new development default; no OpenAI key required):

```dotenv
LLM_PROVIDER=gemini
LLM_MODEL=gemini-3.1-flash-lite
GEMINI_API_KEY=your-key-here
```

OpenAI (existing support preserved):

```dotenv
LLM_PROVIDER=openai
LLM_MODEL=gpt-4.1-mini
OPENAI_API_KEY=your-key-here
```

To switch, change `LLM_PROVIDER`, change `LLM_MODEL` to a compatible model, supply
that provider's key, and restart. Only the selected key is required. A blank `LLM_MODEL`
uses `gemini-3.1-flash-lite` for Gemini or `gpt-4.1-mini` for OpenAI. Existing `.env` settings
are not overwritten. Use a model that supports structured output; model availability
and access depend on your provider account. No automatic fallback or provider retries
are enabled. Existing lesson schema-repair behavior remains unchanged.

Both adapters use the existing HTTPX dependency and official REST APIs. No additional
SDK is needed. See [provider-design.md](docs/provider-design.md) for the boundary,
safe diagnostics, and extension instructions.

### Runtime troubleshooting

The backend loads `.env` from the application directory (beside this README), regardless
of the launch directory. Operating-system environment variables still take precedence.
Settings and the provider are loaded at startup: save changes, stop the old server and
its reload worker, then restart. Keep the working directory here so the existing relative
database path continues to point to your saved learner data.

Use the URL printed by the server. For example, a server launched with `--port 8001`
is at `http://127.0.0.1:8001`. The frontend uses relative `/api/...` URLs and therefore
calls the backend serving that page; it has no separate provider, model or proxy setting.
`/api/health` reports the **running process's** provider, model and key-presence boolean
without revealing credentials. This is a configuration check, not a live API test.

Startup logs identify the working directory and `.env` path. Failed provider calls log
the model, HTTP status, allowlisted provider error category/reason and API route template.
Vendor response bodies/messages are never logged because they can echo secrets or prompts.
A 404 indicates a model/endpoint configuration problem; 429 indicates rate/quota pressure;
5xx indicates a provider service error. A temporary service error can be retried manually.
See [the runtime verification report](PHASE4_5_RUNTIME_REPORT.md) for the browser and live
service checks, as well as the limits of diagnosing the original screenshot.

## Run backend and frontend

Both run in one process. From the project directory:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

On macOS/Linux, substitute `.venv/bin/python`. Open **http://127.0.0.1:8000**.
API documentation: http://127.0.0.1:8000/docs. Stop with Ctrl+C. Optional `--reload`
clears temporary chat sessions on code changes; profile conversations and assessments
remain in SQLite.
**Use one worker**, because Phase 1 conversation memory is process-local.
Do not open `frontend/index.html` directly from disk.

The app starts without a key. Deterministic placement works without an API connection.
Unknown free-response variants cannot be judged without a provider: the assessment
records unavailable evidence, continues and reports lower confidence. Ordinary tutor
chat still needs the API key. `/api/health` checks configuration presence, not account
balance, network connectivity or model access.

Study planning and fixed vocabulary, kanji, script and reading activities work without
an API key. Grammar and sentence-writing lessons use the existing provider on demand.
If lesson generation or grading fails, the saved plan remains available to retry or skip;
provider failure is never recorded as an incorrect answer.

## Today's Study

1. Complete placement and choose **Begin learning**, open a saved learner ID in
   **My learning**, or choose **Start with a beginner profile** on Today's Study.
2. Choose any whole number from **5 to 60 minutes** and a focus. Balanced is the default;
   grammar, vocabulary, kanji, reading, sentence writing, review, new material and quick
   practice are also supported.
3. Select **Generate study plan**. Preview the topics, estimated time and short reasons.
   Planning does not call the LLM. An existing planned/in-progress session is returned
   unchanged, even if a later request asks for different settings.
4. Select **Start session**. Each lesson is loaded only when reached. Fixed recall content
   needs no provider call; generated lessons use a validated structured schema.
5. Answer and select **Check answer**, then **Continue**, or **Skip activity**. Feedback
   and reference answers appear after grading. A skip is not a correct or incorrect score.
6. Finish to see a recap based on this session's results. The next plan uses updated
   Phase 3 memory. Refresh/restart restores the active plan; **End this plan** abandons it
   without deleting completed evidence and permits a new plan.

Duration is an approximate self-study budget, not a timer or verified time spent. The
prototype has one scored question per activity; use the remaining time to study examples
and practice independently. The small catalog is a demonstration, not a full course.
Advanced explicit requests remain available through ordinary tutor chat.

See [curriculum-design.md](docs/curriculum-design.md) for policies, formulas, lifecycle,
data contracts and Phase 5 extension boundaries.

## Assessment flow

1. Open **Placement**. Optionally select your experience; this changes only initial
   item selection, not the scoring prior or final level directly.
2. Start placement. Four easy kana items screen for a complete beginner.
3. Answer choices or type a free response. **I don’t know** is always available.
4. Questions adapt in difficulty while covering different skills. The screen shows
   count against a maximum of 30, not a misleading fixed completion percentage.
5. The assessment ends when evidence stabilizes, the beginner screen is conclusive,
   the maximum is reached, or suitable bank items are exhausted.
6. Review skill estimates, confidence, strengths, gaps and a starting recommendation.
7. Select **Begin learning** to open a persistent session using this learner profile.

You can switch to **Tutor chat** without finishing placement. **Use beginner chat**
creates a new unassessed learner with no fabricated skill scores. **New session**
closes the selected conversation and opens another; learning memory is retained.
**Start another assessment** offers a new assessment without deleting previous results.
Refreshing restores the current assessment through a browser-stored resume identifier;
use **Reload saved assessment** after a connection error. Active assessments expire
by default after 24 hours of inactivity. Completed results do not expire automatically.

The UI does not reveal answer keys, exact difficulty, interim scores or correctness
feedback during placement. All generated text is rendered as text, never executable HTML.

## How adaptation and confidence work

Each non-script skill has a small Bayesian ability grid on the internal 0–14 scale.
Updates depend on item difficulty, fractional score and evidence weight, with a
chance adjustment for multiple choice. Scripts use sample recognition success rates.
One item is insufficient for a displayed skill level. Particles and conjugation also
contribute to grammar; these subskills are not counted twice in the overall summary.

Repeated successes raise target difficulty, failures lower it, and mixed evidence
focuses questions near the estimated boundary. Coverage and confidence determine which
skill comes next. Asked IDs cannot repeat, and choice positions are shuffled stably
within each assessment. Most simulated learners finish in 20–30 questions; a complete
beginner can finish after the four-item screen with other skills marked unassessed.

Confidence combines available evidence, posterior uncertainty, answer consistency,
coverage, boundary evidence, skips and evaluator failures. It is a heuristic confidence
indicator, not a probability of passing JLPT. Strong/weak topic labels require repeated
observations from item metadata. Written production is separate from the summary of
vocabulary, grammar, kanji and reading. Listening and speaking are unassessed.

See [assessment-design.md](docs/assessment-design.md) for exact formulas, thresholds,
stopping rules, persistence contracts and architectural decisions.

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `GEMINI_API_KEY` | empty | Gemini server-side credential; required only for Gemini |
| `OPENAI_API_KEY` | empty | OpenAI server-side credential; required only for OpenAI |
| `LLM_PROVIDER` | `gemini` | `gemini` or `openai` |
| `LLM_MODEL` | blank | Selected adapter's default; `.env.example` explicitly selects Gemini 3.1 Flash-Lite |
| `LLM_TIMEOUT_SECONDS` | `45` | Generation deadline |
| `LLM_MAX_OUTPUT_TOKENS` | `1800` | Output budget |
| `ROMAJI_ENABLED` | `false` | Tutor romaji policy; placement separately accepts declared alternatives |
| `MAX_HISTORY_TURNS` | `12` | Maximum complete pairs used as conversation context |
| `SESSION_TTL_SECONDS` | `3600` | Idle chat-session lifetime |
| `MAX_SESSIONS` | `100` | In-memory chat capacity |
| `ASSESSMENT_DB_PATH` | `data/assessment.sqlite3` | Shared placement, learning and curriculum database; relative to working directory |
| `ASSESSMENT_TTL_SECONDS` | `86400` | Idle lifetime for active assessments |

## Storage and upgrade

Phase 1 had no database. Phase 2 introduced SQLite schema version 1 with four tables:
`assessment_questions`, `assessments`, `assessment_answers`, `learner_profiles`.
Phase 3 introduced schema version 2 using `PRAGMA user_version`.
It adds current learner/skill/topic/mistake state, canonical topics, events, saved
sessions, conversation turns and skill history. Existing rows are preserved. Completed
placements are backfilled once into current state; active assessments remain resumable.
Migration and backfill commit together or roll back. Back up the existing database with
the server stopped before upgrading; keep the same `ASSESSMENT_DB_PATH`.
Phase 4 automatically advances to **schema version 3**, adding `study_sessions` and
`study_activities` plus controlled catalog entries in the existing `learning_topics`.
All v1/v2 rows are retained. A partial unique index permits only one active study plan
per learner. Plans, content and results persist; no migration recalculates earlier plans.
Active snapshots preserve the current question and evidence; final snapshots include
skill estimates and the profile. A result and initial profile share a versioned schema.

State updates, answer insertion and profile creation commit atomically. Duplicate
submission IDs replay safely; conflicting/stale submissions return 409. Answer and
question snapshots remain server-side. SQLite failures return a safe error, while
ordinary chat without a profile remains available.

The browser stores learner, session and assessment IDs, not answers or secrets. SQLite
stores placement evidence, profile state, learning events and conversation turns locally.
Back up the SQLite file with
the server stopped. Neither databases nor `.env` belong in source archives. Expired
assessment rows currently remain stored; there is no automatic retention cleanup.
Each new assessment creates an anonymous learner ID. **My learning** shows the ID and
lets you reopen it on the same server. IDs are not authenticated accounts. Retaking
placement creates a separate learner; merging or reassessing an existing learner is
deferred. **Use temporary chat** provides the original in-memory mode without a profile.

Profile chat persists across refresh/restart. Only a bounded recent conversation window
and a compact learner summary are sent to the configured provider when tutoring.
Semantic placement grading sends only one question, criteria, references and answer.
OpenAI requests set `store=false`; provider retention policies can still apply.
Logs record lifecycle/failure categories without answer text, API keys or model bodies.

## API

| Endpoint | Purpose |
| --- | --- |
| `POST /api/assessments` | Start, body `{ "self_report": "unknown" }` |
| `GET /api/assessments/{id}` | Resume or retrieve public state/result |
| `POST /api/assessments/{id}/answers` | Submit one answer |
| `GET /api/assessments/{id}/result` | Retrieve a completed result |
| `POST /api/learners` | Create an unassessed default learner |
| `GET /api/learners/{id}/profile` | Current profile plus immutable original placement |
| `PATCH /api/learners/{id}/preferences` | Save supported preferences and primary goal |
| `GET /api/learners/{id}/activity` | Recent events; limit 1–50, offset 0–10,000 |
| `POST /api/learners/{id}/sessions` | Create a persistent conversation |
| `GET /api/learners/{id}/sessions` | Recent sessions; limit 1–50 |
| `GET /api/learners/{id}/sessions/{session_id}` | Latest 12 saved exchanges |
| `POST /api/learners/{id}/sessions/{session_id}/close` | Close without erasing history |
| `POST /api/curriculum/plan` | Create or resume study plan; learner_id, available_minutes, session_type, optional requested_focus |
| `GET /api/learners/{id}/study/active` | Active study plan or null |
| `GET /api/learners/{id}/study/{session_id}` | Saved plan/progress/recap |
| `POST /api/learners/{id}/study/{session_id}/start` | Start or resume |
| `POST /api/learners/{id}/study/{session_id}/activities/{activity_id}/open` | Generate once or retrieve cached teaching content |
| `POST /api/learners/{id}/study/{session_id}/activities/{activity_id}/complete` | Submit answer plus submission_id UUID; reuse identical ID/payload on retry |
| `POST /api/learners/{id}/study/{session_id}/activities/{activity_id}/skip` | Skip without competence evidence |
| `POST /api/learners/{id}/study/{session_id}/complete` | Finish after all activities are complete/skipped |
| `POST /api/learners/{id}/study/{session_id}/abandon` | End an active plan while retaining prior results |
| `POST /api/sessions` | Create a temporary chat session |
| `DELETE /api/sessions/{id}` | Reset a chat session |
| `POST /api/chat` | Tutor reply; persistent sessions require learner_id and request_id |
| `GET /api/health` | Server/configuration status |

A placement answer request:

```json
{
  "question_id": "q001",
  "submission_id": "<new UUID, reuse it when retrying the same answer>",
  "answer": "あ",
  "dont_know": false
}
```

For **I don’t know**, use `"answer": null, "dont_know": true`. The question must match
the current server-side question. Send actual choice text, not an A/B/C position.
Responses include the next public question or completed result, without private item
metadata. A provider failure may include a neutral unavailable-evidence notice.

Chat requests still accept `session_id`, `message`, `mode` and `level`. Modes are `chat`,
`correct`, `grammar`, `vocabulary`, `examples`, `exercise`, `quiz`; levels are `beginner`
and `N5`–`N1`. Add `learner_id` returned by a completed placement to enable profile context.
The server loads it from SQLite; the client cannot submit fabricated scores. For saved
sessions also send a fresh UUID `request_id`, reusing it when retrying the identical
request. A duplicate returns the saved reply without another provider call or state
update. A reused ID with different content returns 409. Legacy `/api/sessions` sessions
remain temporary; use the learner session endpoints to record learning observations.

## Learning memory and preferences

**My learning** displays current evidence and the preserved placement starting point.
Edit explanation language, correction style, romaji, kana readings, preferred difficulty
and a primary goal. The next tutor request uses saved preferences. The chat level selector
also saves a difficulty preference; it does not alter assessed ability. Goals influence
curriculum priorities. Curriculum difficulty follows measured skill evidence, so a high
chat difficulty preference or ambitious JLPT goal cannot bypass prerequisites.

Known topic aliases become canonical tags. Unknown topics go into fixed unscored generic
categories. At most eight validated observations are accepted per reply, one per topic.
Explanations and help requests record exposure, not proficiency. Invalid observations
are ignored while a valid teaching reply is retained. The latest eight scored encounters
determine topic status; at least three are needed for a weakness, four for a strength.
Later correct answers can remove a weakness. Skill estimates move at most 0.15 every
five scored interactions per skill and remain within one point of placement. Unassessed
skills remain unassessed; overall level does not automatically change.

Tutor profile context is capped at 4,000 UTF-8 bytes, with up to five weak topics, five
active recent mistakes, three strengths and five recent topics. Prior conversation
context is capped at 12,000 characters and `MAX_HISTORY_TURNS` complete exchanges.
Full events, placement answers and lifetime transcripts never enter the tutor context.
These are size bounds rather than exact tokenizer counts. See
[learning-memory.md](docs/learning-memory.md) for precise policies and extension points.

## Developer reset

There is no accidental reset button or public reset endpoint. Stop the server and back
up SQLite first. This explicitly deletes **one learner's** subsequent learning memory,
preferences, saved conversations and study plans, then restores their original placement or unassessed
defaults. Assessments and other learners are preserved. Repeat the same actual UUID in
both arguments:

```powershell
.\.venv\Scripts\python.exe -m app.learner.reset --database data/assessment.sqlite3 --learner-id <UUID> --confirm-reset <UUID>
```

The command refuses a missing database, a schema other than version 2 or 3, or mismatched
confirmation. Deleted learning history can only be recovered from your backup.

Errors use `{"error":{"code":"...","message":"..."}}`. Typical statuses are 422
invalid input, 404 unknown session/profile, 409 conflict or incomplete result, 410 expired
assessment, 502 invalid model reply, 503 unavailable provider/storage, and 504 timeout.
Evaluator outages are consumed as unavailable evidence rather than scored as wrong.

## Project structure and extension points

```text
app/
  main.py, config.py, errors.py
  api/chat.py, assessment.py
  api/learner.py          Profile, preferences, activity and saved-session endpoints
  api/curriculum.py       Study planning and lifecycle endpoints
  curriculum/
    catalog.py           63 teachable topics, prerequisites and recall templates
    policy.py            Tunable ranking/strategy weights and reason labels
    planner.py           Pure deterministic strategy, ranking and time allocation
    schemas.py           Validated plan, lesson and completion contracts
    content.py           On-demand content through existing provider; tutor display contract
    service.py           Persistent lifecycle and Phase 3 event transactions
    migrations.py        Additive SQLite schema v3
  learner/               Migration, state, events, taxonomy, context and session services
  tutor/                  Existing prompts, schemas and tutor orchestration
  llm/                    Shared protocol, factory, Gemini and OpenAI REST adapters
  memory/conversation.py  Temporary Phase 1 chat memory
  assessment/
    schemas.py            Question, evaluation, state, skill and profile models
    questions.py          Validated bank and candidate-import boundary
    data/questions.json   68 original prototype items
    evaluator.py          Local comparison and semantic LLM evaluation
    scoring.py            Evidence updates and confidence
    selector.py           Coverage and adaptive item selection
    engine.py             Assessment lifecycle and stopping
    results.py            Evidence-based profile and recommendation
    repository.py         SQLite initialization and atomic persistence
frontend/                 Tutor, placement and learner-profile UI
 tests/                   Phase 1 regression and Phase 2 tests
 docs/assessment-design.md
```

Implement another provider through `LLMProvider.generate`; tutor, assessment and curriculum
reuse it. Register it in the provider factory and add its credential setting. Extend the question bank through the validated
schema and bump its bank version for a released content change. Future generated items
need content review before being admitted; live automatic item generation is not enabled.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pytest -q tests/test_assessment.py tests/test_assessment_core.py
.\.venv\Scripts\python.exe -m pytest -q tests/test_curriculum.py
```

Tests are offline and use temporary databases, mock providers and mocked HTTP transport.
The existing `MockProvider` supplies deterministic replies for learning-system tests.
An automatic test fixture blocks real HTTPX network transports, even if your environment
contains an API key. Provider tests use `MockTransport`; no paid API calls are needed.
They cover start/question/answer flow, correct and incorrect answers, skips, input and
schema validation, partial credit, evaluator failures, adaptation in both directions,
coverage, no repeated IDs, confidence, simulated learner ranges, uneven skills, maximum
length, profile generation, resume after restart, idempotency, stale writers, concurrency,
transaction rollback, storage failures, answer secrecy and tutor compatibility.
Phase 3 adds migration preservation/rollback, preference persistence, canonical topic
memory, weak-topic recovery, bounded context, saved-session replay/ownership, atomic
turn updates, conservative skill drift and scoped developer reset tests.
Phase 4 adds deterministic planning, synthetic learners A–D, prerequisites, goal/focus
and time allocation, v2 upgrade/rollback, activity lifecycle, generated content validation,
result replay/rollback, concurrency, cancellation and compact-context tests.
Phase 4.5 adds provider selection, switching, text/structured normalization, safe logging,
configuration and failure checks. Phase 5 adds 48 mastery cases; Phase 6 adds 57 review
cases, for **355 passing tests** in the app's Python 3.14 environment. See
[PHASE6_VERIFICATION.md](PHASE6_VERIFICATION.md) for current results; historical checks
remain in the earlier phase reports.

## Limitations and future work

This is a local prototype. The bank has not received independent Japanese-teacher review
or empirical item calibration. Difficulty labels and confidence are provisional; passing
all sampled high-level items does not establish official certification. Small samples,
short reading passages, recognition choices, and a limited production rubric restrict
accuracy. Some subskills may have too little evidence for a level. Live LLM grading and
teaching quality still need verification with a configured key.

The app has no production authentication, rate limits or assessment ownership controls;
keep it bound to loopback. IDs are not user accounts. Free-response grading can make
mistakes despite valid JSON. Bank generation is a validated extension point, not an
implemented automatic generation workflow. There is no streaming, automatic
level promotion or spaced repetition. The verified dependency set
emits upstream TestClient deprecation warnings that do not affect test results.

Learning observations can be wrong even when structurally valid. The fixed catalog is
small, scores are heuristic, and placement confidence remains separate from mastery confidence. Recent mistake
counts cover at most 50 occurrences in 30 days. Topic status is a rolling signal, not a
mastery certification. Saved transcripts/events currently have no automatic retention
cleanup. Requests are scoped to learner/session IDs, but anyone with the IDs and server
access can read or modify that local learner; this is not production access control.

The curriculum catalog covers foundations through a small N3 sample. It is not a complete
N5–N1 course. Generated text is checked for schema/topic/difficulty identity, but this
cannot prove Japanese correctness or that an exercise actually matches its claimed
difficulty. Fixed templates currently use English instructions. Estimated durations and
priority weights need real-learner calibration. Unknown prerequisites are conservative;
unassessed learners should take placement before seeking advanced automatic plans.

Mastery v1 is a conservative heuristic, not a calibrated probability of recall. Its small
reviewed catalog and existing question templates leave many dimensions unknown. Repeated
identical questions contribute progressively less evidence. LLM-assisted grading remains
a possible source of error, although the mastery calculation itself makes no LLM calls.
Phase 6 now adds review timing through FSRS with explicit conservative policy limits.
Mastery confidence still needs calibration, especially for sparsely tested dimensions.
Phase 7 may polish the product experience; it has not begun.

The original adapter follows the official [Structured Outputs guide](https://developers.openai.com/api/docs/guides/structured-outputs).
