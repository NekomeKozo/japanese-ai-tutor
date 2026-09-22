# Phase 2 completion report

Phase 2 extends the existing prototype in place. Phase 1 remains usable without placement.

## Added files

- `PHASE2_REPORT.md`
- `app/api/assessment.py`
- `app/assessment/__init__.py`
- `app/assessment/data/questions.json`
- `app/assessment/engine.py`
- `app/assessment/evaluator.py`
- `app/assessment/questions.py`
- `app/assessment/repository.py`
- `app/assessment/results.py`
- `app/assessment/schemas.py`
- `app/assessment/scoring.py`
- `app/assessment/selector.py`
- `docs/assessment-design.md`
- `frontend/assessment.js`
- `tests/test_assessment.py`
- `tests/test_assessment_core.py`

## Modified files

- `.env.example`
- `.gitignore`
- `README.md`
- `VERIFICATION.md`
- `app/config.py`
- `app/main.py`
- `app/tutor/schemas.py`
- `app/tutor/service.py`
- `frontend/app.js`
- `frontend/index.html`
- `frontend/styles.css`
- `tests/conftest.py`

## Database changes

SQLite schema version 1 adds `assessment_questions`, `assessments`, `assessment_answers`
and `learner_profiles`. State, response evidence and final profiles commit atomically.
Final skill estimates persist in the profile; active estimates are reconstructed from
persisted evidence. No Phase 1 data was removed. No new external dependencies were added.

## Assessment behavior

There are 68 curated prototype items. The application owns scoring, coverage, selection,
stopping and recommendations. A per-skill Bayesian grid uses difficulty, fractional score,
chance-adjustment and evidence weight; scripts use weighted recognition rates. Difficulty
rises with repeated success, drops after errors and narrows around an observed boundary.
Topic strengths and weaknesses require repeated metadata-backed evidence.

Confidence combines evidence count, uncertainty, consistency, coverage, boundary evidence,
skips and unavailable evaluations. A four-item screen can stop a complete beginner; other
assessments require coverage and stability or stop at 30. Estimates are provisional study
ranges, not certification. Listening and speaking are null, and written production remains
separate from the JLPT-reference summary.

**Skills:** hiragana, katakana, vocabulary, grammar, particles, verb conjugation, adjective
conjugation, kanji, reading and sentence construction.

**Question types:** multiple choice, vocabulary meaning, Japanese-to-English,
English-to-Japanese, sentence completion, grammar selection, kanji reading, kanji meaning,
reading comprehension and sentence construction. Choice/fixed answers are local; other
semantic answers use the existing provider with validated output and partial credit.
Provider failure creates unavailable evidence, never an incorrect learner score.

## Phase 1 integration

The original tutor and LLM adapter were retained. Chat accepts an optional `learner_id`;
the server loads its saved placement summary and adds it to tutor context. The UI adds
Placement/Tutor navigation, questions, resume, results and Begin learning. Ordinary chat
remains available when placement is absent, storage fails or the bank is invalid.

## Tests and results

Added 46 Phase 2 test cases across two files; **102 total tests pass**, including all 56
original cases. Coverage includes adaptive learner simulations, partial credit, confidence,
no repeats, all skill coverage, length limits, persistence/restart, safe duplicates,
concurrency, atomic rollback, hidden-answer integrity, evaluator failures and tutor handoff.
Browser checks passed for choice/typed answers, skips, resume, completion, results,
profile handoff and missing-provider fallback. See `VERIFICATION.md` for details.

## Limitations and Phase 3

The initial bank, difficulty labels and confidence thresholds need independent Japanese
review and real learner calibration. Upper-end estimates are conservative with a small
bank. Some subskills have insufficient evidence. Live LLM grading has not been verified
because no API key is configured. Generated-item validation is an extension boundary;
automatic question generation is not enabled. This remains a local, unauthenticated
prototype with no cross-device profile recovery or continuous profile updating.

Phase 3 should introduce versioned learning activity and persistent learning memory,
evidence provenance, and careful updates to the initial profile. Preserve placement
snapshots. No Phase 3 curriculum, memory or scheduling features were implemented.

Run and configuration instructions are in `README.md`; formulas and architectural
decisions are in `docs/assessment-design.md`.
