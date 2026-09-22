# Phase 3 verification

Verified locally on Windows, Python 3.12, using the existing locked dependencies.

- Full offline suite: **139 passed** (102 existing cases plus 37 Phase 3 cases).
- Two existing upstream Starlette/AnyIO deprecation warnings; no test failures.
- Python compilation and syntax checks for all three frontend JavaScript files passed.
- SQLite v1 fixture with active and completed assessments migrated without changing any
  of the four original tables' rows. Repeated startup did not duplicate placement events.
- Simulated migration failure rolled back new tables and retained schema v1 and profiles.
- Tested profile/preferences/session persistence across app restart; canonical aliases,
  unknown/malformed observations, exposure vs competence, weakness recovery, bounded
  history/context, learner ownership, duplicate/conflicting requests and event IDs.
- Tested event/turn/state rollback, stale session writers, provider failure recovery,
  one skill update per turn, capped drift, easy-content limits, aging mistakes and scoped
  reset with required matching confirmation.

Browser checks used the real application at port 8000 and a separate offline provider
fixture at port 8001. Fixture data lives under the workspace `work` directory, outside
the deliverable. The real existing Phase 2 preview database upgraded successfully.

- Existing completed placement rendered correctly and opened a saved learner session.
- My learning displayed skill estimates, placement evidence, weaknesses, vocabulary,
  grammar, kanji memory, preferences and session/activity history.
- Changed romaji preference and travel goal; both remained selected after refresh.
- Created a default learner; sent three mock-provider chat messages, observed one
  canonical destination-particle pattern become active and a topic become needs-review.
- Refreshed and restored all three saved exchanges from the backend.
- New session preserved learning memory and closed the previous session; View reopened
  the closed transcript with the correct closed-session notice.
- Inspected the profile layout in the browser; no console errors in the mock flow.

Live provider tutoring/observation quality was not verified because no API key is
configured. Mock observations validate application plumbing, not linguistic accuracy.
This phase does not validate topic difficulty or mastery thresholds against real learners.

Historical Phase 2 verification remains in `VERIFICATION.md`. The Phase 3 source archive
excludes SQLite files, secrets, virtual environments, caches and browser-test fixtures.
