# Phase 6.5 progress report — 2026-09-27

**Status: local implementation and clean-package verification complete; live rollout
is blocked on owner-managed Render environment configuration. Phase 6.5 is not
complete. No Phase 7 or RAG work has begun.**

## Initial audit

| Area | Finding before changes |
|---|---|
| Canonical repository | `C:\Users\MIGUEL PC\Github\japanese-ai-tutor`; no new clone or repository created |
| Branch / status | `main`, clean; checkpoint `6eb6014` |
| Remote | `https://github.com/NekomeKozo/japanese-ai-tutor.git`, exact match |
| Private files | `.env`, reference directories, local databases ignored; none tracked |
| Secret history | Available history and tracked source checked; no secret candidates found |
| Backend | FastAPI lifespan creates providers and services; Uvicorn serves HTTP |
| Frontend | Vanilla HTML/CSS/JS served by FastAPI; relative API URLs; no Node build |
| Python / packages | Existing Python 3.12 test environment and 3.14 local environment; pip requirements and pinned lock file |
| Configuration | Pydantic Settings, project-local `.env`, secrets wrapped in SecretStr |
| Database | SQLite snapshots, append-only evidence, transaction-scoped connections |
| Migrations | Sequential additive v1–v5; no ORM/Alembic |
| PostgreSQL gaps | PRAGMA versioning, BEGIN IMMEDIATE, bind markers, conflict SQL, schema introspection and REAL precision |
| DATABASE_URL | Previously unused |
| Gemini | REST generateContent adapter, server-only key, JSON Schema and safe errors |
| OpenAI | Responses adapter through the same provider protocol |
| Fake provider | Test injection, network blocked in automated tests |
| Groq fit | New protocol adapter and bounded provider router, outside learning algorithms |
| Limits | 4,000-character learner text, bounded histories and output token budgets |
| Headers | Cache-Control, nosniff, self-only CSP; safe API errors |
| Authentication | None; UUID scoping was not authentication |
| Rate limiting | None |
| Japanese scope | Teacher prompt only; no application enforcement |
| Injection defenses | Untrusted learner text instructions and validated schemas; no application scope filter |
| Existing deployment | Owner reported Render Free + Supabase Free, GitHub connected; `/health` returned safe 404 in initial live check |
| Existing Phase 6.5 code | None |

The broad `data/` ignore rule also hid the built-in placement question bank. The
deployment now includes only `app/assessment/data/questions.json` through an explicit
exception. Private data directories remain ignored.

## Implemented

1. PostgreSQL adapter using psycopg 3.3.3; SQLite remains the local default.
2. Private PostgreSQL schema, sequential atomic migrations, safe errors, TLS for
   remote connections, transaction serialization, and bounded connection timeouts.
3. Staging refuses startup without PostgreSQL, HTTPS origin, access/scope settings,
   valid access secrets, and a valid question bank. No ephemeral SQLite fallback.
4. Public zero-inference `/health`, protected database `/ready`, quieter startup logs.
5. Server-validated access code, signed expiring HttpOnly/Secure staging cookie,
   persistent browser resource ownership, and same-origin write checks.
6. Request-body and AI-route limits, login throttling, deterministic topic/injection
   checks, and acceptance of short answers to server-held exercises.
7. Configurable Groq adapter, JSON Schema output, bounded Gemini→Groq failover,
   no failover on safety/configuration/application failures, safe telemetry.
8. Source/history audit script, strict future Docker exclusion rules, Python runtime
   selection, CI with real disposable PostgreSQL, and full deployment instructions.
9. Existing UI retained; access screen added and “saved locally” wording corrected
   for server persistence. Existing learning algorithms are unchanged.

## Files

Added: `.dockerignore`, `.python-version`, `.github/workflows/tests.yml`,
`app/storage.py`, `app/safeguards.py`, `app/llm/groq.py`, `app/llm/failover.py`,
`frontend/access.html`, `frontend/access.js`, `scripts/audit_deployment.py`,
`tests/test_staging.py`, `tests/test_failover.py`, `tests/test_postgres.py`,
`docs/deployment.md`, and this report. The existing application-authored
`app/assessment/data/questions.json` is newly included in Git, unchanged.

