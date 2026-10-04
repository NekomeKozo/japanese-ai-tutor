# Phase 11F — Website performance and resource optimization

## Initial inspection

Started on `main` at `c990366`, including the complete Phase 11E implementation (`b9b1f45`) and its report. Tracked files were clean. Existing untracked design discovery, mockups and original/iPhone screenshots were preserved and excluded from this commit. Remote main had no divergent changes; the existing unpushed Phase 11E report commit is included in the normal push.

Focused inspection covered frontend loading, Home/Profile/Review requests, application startup, question-bank initialization, database connections and ownership checks. The vanilla frontend already defers its 20 initial JS/CSS resources, uses system fonts, renders one flashcard at a time and lazily loads its public catalog. No large production images, model initialization or framework bundle justified a redesign/build pipeline. Provider clients already share the lifespan HTTP client; knowledge retrieval is bounded and lazy.

Measured bottlenecks: blanket `no-store` forces full static transfers; identical overlapping API reads and the initial Home profile read are redundant; startup inserts each of 68 authored questions separately; synchronous database reads/ownership checks run on the event loop.

## Changes

- Compress static responses only using the existing Starlette dependency. HTML, learner APIs and uploaded audio remain outside compression.
- Compute an asset version once from authored frontend content. Initial JS/CSS and the lazy catalog use that version. Successful versioned public assets use **private** immutable browser caching; unversioned/old-version requests must revalidate. HTML, APIs and failures remain `no-store`. No shared learner cache, service worker or offline storage was added.
- Share only equivalent **in-flight** GETs; clone each result for its caller. Drop pending references on learner changes, learning updates and mutation start; settled responses are never retained. Custom headers/signals bypass sharing. Initial Home rendering reuses the profile just restored by bootstrap; subsequent visits fetch fresh data.
- Run profile/activity/saved-session/study reads, ReviewService calls and existing ownership checks in Starlette's bounded worker pool. Authentication, request limits, origin rules, SQL transactions, advisory locks and idempotent review receipts remain in place. Connections are opened and closed inside their worker calls.
- Batch bound question-bank inserts in groups of at most 100, retaining insert-if-missing behavior and existing rows. No schema, learning data, scheduler, mastery, provider or infrastructure changes.

Files: `app/{main,safeguards,web_assets}.py`, `app/api/{learner,curriculum,reviews}.py`, `app/assessment/repository.py`, `frontend/{app,shell,flashcard-catalog}.js`, `tests/{test_web_performance,test_postgres}.py`, `tests/frontend.test.cjs`, the two benchmark scripts, `design/performance/phase11f/` and this report.

## Reproducible measurements

Raw results: [design/performance/phase11f](design/performance/phase11f/). Baseline was captured before production edits. Backend script uses disposable SQLite, TestClient/ASGI and a provider that fails if called; frontend script runs real scripts in the existing mocked DOM/fetch harness. No live database or AI requests are used.

```text
python scripts/benchmark_performance.py --output /path/to/results.json
node scripts/benchmark_frontend.cjs /path/to/frontend-results.json
```

| Local measurement | Before | After |
| --- | ---: | ---: |
| Initial JS/CSS resource count | 20 | 20 |
| Initial JS/CSS raw bytes | 186,153 | 187,594 |
| Initial JS/CSS body transfer, gzip accepted | 186,153 | 57,433 |
| Repeat static body bytes under fresh cache policy | 186,153 | 0 |
| Three simultaneous identical GETs, network calls | 3 | 1 |
| 50 Free Practice render/reveal/navigation cycles, network calls | 0 | 0 |
| Startup question-bank insert statements | 68 | 1 |
| Local startup, one sample | 151.24 ms | 132.08 ms |
| Warm profile latency, median of 10 sequential requests | 2.39 ms | 2.77 ms |
| Health completion during a simulated 150 ms profile read | 157.75 ms | 2.62 ms |

Static body transfer fell **69.1%**. The raw-size increase is the small request-sharing helper. Repeat bytes describe a fresh immutable cache entry, not guaranteed request counts across browsers; ETag/304 behavior is tested separately. Warm SQLite latency did not improve; worker dispatch has slight overhead. Startup samples are indicative, not a Render cold-start speedup claim. The contention experiment isolates event-loop blocking, not production database latency or capacity. The startup sample excludes app construction/asset fingerprinting; question-bank statement count is the reliable remote round-trip reduction.

