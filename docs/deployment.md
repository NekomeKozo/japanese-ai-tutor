# Phase 6.5 private staging

Status: commit `8c01edf` is deployed and GitHub CI passed all 418 tests. Public
health and the access gate are verified; the owner confirmed the `/health` dashboard
setting. Authenticated learning and restart acceptance tests remain pending.
This is not a production release.

## Architecture

Browser → HTTPS Render Web Service → FastAPI frontend + API → Supabase PostgreSQL.
Gemini is the primary inference provider; Groq is an optional bounded fallback.
OpenAI and offline fake providers remain available. No Railway, separate static
site, Docker runtime, browser database client, RAG, or reference upload is needed.

Existing service: https://japanese-ai-tutor.onrender.com
Health after deployment: https://japanese-ai-tutor.onrender.com/health
The deployed service now returns `200 {"status":"ok"}` at `/health`.

## Manual setup before pushing this checkpoint

Open https://dashboard.render.com and select the existing **japanese-ai-tutor**
Web Service connected to `NekomeKozo/japanese-ai-tutor`. Do not create another service.
Open **Environment → Edit / Add Environment Variable**. Enter these values there:

| Variable | Value | Secret? |
|---|---|---|
| `ENVIRONMENT` | `staging` | No |
| `FRONTEND_URL` | `https://japanese-ai-tutor.onrender.com` | No |
| `LLM_PROVIDER` | `gemini` | No |
| `LLM_MODEL` | `gemini-3.1-flash-lite` (preserve a different already-working selection) | No |
| `GEMINI_API_KEY` | Your existing Gemini key | Yes |
| `DATABASE_URL` | Supabase PostgreSQL **session pooler URI** with the database password | Yes |
| `STAGING_ACCESS_ENABLED` | `true` | No |
| `STAGING_ACCESS_CODE` | A unique random access code, at least 16 characters | Yes |
| `STAGING_SESSION_SECRET` | A different random signing secret, at least 32 characters | Yes |
| `STAGING_SESSION_HOURS` | `168` | No |
| `SCOPE_ENFORCEMENT_ENABLED` | `true` | No |
| `AI_RATE_LIMIT_PER_HOUR` | `40` | No |
| `AI_GLOBAL_RATE_LIMIT_PER_HOUR` | `200` | No |
| `LLM_MAX_OUTPUT_TOKENS` | `1800` | No |
| `LLM_TIMEOUT_SECONDS` | `45` | No |
| `LLM_FAILOVER_ENABLED` | `true` after both Groq settings below exist; otherwise `false` temporarily | No |
| `LLM_FALLBACK_PROVIDER` | `groq` | No |
| `GROQ_API_KEY` | Your Groq key, entered privately | Yes |
| `GROQ_MODEL` | `openai/gpt-oss-20b`, or another Groq model supporting JSON Schema output | No |

