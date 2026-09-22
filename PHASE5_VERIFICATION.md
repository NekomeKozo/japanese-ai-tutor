# Phase 5 verification — 2026-09-22

## Automated checks

- Python 3.12 test environment: **298 passed**, 2 upstream deprecation warnings, 20.39s.
- Actual app Python 3.14 environment: **298 passed**, same 2 warnings, 55.00s.
- 48 new mastery cases plus all 250 prior-phase regression cases.
- All application Python files compile. Mastery JavaScript passes the Node syntax check.
- Tests use temporary databases and blocked external HTTP transports. No paid model calls
  were made for this Phase 5 verification. Existing Gemini/OpenAI adapter regression tests
  pass; provider source and configuration are checked unchanged against Phase 4.5.

The warnings originate in Starlette's HTTPX TestClient and AnyIO BlockingPortal aliases.
They did not affect either test run.

## Covered behavior

Unknown dimensions, first-success conservatism, partial credit, repeated success/failure,
recognition versus production, hint uncertainty, bounded difficulty/source quality,
single-error stability, decline/recovery, independent/diverse contexts, identical-question
discounting, each of 13 dimensions, invalid/unknown evidence, no vocabulary-to-kanji
transfer, required kanji reading context, placement caps, persistence, duplicate retries,
transaction rollback, restart/recomputation/history equality, learner scoping, API filters,
curriculum result/retry integration, correction-mode production, planning fallback and
dimension focus, local fixed content, migration preservation/idempotency/rollback,
placement initialization, conservative legacy evidence, deterministic ordering, bounded
overall first-dimension changes, reset compatibility and future-facing query helpers.

Synthetic A: recognition success does not hide weak vocabulary production.
Synthetic B: sustained varied grammar evidence can establish strong mastery.
Synthetic C: repeated recent production failure after established strength flags review.
Synthetic D: uneven kanji dimensions remain separate; untested production stays null.

## Browser checks

Used a separate synthetic database and offline provider on port 8002. The actual app's
learner database was not populated with synthetic events. Verified:

- Phase 5 page and My learning → Japanese Knowledge load.
- Topic list displays varied grammar as Strong / High confidence and uneven vocabulary
  as Learning / Limited evidence.
- Vocabulary and Learning filters correctly reduce the list to one matching topic.
- 食べる detail separates recognition from production and leaves meaning/reading unknown.
- 学 detail leaves recognition, kun-reading and production unknown, retains meaning and
  tested on-reading, and displays 学生 as its tested context.
- Layout inspected at the browser's narrow and wider visible widths; text stays readable.
- Existing learner profile summaries, preferences and sessions remain present.

## Actual local migration and runtime

Before migration, the tutor was not listening on port 8001. Created a private SQLite API
backup outside the release archive, then applied schema v3 → v4. Compared every original
row in all 15 existing tables: **146 rows preserved exactly**, with only additive canonical
catalog rows permitted. SQLite integrity check returned `ok`. There was no qualifying
historical performance evidence in this database, so zero derived evidence/state/history
rows is expected; API/UI present unknown topics until scored practice occurs. Migration
backfill with qualifying evidence is separately covered by automated tests.

Backup: `work/phase5-pre-migration-20260922-115804.sqlite3` in the parent workspace.
The backup contains private learner data and is intentionally excluded from the ZIP.

Started the upgraded app using its existing `.venv` and private `.env` on loopback port
8001. Health reports ready, Gemini configured, model `gemini-3.1-flash-lite`, key present.
No credential value was displayed or put into reports. Health is a configuration/startup
check, not a new paid Gemini inference test; the prior live verification remains documented
in `PHASE4_5_RUNTIME_REPORT.md`.

## Release checks

The packaging script retains every baseline source file, verifies Gemini/OpenAI provider
and configuration files are unchanged, checks ZIP integrity, excludes `.env`, databases,
local environments, caches and logs, and scans bundled bytes against configured secret
values without printing them. Phase 4.5 archive remains available separately.

No scheduling or other Phase 6 functionality was implemented.
