# Deployment

## Current topology

Canonical production origin: **https://goigrow.onrender.com**.
The primary service is `goigrow`, a Free Python web service in the existing
GoiGrow / Production Render environment. Its application configuration remains
private `staging`. One FastAPI process serves frontend and API; the existing
Supabase project supplies PostgreSQL and Auth.

Temporary rollback note: `goigrow-legacy` remains at
https://japanese-ai-tutor.onrender.com. Keep it and its approved callback/recovery
entries until retirement is separately approved and original-profile access is
verified. Cookies/storage do not migrate automatically between these hostnames.
Do not create another service/database as a routine deployment step.

## Render configuration

Maintain the existing Git-provider connection, production `main` branch, Singapore
region, Free plan, single instance and single worker. Current commands are:

```sh
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

Health check path is `/health`; automatic deployment is On Commit. These are
descriptions of the reviewed service, not instructions to change it during a doc edit.
CI separately checks the locked dependency stack. A change to lock-file installation,
CI-gated deploys or access logging should be a reviewed infrastructure change.
There are no linked environment groups or private checkpoint files required for the
normal running deployment. If groups are later used, verify linkage and precedence
before moving services; direct service variables override group values.

## Required configuration

Keep values in the existing authorized secret mechanism. The table gives names
and safe purposes only; `.env.example` supplies local defaults, not production secrets.

| Variables | Purpose |
|---|---|
| `ENVIRONMENT`, `FRONTEND_URL` | Application mode and exact public HTTPS origin used by mutation checks |
| `DATABASE_URL` | Backend-only connection to the existing Supabase PostgreSQL database; remote TLS required |
| `STAGING_ACCESS_ENABLED`, `STAGING_ACCESS_CODE`, `STAGING_SESSION_SECRET`, `STAGING_SESSION_HOURS` | Private entry gate, signed legacy browser ownership and authorization lifetime |
| `SCOPE_ENFORCEMENT_ENABLED` | Japanese-learning request scope enforcement |
| `ACCOUNT_AUTH_ENABLED` | Independent account feature control; do not change implicitly |
| `SUPABASE_AUTH_URL`, `SUPABASE_AUTH_PUBLISHABLE_KEY`, `SUPABASE_AUTH_TIMEOUT_SECONDS` | Trusted Auth project, supported non-admin key and bounded provider verification |
| `ACCOUNT_INVITED_IDS` | Exact canonical account UUID allowlist; values remain private |
| `ACCOUNT_OWNER_BOOTSTRAP_IDS` | Optional single approved owner already in the allowlist; no invitation-timestamp requirement for that identity |
| `ACCOUNT_SESSION_ENCRYPTION_KEYS` | Ordered private encryption key ring for server-side provider tokens; retain backup/rotation compatibility |
| `ACCOUNT_LEARNER_LINKING_ENABLED` | Separate linking activation control; currently disabled |
| `ACCOUNT_LEARNER_CHECKPOINT_PATH` | Optional private operator proof configuration; normal deployment leaves it unset |
| `LLM_PROVIDER`, `LLM_MODEL`, `LLM_TIMEOUT_SECONDS`, `LLM_MAX_OUTPUT_TOKENS` | Selected tutoring adapter/model and generation limits |
| `GEMINI_API_KEY`, `GROQ_API_KEY`, `OPENAI_API_KEY` | Credentials only for deliberately configured providers |
| `GROQ_MODEL`, `LLM_FAILOVER_ENABLED`, `LLM_FALLBACK_PROVIDER` | Bounded Gemini-to-Groq failover when configured |
| `AI_RATE_LIMIT_PER_HOUR`, `AI_GLOBAL_RATE_LIMIT_PER_HOUR` | Application inference limits; include process-local state |
| `STT_ENABLED`, `STT_TIMEOUT_SECONDS`, `STT_RATE_LIMIT_PER_HOUR`, `STT_GLOBAL_RATE_LIMIT_PER_HOUR`, `STT_GLOBAL_RATE_LIMIT_PER_DAY` | Explicit Japanese transcription availability and bounded usage |
| `KNOWLEDGE_ENABLED`, `KNOWLEDGE_DB_PATH`, `KNOWLEDGE_TOP_K`, `KNOWLEDGE_CONTEXT_LIMIT`, `KNOWLEDGE_MIN_SCORE` | Optional existing private derived-index retrieval |

Settings validation requires secure origins, a PostgreSQL connection and the existing
staging/scope protections in staging mode. Account activation additionally requires
valid provider configuration, encryption keys and account allowlists. It must fail
closed rather than silently fall back to a new SQLite store. Preserve signing/encryption
keys across service changes; changing them can affect access to existing contexts/sessions.

The server resolves `.env` beside the application; process environment takes precedence.
After configuration changes, use an actual deploy that incorporates the saved values.
A Render restart reuses the running deploy's environment values, so it is not a substitute
for deploying a pending configuration change. Verify the exact deploy becomes Live.

## Supabase Auth URLs and policy

Default Site URL is the base origin **https://goigrow.onrender.com**.
The explicit production Redirect URLs are:

- https://goigrow.onrender.com/auth/callback
- https://goigrow.onrender.com/auth/recovery

Retain the approved temporary legacy-host callback/recovery entries for rollback
and the existing exact localhost development entries. Do not broaden to wildcard
redirects or arbitrary `next` URLs. Current local callbacks use
http://localhost:8012/auth/callback and http://localhost:8012/auth/recovery.

Public provider signup remains disabled, email confirmation required and approved
email/password sign-in enforced. Do not change users, passwords, allowlists, provider
settings or SMTP as part of hostname maintenance. Default provider mail restrictions
must be checked before inviting external testers; do not assume general public email
delivery, paid billing or a completed one-click invitation/recovery experience.

## Storage, upgrades and backups

Use the same existing PostgreSQL database, never a replacement empty learner store.
The private schema and ownership boundaries are described in [architecture](architecture.md).
An IPv4-compatible Supabase pooler may be needed by the hosting network; preserve
the verified connection and check hostname/SSL/URI encoding privately. Never print
the connection string, pass it in public command examples or weaken TLS to fix access.

Learning migrations are additive and transactional; the current schema version is 8.
Auth/session and association schema changes have their own reviewed boundaries.
Before a migration, back up and verify the intended database and inspect role grants,
dependencies, compatibility and rollback. Rehearse on a disposable database. Preserve
learner/history fingerprints and IDs; never reset, seed a replacement or fabricate Auth
state to solve a startup issue. Keep session-encryption-key backups separately private.

Optional knowledge import is explicit, separate from startup, and uses only derived
records. Do not upload raw reference documents to Render. [Knowledge operations](knowledge.md).

## Verification and rollback

After an authorized deploy, verify:

1. Expected service, branch and commit are Live; startup completes.
2. `/health` is healthy and fast without inference. Protected `/ready` checks storage.
3. Staging entry remains enforced and cookie-free protected APIs are denied.
4. The approved owner account path works and linking remains in its intended state.
5. Same database/project, unchanged history and expected association-table state.
6. Exact origins/redirects, provider limits, environment keys and group linkage survive.

Do not create learners or exercise linking merely to test infrastructure. A process
liveness response does not prove database availability, owner identity or model quota.
Private free services can spin down, and a paused database must be resumed in the
existing project instead of replaced. Diagnose redacted exception categories and
configuration presence without copying full logs or secrets into public reports.

Retain a compatible known-good service/build during cutover. Rollback does not undo
database or provider writes. Do not drop additive tables, rewrite history or restore
an old staging-only authorizer over linked data. Keep the original browser context
available until profile restoration is explicitly verified. Retirement, activation,
destructive repair and provider/billing changes require separate authorization.