LCP, CLS and INP are **unavailable**: the supported browser inspection surface does not expose Performance entries. VM rendering is not a paint metric. Browser heap/CPU and network-throttled timings were not reliably measurable. No invented Lighthouse/Core Web Vitals score.

## Verification

- Frontend regression: **139 passed**, including new sharing/invalidation/cloning/retry/auth, initial profile reuse and versioned catalog tests; existing Flashcards, navigation, drafts, TTS, microphone/transcription cleanup and voice tests remain passing. All JavaScript syntax and diff whitespace checks passed.
- Focused backend: **189 passed, 7 PostgreSQL tests skipped locally**; separate Tutor/audio/conversation regression: **117 passed, 7 optional tests skipped**. Existing dependency deprecation warnings only. Offline transport guards prevent accidental external calls.
- Tests verify identical decoded compressed assets, version invalidation, conditional responses, private cache boundaries, denied access/ownership, unchanged existing bank rows, missing-row restoration and responsive health during a blocked worker read. Existing PostgreSQL integration coverage also checks batched initialization/restoration; it runs in the normal disposable CI database.
- Local browser: Free Practice reveal, Japanese answer/player controls, Due Reviews, rating receipt/advance and reload persistence verified with a disposable learner; one saved review changes four due targets to three. No production ratings were submitted.
- Exact emulated CSS widths **320, 390, 430, 768, 1440** checked for Flashcards and Home, Tutor, Progress, Settings, Placement, JLPT, Listening and Speaking setup. No document overflow or visible error states; existing theme/layout/styles were unchanged. Desktop and narrow screenshots retained in task outputs. These are browser emulation checks, not a new physical-phone/Safari or audible-audio test.

## Deployment and hosting limits

Implementation commit `568c359` was pushed to `main` through the existing Render auto-deployment workflow. [GitHub Tests](https://github.com/NekomeKozo/japanese-ai-tutor/actions/runs/37194641205) passed, including the full backend suite, disposable PostgreSQL initialization/restoration and receipt tests, source/history audit, JavaScript syntax and all 139 frontend tests. No service/database recreation, billing changes, Supabase settings changes, paid calls, load testing or keep-alive traffic.

Live verification on October 4, 2026: the freshly loaded HTML uses the new asset version; Home restores the existing learner, Free Practice loads its versioned catalog and supports reveal/next, and Due Reviews retrieves the existing scheduled queue. No live rating, chat, recording or learner mutation was submitted. Desktop at 1440px and mobile emulation at 390px have no document overflow; revealed rating controls are reachable by keyboard (focused Hard button at 478–550px in a 900px viewport). Live captures are retained in task outputs. The live versioned stylesheet uses gzip and private immutable caching and matches the local content after line-ending normalization.

The first public health check timed out after 25 seconds; that observation alone cannot establish whether sleep/wake, deployment turnover or networking caused it. A later warm `/health` request returned 200 in 86.9ms including client/network overhead, with `no-store`; the stylesheet returned 200 in 91.21ms. These are single live round trips, not database latency, a cold-start benchmark or a Core Web Vitals score. Unauthenticated API/static probes returned 401/no-store. Results are retained in `design/performance/phase11f/live-checks.json`.

Render sleep/wake, image build and remote PostgreSQL connection/lock latency are distinct from warm app performance. This phase does not remove sleep or serialization protections. AI generation/transcription latency is unchanged and not rebenchmarked using paid/real calls. Other synchronous backend workflows remain potential future profiling targets; worker dispatch alone does not remove database contention.

## Phase 11G handover

Recheck on the user's actual phone and inspect genuine browser performance traces when available. Preserve `no-store` for all learner responses and version public assets when adding any offline feature. Keep review receipt/version protections and existing scheduling semantics. Any connection-pool or lock change requires separate measured analysis. No PWA/service worker/offline sync or Phase 11G work was started. **Stop after Phase 11F.**
