# Mastery Algorithm v1

This is a deterministic, provisional estimate of demonstrated knowledge, separate from
confidence in that estimate. It is neither raw accuracy nor a calibrated probability of
future recall. It consumes structured Phase 3 events; it never calls a model. The existing
placement estimate and Phase 3 rolling practice signals keep their original semantics.

## Evidence and identity

Only scored performance events on the bounded application catalog qualify. Exposure,
unknown tags, malformed metadata, nonfinite scores and invalid dimensions do not. Partial
credit remains in [0,1]. Server-owned metadata identifies the dimension, evidence type,
activity, prompt-context hash, hint/reveal state, learner level and reading context.
No arbitrary model-created topics are admitted. Prompt text is not copied into mastery
evidence. Original events retain their existing fingerprint and duplicate handling.

Fixed curriculum group questions are mapped to the actual tested word or character via
`mastery/catalog.py`. Other broad groups do not become individual-item evidence. Words
such as 学校 are separate vocabulary topics; knowing them never automatically establishes
学 or 校 mastery. The legacy 学 reading/meaning topics share the individual 学 identity.
On/kun reading evidence requires its tested word context (for example 学生). Contexts are
retained and displayed; one reading context never claims all pronunciations are known.

A multiple-choice meaning or reading answer supplies that dimension plus recognition.
These are two dimension rows from one event, not two independent encounters. Overall
counts/confidence deduplicate by event ID. Production evidence never fills recognition,
meaning or reading automatically. Untested dimensions have null scores and zero confidence.

## Exact weighting

Sort by timestamp, event ID and dimension. For each dimension, replay its observations in
this order. Let `s` be partial-credit score; `r` the number of earlier observations with
the same `(context_id, evidence_type)` in that dimension; `q` be evidence quality.

```
c = clamp(0.05 * (difficulty - learner_level), -0.2, 0.2)
    [c = 0 if learner level is unknown]
d = 1 + c * (2*s - 1)
w = type_weight * source_weight * d * hint_factor * q / (1+r)^2
```

Thus difficulty changes weight by at most 20%; difficult successes count somewhat more,
difficult failures somewhat less, and easy failures remain meaningful. Repeating the
same prompt has diminishing weight, even with a new event ID. A distinct context/type
pair counts as one independent encounter; this is a proxy, not proven independence.

| Evidence type | Weight |
|---|---:|
| Recognition / multiple choice | 0.55 |
| Recall | 0.80 |
| Comprehension | 0.75 |
| Application | 0.90 |
| Production | 1.00 |

| Source | Weight |
|---|---:|
| Placement assessment | 0.40 |
| Tutor chat | 0.55 |
| Quiz | 0.80 |
| Exercise | 0.85 |
| Curriculum | 1.00 |
| Manual review | 0.80 |

Unknown source fallback is 0.40 (normal event schemas constrain sources). Quality defaults
to 1. Explicit correction-mode tutor evidence uses quality 0.7. Missing dimension metadata
becomes recognition only with quality multiplied by 0.35. Missing context becomes one
shared `unknown:source` context, preventing invented independence.

Known hint use multiplies positive evidence (`s > .5`) by .5; unknown hint use multiplies
weight by .85; otherwise factor 1. Current flows generally cannot prove that no hint or
answer was seen, so they record unknown rather than asserting unaided recall. Positive
evidence explicitly marked answer-revealed is discarded. This metadata supports future
better instrumentation without adding a scheduler.

## Dimension score

The prior mean is .5 with strength 2 (equivalent to one success and one failure).
For every prefix of the chronological evidence:

```
H = (1 + sum(w*s over all observations)) / (2 + sum(w over all observations))
R = (1 + sum(w*s over latest 6)) / (2 + sum(w over latest 6))
target = 0.7*H + 0.3*R
score_next = score_previous + clamp(target - score_previous, -0.08, 0.08)
score_initial = 0.5
```

No evidence returns null instead of the prior. The .08 bound is per new observation in
a dimension; maintenance/backfill may introduce several observations at once. Recent
means use observation order, not wall-clock decay. Time away alone does not lower mastery.
Stored scores/confidences are rounded to four decimals; internal replay uses full precision.

## Confidence and stability

Let W be total effective weight, V the weighted variance of raw scores, E the number of
distinct evidence types, A the number of activity types, D the number of recorded dates,
and I the number of independent context/type pairs:

```
consistency = max(0.4, 1 - 2*V)
diversity = min(1, 0.6 + 0.1*(E-1) + 0.1*min(2,A-1))
distribution = min(1, 0.7 + 0.1*(D-1))
confidence = (1-exp(-W/12)) * consistency * diversity * distribution * min(1,I/5)
```

Recognition-only confidence is capped at .45; placement-only confidence at .35.
Dimension stability is consistency times confidence. Overall stability records the
same evidence-level quantity before the coverage multiplier below. It is a heuristic
signal for future calibration, not a forgetting-model stability parameter. UI confidence
labels are limited evidence (<.35), moderate confidence (<.65), high confidence otherwise.

## Overall score and dimensions

