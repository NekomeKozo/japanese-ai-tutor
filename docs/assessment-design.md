# Placement assessment design

## Boundaries

The application controls state, scoring, selection, stopping and profile creation. An
LLM can judge the meaning of an individual free response, but never supplies the final
level. This makes placement reproducible with mocked evidence and prevents a narrative
model judgment from bypassing skill coverage or confidence requirements.

Each item measures one primary skill. Particle, verb-conjugation and adjective-conjugation
items also contribute to the grammar aggregate. Separate estimates preserve uneven
abilities. Written sentence production is a separate skill; the JLPT-reference summary
averages vocabulary, grammar, kanji and reading, without double-counting grammar subskills.
Listening and speaking remain null. The official [JLPT test composition](https://www.jlpt.jp/sp/e/guideline/testsections.html)
is the scope reference, not a source of our item calibrations or an endorsement of this test.

## Questions and evaluation

The 68 original prototype items cover ten skills and ten question types. Internal question
keys (`q001`, etc.) do not encode levels. Difficulty runs from 0 to 14, with early/main/high
JLPT-reference bands; script difficulty is 0–2. These are author-assigned **provisional
labels**, not official JLPT item classifications. The small bank contains some overlapping
skills and short passages; expert review and learner calibration are required before
treating its results as reliable placement measurements.

Curated questions are validated at startup. `QuestionBank.validated_candidates` is an
import boundary for future generated items. Validation does not publish an item or prove
its linguistic quality. This release deliberately uses the curated bank only; a human
should review correctness, alternatives and difficulty before adding generated items.

Choice and fixed-answer evaluation is deterministic. NFKC normalization handles width,
case and terminal punctuation. Choice answers must be one of the presented choices.
Known acceptable semantic answers can also be accepted locally. Other semantic answers
use one call to the existing `LLMProvider.generate` interface with only the current prompt,
expected meaning, criteria and answer. Output is schema-validated, including scores in
[0, 1]. Meaning, grammar, naturalness and acceptable alternatives are separate fields.

An unavailable evaluator creates `score=null, weight=0`. The question is consumed without
penalizing ability, and the selector looks for further evidence. We do not retry paid calls
automatically. If all production items become unavailable, production remains unassessed
and the test can reach its length cap with lower confidence. Known romaji alternatives
receive half evidence weight and an explicit note; they do not establish kana production.
“I don’t know” scores zero with weight 0.65 rather than being treated as missing evaluation.

## Transparent scoring model

For non-script skills, ability is a discrete grid from 0 to 14 in increments of 0.25.
The prior is proportional to `exp(-0.5 * ((ability - 3) / 5)^2)` and is the same for every
learner, regardless of self-report. An item at difficulty `d` predicts:

```text
guess = 1 / number_of_choices for choice items; 0.02 otherwise
p = guess + (0.97 - guess) / (1 + exp(-(ability - d) / 1.1))
log_likelihood += weight * (score * log(p) + (1 - score) * log(1 - p))
```

The posterior mean is the internal skill estimate. The 15th–85th percentile span is an
uncertainty interval, **not a validated frequentist confidence interval**. Success at a
harder item shifts the estimate higher than success at an easy item. Partial credit is
continuous. Chance-adjustment and a broad posterior reduce the impact of a lucky guess.
One scored observation retains an internal estimate but displays “Insufficient evidence.”

Script recognition is a weighted sample success rate, accompanied by item count and
confidence. A perfect two-item screen is labeled “Strong on sampled items,” never “mastered.”

Per-skill confidence combines:

- Effective evidence weight, saturating at four full-weight observations.
- Posterior interval width.
- Consistency: easy failures paired with harder successes lower confidence.
- Whether both successful and unsuccessful performance bound ability.
- Reduced evidence for skips and romaji, and the proportion of unavailable evaluations.

Unbounded performance is capped at 0.55 confidence. Overall confidence averages seven major
areas (the two scripts, vocabulary, grammar, kanji, reading and production), then discounts
unavailable evaluations. Missing areas contribute zero. Low is below 0.40, Moderate is
0.40–0.749, and High is at least 0.75. These thresholds are heuristics, not probabilities of
passing an exam. Upper-ceiling success is flagged separately; ability above the bank remains
unresolved. A summary score is computed only from core skills with at least two observations.

## Adaptive selection and stopping

1. Begin with two easy hiragana and two easy katakana items. If all four are wrong or
   unknown, stop with a foundations recommendation and explicitly unassessed other skills.
2. Sample each remaining skill once. Self-report only adjusts initial non-script selection
   slightly (0 for complete beginner, 3 for reported N4, otherwise 2).
3. Repeated success can raise the starting difficulty of an untested skill. This screening
   evidence changes question selection only; it never grants another skill an ability score.
4. Favor major skills with fewer observations and lower confidence. Never repeat an item ID.
5. For a skill, a score at least 0.85 raises target difficulty by 2 (by 3 after two successes);
   below 0.60 lowers it by 2; partial success holds it. Once success and failure bound the
   skill, select near its posterior mean. The nearest unused item is used, so the small
   bank may sometimes force a larger jump or a further diagnostic item away from the target.
6. Shuffle choices reproducibly per assessment and question to avoid answer-position bias.

Ordinary stopping requires at least 16 answers, two available observations in each major
area, a boundary/floor/ceiling in each non-script major skill, overall confidence at least
0.48, and changes below one difficulty unit relative to three questions earlier. Stop at
30 questions regardless of confidence. If no suitable unused item remains, complete with
`bank_exhausted` and the available evidence. The beginner screen is an explicit early-stop
exception to major-skill coverage; it does not fabricate those missing skill scores.

Strong/weak topics come from question metadata with at least two observations. A sample
average at least 0.80 suggests strength; at most 0.45 suggests review. Topic labels are
descriptive and are not mastery records. Recommendations are generated in code and use
skills with at least two observations; one lucky item cannot drive a recommended study area.

## Storage, ownership and integration

Placement uses the shared repository/storage adapter: local SQLite or the existing
private PostgreSQL database. `assessment_questions` stores versioned bank definitions;
`assessments` stores the versioned active state; `assessment_answers` retains question,
answer and evaluation evidence; `learner_profiles` preserves the completed snapshot.
Unknown schema versions and staging initialization failures must fail closed.

An assessment snapshot contains its current private question, answer history and final
profile when complete. Skill estimates are recomputed from saved evidence while active.
Bump the bank/state version for incompatible released-bank changes; do not silently
resume an active assessment with mixed versions.

One transaction updates state, inserts the answer and initializes the completed learner
profile. Optimistic versions, process-local busy coordination and unique assessment/
question/submission keys prevent stale or repeated scoring. Reusing a submission ID
with different content is a conflict. Completion and learner-memory initialization
share the existing transaction and must not double-count placement evidence.

Active assessments expire after the configured idle period; completed results remain
persistent. Browser resume IDs are hints, never bearer authorization. The server checks
staging/account ownership for assessment and learner access. See [security](security.md).

Saved tutor sessions load a compact trusted profile summary; browser-provided scores
are not accepted. Placement is not required for an unassessed learner's ordinary chat.
Continuous practice, mastery and curriculum are separate consumers of validated evidence:
[memory](learning-memory.md), [mastery](mastery-design.md), [curriculum](curriculum-design.md).
