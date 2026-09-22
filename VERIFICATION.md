# Phase 2 verification

Verified locally on Windows with Python 3.12.14. Installed dependencies are unchanged
from Phase 1 and recorded in `requirements-lock.txt`.

- `python -m pytest -q`: **102 passed**, including all 56 Phase 1 cases and 46 Phase 2 cases.
- Two upstream TestClient/AnyIO deprecation warnings remain; no test failures.
- Python compilation and syntax checks for both frontend JavaScript files passed.
- Uvicorn started the updated application successfully on `127.0.0.1:8000`.
- Browser verified the placement introduction, shuffled radio choices, submitting a
  choice, progress, typed kanji answers, I-don't-know flow, early beginner completion,
  result table, recommendations and Begin learning handoff to the existing tutor.
- Browser verified active-assessment recovery after refresh and completed-result
  recovery after a real server restart.
- Browser verified free-response failure without a configured provider: the assessment
  advanced and explicitly said the answer did not count as incorrect.
- Inspected the rendered placement layout at the browser's narrow viewport.
- Test/preview records live outside the deliverable in the workspace `work` directory.
  The source archive excludes databases, secrets, environments and caches.

## Deterministic learner simulations

These use synthetic correctness at author-assigned item boundaries. They test algorithm
behavior, not real-world validity of the Japanese placement result.

| Synthetic evidence | Length | Summary | Confidence |
| --- | ---: | --- | --- |
| Miss every script item | 4 | Absolute Beginner; other skills unassessed | Low |
| Correct through difficulty 3, wrong above | 20 | High N5 | Moderate |
| Correct through difficulty 6, wrong above | 24 | High N4 | Moderate |
| Correct through difficulty 9, wrong above | 26 | High N3 | Moderate |
| Correct at every sampled level | 30 | High N2; ceiling limitations reported | Moderate |
| Strong vocabulary/writing, weak kanji | 25 | N4 summary, distinct skill estimates | Moderate |

The conservative upper-end summary and wide study range reflect the limited bank and
prior, not proof that an advanced learner is below N1. Expert item review and empirical
calibration remain necessary.

## Failure and integrity checks

Tests cover invalid/oversized input, private-answer redaction, malformed/out-of-range
LLM output, semantic partial credit, alternate answers, romaji weighting, unavailable
and timed-out evaluators, duplicate and stale submissions, simultaneous requests,
optimistic concurrency, SQLite failures, rollback of the whole answer/profile transaction,
expiry, unknown sessions, question exhaustion, invalid bank startup, self-report separation,
profile persistence and placement context in the tutor. Generated candidates are validated
without being admitted automatically to the live bank.

**Not verified:** a real model response, provider account access, live semantic-grading
quality, or empirical placement accuracy. No API key is configured and no paid API calls
were made. Use the README setup to supply your own key, then review semantic evaluations
and tutoring quality before relying on the estimates.

Phase 3 has not been implemented.