Create a Groq key at https://console.groq.com/keys if needed; never paste it into
chat. Check model access in that account. The model is configurable, not embedded
in learning code. See [Groq structured outputs](https://console.groq.com/docs/structured-outputs).

For the database value, open https://supabase.com/dashboard → existing project →
**Connect → Session pooler → URI**. Substitute the database password privately
and URL-encode reserved password characters. Do not use the project HTTP URL,
anon key, service-role API key, or a browser SDK. The pooler supports IPv4 hosts;
direct connections may require IPv6. Remote connections require TLS in the adapter.
Do not add `tutor_private` to Supabase's exposed API schemas or grant it to anon /
authenticated roles. No application tables are created in `public`.
See [Supabase connection options](https://supabase.com/docs/guides/database/connecting-to-postgres).

Use Render's **Save only** option if available while preparing these settings.
Report only “settings saved”, whether Groq is ready, and any non-secret error code.
Never share keys, the full database URL, database password, access code, signing
secret, or screenshots containing their values. Keep the signing secret stable
across deployments so browser ownership remains usable.

## Build, startup, health, and automatic deployment

In the existing Render service's **Settings → Build & Deploy**:

- Branch: `main`; repository root is the application root.
- Build command: `pip install -r requirements-lock.txt` (reproducible dependencies).
- Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers 1 --no-access-log`.
- Runtime: Python. `.python-version` selects Python 3.12; remove an incompatible
  `PYTHON_VERSION` override or explicitly use the desired supported patch version.
- Auto-Deploy: **After CI Checks Pass**, once the included **Tests** workflow has
  run successfully. This avoids deploying a failed test commit. No deploy hook
  secret or duplicate GitHub deployment action is needed.
- Keep **Free** compute and one instance. No keep-alive pings or scheduled inference.

The workflow runs the complete offline suite, real PostgreSQL integration tests
using an ephemeral local CI service, a source/history audit, and JavaScript syntax
checks. The frontend is plain static files: there is no npm build step.

After the code is pushed and `/health` returns `{"status":"ok"}`, manually open
**Settings → Health Checks → Health Check Path**, change `/` to `/health`, and save.
This dashboard action is deliberately left to the owner. Report “health path set”.
`/health` is public, contains no configuration, and never calls a model or database.
`/ready` requires staging access and checks a database connection. Startup must finish
its migrations successfully before staging serves traffic.

The frontend continues to call relative `/api/...` URLs. No CORS middleware or
wildcard credential origins are added. Mutating browser requests are restricted
to `FRONTEND_URL`; this avoids reliance on proxy scheme headers for origin checks.
Render terminates HTTPS. No secrets are built into JavaScript.
See [Render deploys](https://render.com/docs/deploys) and
[Python versions](https://render.com/docs/python-version).

## Database behavior and migrations

Local development leaves `DATABASE_URL` empty and retains the existing SQLite file.
Staging requires a PostgreSQL URI and never falls back to SQLite. Local SQLite
files are untouched; their existing learner data is not automatically uploaded.
The fresh cloud database starts with the built-in question bank and empty learners.

`app/storage.py` centralizes PostgreSQL syntax and connection handling. The existing
v1–v5 migrations run in order, using a private `schema_version` table instead of
SQLite `PRAGMA user_version`. Parameters remain bound. SQLite `REAL` becomes
PostgreSQL `DOUBLE PRECISION` to preserve score precision. Conflict handling and
table introspection are adapted only for application-owned SQL.

PostgreSQL schema creation, migrations, seeding, and version changes commit in one
transaction. A failed migration rolls back; later startup can retry. Startup never
drops or resets learner tables. A separate additive `staging_resources` table
records browser ownership of learners, assessments and chat sessions.

Short transactions use a PostgreSQL advisory transaction lock to preserve the
existing SQLite serialization assumptions. Connections close after each transaction;
Supabase's session pooler supplies pooling. Connections are re-established on later
requests, with bounded connect/statement/lock timeouts. Failed writes are not silently
retried. This simple serialization is appropriate for a small private alpha, not
large concurrent traffic. Keep one application worker for existing in-memory locks.

## Access, ownership, and quota limitations

The access code is checked server-side with constant-time comparison. The cookie
contains a signed random identity and expiration, never the access code. In staging
it is `Secure`, `HttpOnly`, and `SameSite=Strict`. Authorization lasts seven days by
default; the signed identity cookie remains for up to a year so re-entering the
access code can preserve ownership. Rotating the signing key invalidates ownership
cookies; do this deliberately. Rotating the access code alone does not revoke
already-issued sessions before their expiry.

This is browser-based private-alpha access, not user accounts. Different browsers
get different identities, even with the same access code. Sharing a learner UUID
does not grant access. Clearing cookies or changing the signing secret loses the
browser's ability to access its existing learners; records remain in the database.
There is no account recovery or cross-device progress synchronization yet. Do not
claim older unowned learners by supplying an ID. Existing local learners remain
available locally with staging access disabled.

AI-capable routes allow 40 attempts per browser identity per hour, with a global
200/hour cap. Placement answers and activity submissions count conservatively even
when graded deterministically or replayed. Invalid bodies and ownership failures
are rejected earlier. Login has per-client and global limits. Limits are in memory
and reset on restart; they are not a distributed quota system. LLM retries remain
bounded, and health, login, ordinary reads, mastery, and SRS do not generate AI calls.

Bodies are capped at 32 KiB; study text keeps its existing 4,000-character limit.
Provider output tokens remain server-controlled. Deterministic scope rules reject
obvious unrelated tasks and common injection/extraction attempts before inference.
Short English answers are allowed for an actual server-held exercise. Ambiguous
standalone requests ask the learner to frame the question as Japanese study.
These conservative rules and existing teacher/evaluator instructions are useful
defenses, not a proof against every adversarial paraphrase. They may need tuning;
no paid classifier or secret/file/tool access is given to the model.

## Provider failover

Gemini success never calls Groq. Eligible rate/quota failures, connection errors,
timeouts and temporary 5xx failures may trigger one Groq attempt. Authentication,
model configuration, invalid output, input validation, local limits, database errors,
scope rejection and safety refusals do not trigger fallback.

The primary gets half the existing total inference deadline; fallback uses the
remaining budget, with a small margin. Outer tutor/evaluator timeouts remain in
force. Both failures return safe errors. The existing evaluator can record unavailable
evidence without scoring it as a learner mistake; study grading failures remain
retryable without committing progress. Schema validation and idempotency remain
in the application, after inference. Existing lesson schema-repair retries remain
bounded at two generations with failover disabled. With failover enabled, the
router additionally limits the entire HTTP request to one primary and one fallback
attempt, including schema-repair paths; it never recursively alternates providers.

Logs contain safe failure categories, selected provider/model, environment/database
type and fallback reason. They omit raw vendor responses, connection strings,
authorization headers, prompts and conversation contents. Uvicorn access logs are
disabled by the documented start command to avoid recording learner URLs.

## Privacy and source packaging

`.env`, private reference directories, local databases and their sidecar files stay
ignored. An explicit exception includes only the application-authored placement
bank `app/assessment/data/questions.json`; it is not a private reference resource.
FastAPI serves only `frontend/` as static content. `.dockerignore` is a restrictive
allowlist for any future Docker use; no Docker image is built in this phase.

Run `python scripts/audit_deployment.py` before committing or pushing. It checks
working source and available history without printing secret matches. It is a
heuristic audit, not a guarantee against every possible secret format. CI runs it
too. No reference files are read, ingested, copied, committed, or uploaded.

## Verification and acceptance checklist

Local: `python -m pytest -q`. To include PostgreSQL, set `TEST_POSTGRES_URL` privately
to an isolated loopback PostgreSQL administrator connection. Tests create and remove
only randomly named `tutor_test_*` databases; remote hosts are refused. Never point
this variable at Supabase. CI supplies its own disposable database service.

After deployment, use a disposable staging learner to verify:

1. HTTPS health, access page, wrong-code rejection, successful login and safe headers.
2. Gemini tutor question: “Explain は and が to an N5 learner.” Check structured reply.
3. Start/finish placement; reload profile, preferences, saved chat and history.
4. Create a study plan; complete an activity; confirm mastery and review scheduling.
5. Retry the same submission; verify no duplicate progress.
6. Restart the Render service, reopen the browser and confirm PostgreSQL progress.
7. Open a second browser identity; confirm the first learner's IDs return 404.
8. Check phone access, narrow layout, private-file 404s, and browser assets/network
   for absence of secrets. A real phone test still requires the owner.
9. Confirm Groq configuration without exhausting Gemini quota. Automated failover
   tests inject transient failures; do not add a public “force fallback” endpoint.

## Recovery, cost, and rollout

Render logs are under the service's **Logs** menu; **Events** shows deploy status.
On failure identify configuration, build, database/migration, provider or origin
errors using safe categories. Never paste full logs containing secrets into chat.

Keep the Phase 6 checkpoint `6eb6014`. It can run locally with the existing local
SQLite data. It cannot safely replace the cloud app because it lacks PostgreSQL
and staging access. For cloud rollback choose the latest verified **Phase 6.5**
commit in Render, keep database and signing secrets unchanged, and disable automatic
deploy temporarily if necessary. If no safe cloud version exists, suspend access
while repairing. Never auto-downgrade schemas, reset learner data, or force-push.

Expected infrastructure cost is $0 within the already selected free-tier limits.
No paid resources are created by this code. Gemini/Groq usage depends on account
quota and billing settings; do not enable paid billing or buy additional capacity
automatically. Render sleeps after inactivity and has an ephemeral filesystem;
no keep-alive traffic is introduced. Supabase free projects may pause when inactive.
See [Render free limits](https://render.com/docs/free).

Supabase recommends regular private exports for free-tier databases; paid plans
provide managed daily backup access. Before important staging tests or upgrades,
export the `tutor_private` schema and its data with `pg_dump`/Supabase CLI to a private
location outside Git, using credentials from a protected environment. Verify a
restore into a separate disposable database before relying on a backup. Never
restore over the live database casually. No production-grade backup guarantee is
claimed. See [Supabase backups](https://supabase.com/docs/guides/platform/backups).

Phase 7 should begin only after the live checklist passes. UI overhaul, production
accounts, cross-device identity recovery, and RAG remain separate work.
