# Phase 4 verification

Verified locally on Windows using Python 3.12 and the existing locked dependencies.
No dependency installation or live-provider calls were required.

## Automated checks

- **196 tests passed**: all 139 prior-phase cases plus 57 Phase 4 cases.
- The prior migration test now expects the latest schema v3 and reconstructs the same
  original v1 fixture by removing newer study tables. Its preservation assertions remain.
- Two existing upstream Starlette/AnyIO deprecation warnings remain; no test failures.
- Python compilation and syntax checks for all four frontend scripts passed.

Coverage includes cold-start/placement-only/mature profiles; weak/repeated/strong topic
ranking; age and repetition; prerequisites; goals/focus; short/long time budgets and
variety; struggling/strong/returning/uneven skill profiles; deterministic plans; active
resume; event/result replay; skip semantics; malformed/wrong-identity lessons; provider
and grading failures; compact context; atomic result rollback; learner ownership and
activity ordering; abandonment; v2 data preservation and migration rollback; scoped reset;
restart; stale generation after a skip; cancelled generation; plan schema validation;
and two app instances racing to create a single active plan.

Synthetic learners A–D from the brief are covered explicitly: N5 particle weakness,
N4 kanji weakness after grammar-heavy study, N3 return after 60 days, and N3 vocabulary
with N5 grammar. These validate planner behavior, not educational calibration.

## Browser verification

Real application on port 8000 used the existing Phase 2/3 preview database, upgraded
additively to v3. A separate offline provider fixture on port 8001 supplied structured
generated content without network calls. All preview data remains outside the source
deliverable in `work`.

- Previous placement/profile loaded correctly after upgrade.
- Today's Study accepted time/focus and displayed a persisted plan with durations and
  human-readable reasons. The learner's broad placement weaknesses fed review selection.
- Browser inspection caught excess kana review for strong sampled kana; planner gating
  and regression coverage were added before final verification.
- Missing API key during a generated lesson preserved the active plan and offered retry
  or skip. Skipping advanced to a fixed vocabulary activity that worked without a key.
- Submitted a choice, received correct feedback, refreshed and recovered the same plan
  with completed/skipped state retained.
- Restarted the real server and resumed the next reading activity from that same plan;
  no browser console errors were reported in the final check.
- Created a beginner learner directly from the study screen in the isolated fixture.
- Generated a five-minute grammar plan, opened a structured mock lesson through the
  existing tutor renderer, submitted a Japanese answer and completed the session.
- Recap showed practiced content and successful performance without claiming mastery.
- Visually inspected the recap layout; inputs, feedback and controls remained readable.

No live LLM teaching/grading quality claim is made. Static checks cannot prove Japanese
quality or difficulty calibration, and mock generation only verifies application wiring.
The catalog has one scored item per activity and approximate time budgets. Source archives
exclude test databases, provider fixtures, caches, environments and secrets.
