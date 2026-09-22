# Phase 4.5 runtime verification and repair

Verified 2026-09-22. Phase 5 was not started.

## Root cause and confidence

The original screenshot's exact upstream cause cannot be established retrospectively.
The old adapter collapsed most non-success HTTP responses into `provider_failure` and
discarded the status and provider error details. No matching original error log was
available. A transient upstream failure is plausible (an earlier live verification
encountered a Google 503), but that does not prove the screenshot had the same cause.

The actual port-8001 frontend successfully answered the requested は/が question **before
any code changes or restart**. This rules out a persistent inability to make structured
Gemini calls at verification time. It would be inaccurate to claim the original failure
was reproduced or to attribute it conclusively to a stale process, schema or CORS.

Confirmed infrastructure gaps were repaired: failure diagnostics were insufficient,
the default/example model still used the model that returned 404 during earlier live
tests, and default `.env` discovery depended on the launch working directory.

## Actual running configuration

- URL and backend: `http://127.0.0.1:8001`, loopback only.
- Provider: `gemini`.
- Model: `gemini-3.1-flash-lite`.
- `GEMINI_API_KEY` present: yes. Its value was never printed.
- Project and working directory: the `outputs/japanese-tutor` directory in this workspace.
- Environment file: this project's `.env`, beside README.md. One private `.env` was found
  in this workspace; `.env.example` is a separate template, not a runtime source.
- Frontend: relative `/api/...` calls to its own origin. No separate provider configuration,
  backend URL, proxy or CORS workaround is involved.
- One provider object is shared by tutor, assessment evaluator, curriculum content and
  curriculum evaluator. Learning modules contain no direct vendor imports/calls.
- The active application still uses its existing project `.venv` Python interpreter.

The old launcher started at 01:31:31, after the local `.env` was last changed at 01:29:39.
It therefore was not shown to predate that configuration change. Its health endpoint
did not expose the model, so its exact in-memory settings cannot be independently
recovered after shutdown. The restarted process's startup log and health endpoint both
confirm the provider/model/key presence listed above.

During the clean restart, the development reload worker retained the listening socket
after its supervisor was stopped. The new server initially could not bind port 8001.
The identified orphan worker was stopped and the server restarted successfully on the
same port. That restart obstacle was real, but it is not evidence that the worker caused
the earlier screenshot error. The current server runs without an autoreload supervisor.

## Changes

- `app/config.py`: load the project `.env` using an absolute application-relative path.
- `app/llm/common.py`: shared model defaults, safe HTTP diagnostics, request-route context.
- `app/llm/gemini.py`: current verified default; actionable 404/5xx messages and safe logs.
- `app/llm/openai.py`: shared default and safe HTTP diagnostics; existing API behavior retained.
- `app/llm/factory.py`: sanitized runtime provider/model/key-presence metadata.
- `app/api/chat.py`: health reports the loaded runtime configuration without credentials.
- `app/main.py`: startup configuration diagnostics and per-request route-template context.
- `.env.example`: verified Gemini default model.
- `tests/test_multi_provider.py`: expectation updated for the new default.
- `tests/test_runtime_configuration.py`: ten regression cases for environment loading,
  configuration snapshots, secret-safe errors, route logging and actionable failures.
- `README.md`, `docs/provider-design.md`: current setup and runtime troubleshooting.
- This report and the refreshed Phase 4.5 archive document the current result.

Workspace-only live harness: `work/verify_runtime_gemini.py`. It is opt-in, uses local
credentials without embedding them, and is not collected by pytest. Runtime console
logs are in `work/tutor-runtime.stdout.log` and `work/tutor-runtime.stderr.log`.

No changes to placement scoring, learner memory, curriculum ranking, schema validation,
mastery, context limits or frontend assets. No new dependency, fallback router or automatic
provider retry. Existing learner data was not altered for verification; service tests
used a temporary database and actual-server chat checks used temporary conversations.

## Verification

1. Direct Gemini text generation: passed.
2. Factory-selected common provider text generation: passed.
3. Gemini JSON structured output validated against TutorResponse: passed.
4. Actual TutorService through shared provider: passed.
5. Actual port-8001 `/api/chat` endpoint: chat, sentence correction and grammar passed.
6. Actual browser frontend: submitted the は/が prompt, received HTTP 200, and visibly
   displayed the Gemini answer, explanation, examples and exercise. Verified both before
   changes and after a clean restart. The successful tab remains open.
7. Phase 2 free-response evaluator: live non-reference answer used `method=llm`, passed.
8. Phase 3 profile context and observed tutor response: live temporary learner passed.
9. Phase 4 generated grammar lesson: real plan/start/open path with a temporary learner passed.
10. Offline regressions: **250 passed**, including OpenAI selection/payload/error coverage,
    fake-provider learning tests and safe diagnostic tests. Two pre-existing dependency
    deprecation warnings remain. The suite passed in both the original Python 3.12
    verification environment (17.58 seconds) and the running app's Python 3.14 `.venv`
    (47.79 seconds). The latter used a fresh workspace temporary directory and disabled
    pytest's cache after Windows denied access to the other environment's shared test
    temporary/cache folders; no application change was required for that test setup issue.

All live checks used the configured Gemini model. OpenAI was verified offline; no OpenAI
key or paid OpenAI request was required. Provider-specific envelopes stayed inside adapters.
Nullable fields, schema definitions and application validation succeeded without relaxation.

## Result and remaining limits

The full browser → backend → tutor → common interface → Gemini → validated response →
browser display path currently works. Safe diagnostics now distinguish model/configuration,
rate-limit and service errors if another failure occurs. Provider outages, quotas, future
model retirement and generated-language quality cannot be guaranteed by a successful run.
The original screenshot's precise HTTP status remains unknown; no unsupported root-cause
claim is made. Restart the backend after changing `.env` because settings are loaded once.