| Kind | Dimension weights |
|---|---|
| Vocabulary | recognition .15, meaning .25, reading .20, production .40 |
| Grammar | recognition .15, understanding .20, application .25, production .40 |
| Kanji | recognition .15, meaning .25, on-reading .25, kun-reading .25, production .10 |

```
slot[d] = dimension score when measured, otherwise neutral prior 0.5
overall_score = .8 * sum(dimension_weight[d]*slot[d]) + .2 * min(slot[d])
overall_confidence = deduplicated_event_confidence * (.5 + .5*measured_dimension_fraction)
```

An entirely unassessed topic still has null overall score. Neutral slots are an aggregation
prior only, not measured skills. Keeping a fixed denominator avoids a large jump when a
dimension receives its first observation. Weighting the weakest dimension means strong
recognition cannot conceal poor production. Kanji production may remain untested; the
current UI does not assess handwriting or stroke order.

## Status logic

Apply in this order to each dimension:

1. **New:** score is null.
2. **Needs review:** at least 8 observations, historical posterior H >= .68, unshrunk
   weighted latest-six mean < .5, and at least 3 of the latest 4 raw scores < .5.
3. **Strong:** I >= 8, score >= .85, confidence >= .65.
4. **Familiar:** I >= 5, score >= .68, confidence >= .35.
5. **Developing:** I >= 3 and score >= .45.
6. **Learning:** all other assessed cases.

Overall needs-review is triggered by any declining measured dimension. Other overall
statuses use overall score/confidence and deduplicated I. Overall strong additionally
requires every vocabulary/grammar dimension measured, or kanji recognition/meaning/on/kun
measured, and all measured dimension scores >= .68. Otherwise strong is reduced to familiar.
Eight encounters is a minimum gate, not a promise of strong mastery: confidence and
coverage normally require substantially more varied evidence. Recognition-only evidence
cannot become strong. A single failure cannot trigger needs-review. Subsequent varied
success can recover; old success does not disappear after one error.

## Persistence, migration and recomputation

SQLite schema v4 adds `mastery_evidence`, `topic_mastery`, and `mastery_history`, with
foreign keys to existing learner/topic/event identities. Dimensions live in state JSON,
avoiding a parallel learner catalog. Evidence identity is `(event_id,topic_id,dimension)`.
Original event, old practice signals, normalized evidence, new state and history are
committed together inside the caller's existing transaction. Duplicate retries add none.
Indexed updates recalculate only affected topics from their stored normalized evidence.
The replay is linear in that topic's observations, not the learner's lifetime history.

Meaningful history records first evidence, status changes, score change >= .05, or
confidence change >= .10 relative to the last recorded snapshot. Each state/history
snapshot includes algorithm_version=1. Recalculation rebuilds snapshots event by event
to reproduce normal execution, keeping paired dimensions in one event. This maintenance
history replay is quadratic per topic and intended for the current small local dataset.

Migration participates in the existing all-or-nothing initialization transaction. It
seeds additional canonical items and backfills eligible historical events, without editing
their payloads or assuming missing production/reading facts. Broad legacy groups may
produce no item evidence. Existing profiles, conversations, preferences, assessment
results and study plans are untouched. Older plans parse with focus_dimension=null.
The developer reset supports v4 and clears derived rows before their original event rows.

The local maintenance CLI in README replays normalized evidence. It does not invent new
metadata or regrade answers. If a future normalizer changes, explicitly migrate the
normalized evidence as well; merely changing the scoring version cannot recover missing
historical dimensions. Tunables are in `mastery/policy.py`.

## Integration boundaries

Placement metadata comes from the actual question type and context, with low source
weight and confidence cap. Tutor correction metadata marks production only for explicit
correction mode with a validated evaluation and a supported vocabulary/grammar topic.
General conversation claims retain weak recognition treatment. Existing LLM assessment
of free responses may be wrong; no LLM output directly chooses mastery or confidence.

Curriculum ranking reads compact persisted mastery state only. With at least 3 encounters,
add `2*confidence*(.7-score)` and, for decline, `2*confidence`. A supported weak dimension
(score < .65 and at least 2 observations) adds `2*dimension_confidence` and selects a
matching focus: vocabulary production/reading, grammar production/application, or the
existing 学 on-reading task. Missing mastery preserves existing ranking and selection.
Fixed vocabulary/kanji focused tasks use local content; grammar uses the existing lesson
provider and validates an open semantic exercise for production/application focus.
No additional mastery model call, provider change, or expanded context budget is required.

## Limitations to review before Phase 6

The catalog has 57 supported topics at release. It is not a comprehensive course or a
teacher-reviewed/calibrated assessment. Repeated fixed prompts saturate deliberately;
more varied authored items are needed to measure dimensions broadly. Context hashes
only approximate independence. Reading confidence pools tested contexts within on/kun
dimensions; it does not claim coverage of every reading. Age does not decay confidence
or mastery. There are no review dates, intervals, scheduling, FSRS, SM-2, pronunciation,
listening, handwriting, or advanced conversation mastery in this phase. Review thresholds,
priors, uncertainty and dimensions with real learner data before designing Phase 6.