Modified: `.env.example`, `.gitignore`, `README.md`, both runtime requirements files,
`app/config.py`, `app/main.py`, `app/errors.py`, `app/assessment/repository.py`,
the chat/assessment/learner/curriculum API modules, provider factory/common/Gemini
adapter, `frontend/app.js`, and two persistence descriptions in `frontend/index.html`.

## Verification performed

- Original 355 tests passed after the initial storage/access changes.
- Expanded complete suite passed: 417 tests, including real PostgreSQL 18 tests.
- Subsequent focused provider/access/origin/retry checks passed: 112 tests.
- Final clean source export and newly installed pinned environment: **418 tests
  passed**, including PostgreSQL integration, in 30.87 seconds. Two upstream
  Starlette/AnyIO deprecation warnings remain. The disposable database was stopped.
- PostgreSQL fresh/repeated migrations, failed-migration rollback, transaction
  rollback, placement completion, preferences, history, review scheduling, mastery,
  activity retries and restart persistence passed in isolated local databases.
- Two browser identities cannot access each other's profiles, mastery, reviews,
  history, placement or chat sessions; ownership survives application restart.
- Failover tests verify primary success, 429, timeout, connection errors, temporary
  errors, disabled fallback, safe refusals, structured output, bounded attempts,
  and no duplicate learner events/mastery/review attempts on replay.
- Browser preview verified wrong-code rejection, successful login, unrelated-topic
  rejection, a fake tutor reply, and saved chat restoration after reload.
- Preview inspected at 390×844 phone width. This is not a real mobile-device test.
- Clean pinned dependency installation succeeded; `pip check` found no conflicts.
- Changed JavaScript passed syntax checks. Source/history audit passed without
  printing secrets. Private ignore rules were rechecked.
- All JavaScript files in the source export passed syntax checks. The export
  contained no private reference files, local databases, or `.env`; the built-in
  question bank matched the Phase 6 file byte for byte.
- No real Gemini/Groq quota was used for these tests. No cloud database credentials
  were accessed. No local learner database or private reference file was modified.

## Live status and manual handoff

Frontend/backend host: existing Render Free Web Service.
Database host: existing Supabase Free PostgreSQL, integration pending.
Site: https://japanese-ai-tutor.onrender.com
Health target: https://japanese-ai-tutor.onrender.com/health

The local changes have not been pushed or deployed. Current cloud PostgreSQL,
Gemini/Groq behavior, health success, cloud restart persistence, CI completion and
actual phone access are **not verified**. The existing live application should not
be shared with testers before the access gate is deployed.

Next owner action: follow [the environment table and menus](docs/deployment.md)
in Render's existing service. Enter all secrets privately, preserve the selected
Free tier, and report only that settings are saved and whether Groq is ready.
After that: push the reviewed checkpoint, verify CI/deployment, check `/health`,
then stop for the owner to change Render's health-check path to `/health` as requested.
Continue with real staging acceptance and restart tests after that manual step.

## Limits, costs, and rollback

Expected infrastructure cost stays $0 within selected free-tier quotas; no paid
resources were provisioned. Provider charges depend on owner account billing.
Render sleeping is accepted; Supabase free-tier backup/recovery limitations are
documented. No artificial keep-alives or scheduled generation were introduced.

Access is per browser, not full accounts or cross-device progress synchronization.
Cookie loss/signing-key rotation requires future recovery tooling. In-memory limits
reset on restart and require a single worker. Deterministic scope checks cannot
prove resistance to every adversarial phrasing. PostgreSQL transactions are deliberately
serialized for this small alpha. Real Groq model suitability still needs live validation.

The Phase 6 checkpoint remains available for local SQLite rollback. It is not a safe
cloud rollback target because it lacks PostgreSQL/authentication. Cloud rollback must
use a verified Phase 6.5 checkpoint, without destructive schema downgrades. See the
deployment guide for backups, logs, redeployment and recovery.

Phase 7 recommendation: complete the outstanding live acceptance checklist first,
then begin the separately authorized UI phase. Do not begin it automatically.
