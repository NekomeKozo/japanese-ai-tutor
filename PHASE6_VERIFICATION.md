# Phase 6 verification — 2026-09-22

## Automated results

The release suite passes **355 tests** in the actual app Python 3.14 environment,
66.76 seconds, with two pre-existing Starlette/AnyIO deprecation warnings. This comprises
all 298 earlier regression cases and 57 new scheduler cases. The final Python 3.12
suite also passed all **355 tests**, in 26.37 seconds, after the bootstrap boundary fix.
Tests block external HTTP transports and use temporary databases.
Python compilation and syntax checks for reviews.js/study.js passed.

Coverage includes rating thresholds and partial credit; hints/independence; invalid scores;
FSRS determinism; conservative initial intervals; Easy/Good/Hard growth; recognition versus
production; confidence caps; lapse/relearning; persistent difficulty; three-attempt guard;
UTC and backward-clock checks; 12 executable dimensions; unseen material; duplicate events;
queue timing, capacity, variety, priorities and suspension; long absence; safe restart;
completed-result retry; stale schedule versions; grading/content failures; atomic rollback;
attempt replay; schema v4→v5 migration and rollback; mixed-strength midnight bootstrap
capacity; local-day forecast boundaries; answer secrecy; prompt variety; and query ownership.

Synthetic scenarios correspond to the brief: A uneven 図書館; B 15 strong spaced vocabulary
successes; C strong history followed by a lapse; D chronic failures; E a 90-day absence
and capped backlog; F uneven 学 meaning/recognition/reading. No test relies on real time
for scheduler calculations. Existing provider/tutor/placement/mastery/curriculum regressions
remain in the full suite.

## Review-load simulation

100 virtual review targets, introduced 10/day over 10 days, then reviewed when due during
42 virtual days. Total subsequent reviews: **219**. Peak on any day: **14**. Daily counts:

```
0 0 0 6 9 8 11 10 11 9 9 12 14 12 7 9 11 11 10 8 11
10 5 7 0 0 0 0 0 0 0 0 0 0 0 0 1 3 2 7 2 4
```

This is a deterministic strong-success cohort check, not real-user retention validation.
It demonstrates no 80-review spike under this introduction pattern. Simultaneously
learning many items, absences and different outcomes can still create larger backlogs;
the queue/time-budget cap handles them separately.

## Browser verification

Used an isolated database on port 8002 with a provider that rejects any model call.
Verified the complete Daily Review flow with three due targets in a ten-minute budget:

1. Queue displayed vocabulary 2 / kanji 1, selecting three items totaling seven minutes.
2. Production question headings/plan labels concealed the Japanese answer. The initial
   browser check found this cue leak; it was fixed and a regression assertion was added.
3. Submitted たべる for the English production cue. Result saved and next review moved
   roughly two days ahead; due count decreased from three to two.
4. Continued to 学 in the context 学生. Submitted an incorrect reading; result saved with
   a 15-minute retry. The future-today forecast included it while the executable queue did not.
5. Skipped 図書館 reading. Session recap recorded one success, one struggling item and one
   skip. The skipped target remained due, without a failure or successful reschedule.
6. Screenshot inspection confirmed a readable recap and existing study layout.

The preview learner and attempts were not added to the actual user database. No paid model
requests were needed. Dynamic grammar and grading failures were tested with fake providers.
The earlier live Gemini verification remains in PHASE4_5_RUNTIME_REPORT.md; this phase
does not claim a new paid inference test.

## Actual database and app

Created a SQLite backup before upgrading actual schema v4→v5. **172 original rows across
18 tables were preserved exactly.** SQLite integrity and foreign-key checks passed.
No measured historical mastery existed in that database, so zero bootstrap schedules is
expected; eligible practice will create schedules. Synthetic bootstrap tests exercise
the populated-data path, safe staggering, idempotency and rollback.

Private backup (outside the archive):
`work/phase6-pre-migration-20260922-172255.sqlite3` in the parent workspace.

Installed pinned fsrs/tzdata dependencies into the existing app environment. Started the
upgraded tutor on loopback port 8001. Health confirmed Gemini configuration still loaded,
model gemini-3.1-flash-lite and key-present status, without displaying the key.

## Release boundaries

Packaging retains all Phase 5 source files. Provider/configuration, assessment scoring,
tutor core and Phase 5 mastery calculation/policy/normalization are checked unchanged.
The ZIP excludes credentials, environments, caches, logs and learner databases and is
scanned against configured secret values without printing them. The Phase 5 baseline ZIP
is retained separately. No Phase 7 features are included.
