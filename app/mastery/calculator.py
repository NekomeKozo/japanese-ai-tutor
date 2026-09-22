"""Mastery Algorithm v1: conservative replay of weighted historical/recent evidence."""
import math
from collections import Counter
from app.mastery.policy import DIMENSIONS, POLICY, VERSION


def weight(item, repetition, policy=POLICY):
    challenge = 0 if item.learner_level is None else max(-policy.difficulty_limit,
        min(policy.difficulty_limit, (item.difficulty - item.learner_level) * .05))
    # Easy failures still matter; difficult failures have a smaller effect.
    modifier = 1 + challenge * (2 * item.score - 1)
    hint = policy.hint_penalty if item.hint_used and item.score > .5 else 1
    if item.hint_used is None:
        hint *= policy.unknown_hint_factor
    return (policy.type_weights[item.evidence_type] * policy.source_weights.get(item.source, .4)
            * modifier * hint * item.quality / (1 + repetition) ** 2)


def status(score, confidence, independent, *, decline=False, policy=POLICY):
    if score is None:
        return 'new'
    if decline:
        return 'needs_review'
    if independent >= policy.strong_minimum and confidence >= policy.strong_confidence and score >= policy.strong_score:
        return 'strong'
    if independent >= policy.familiar_minimum and confidence >= policy.familiar_confidence and score >= policy.familiar_score:
        return 'familiar'
    return 'developing' if independent >= policy.developing_minimum and score >= policy.developing_score else 'learning'


def measure(items, policy=POLICY):
    if not items:
        return dict(score=None, confidence=0., evidence_count=0, independent_count=0, recent_score=None,
                    historical_score=None, stability=0., status='new')
    seen = Counter()
    weighted = []
    score = policy.prior_mean
    successes = mass = 0.
    for item in items:
        token = (item.context_id, item.evidence_type)
        w = weight(item, seen[token], policy)
        seen[token] += 1
        weighted.append((item.score, w))
        successes += item.score * w
        mass += w
        def posterior(values):
            return (policy.prior_mean * policy.prior_strength + sum(s * v for s, v in values)) / (
                policy.prior_strength + sum(v for _, v in values))
        historical = (policy.prior_mean * policy.prior_strength + successes) / (policy.prior_strength + mass)
        recent = posterior(weighted[-policy.recent_window:])
        target = (1 - policy.recent_weight) * historical + policy.recent_weight * recent
        score += max(-policy.maximum_step, min(policy.maximum_step, target - score))
    mass = sum(w for _, w in weighted)
    mean = sum(s * w for s, w in weighted) / mass if mass else .5
    variance = sum(w * (s - mean) ** 2 for s, w in weighted) / mass if mass else 0
    consistency = max(policy.minimum_consistency, 1 - 2 * variance)
    diversity = min(1., policy.diversity_base + policy.diversity_increment * (len({e.evidence_type for e in items}) - 1)
                    + policy.diversity_increment * min(2, len({e.activity_type for e in items}) - 1))
    distribution = min(1., policy.time_distribution_base + policy.diversity_increment * (len({e.timestamp.date() for e in items}) - 1))
    confidence = (1 - math.exp(-mass / policy.confidence_scale)) * consistency * diversity * distribution
    independent = len(seen)
    confidence *= min(1, independent / policy.confidence_independent_minimum)
    if all(e.evidence_type == 'recognition' for e in items):
        confidence = min(confidence, policy.recognition_confidence_cap)
    if all(e.source == 'placement_assessment' for e in items):
        confidence = min(confidence, policy.placement_confidence_cap)
    recent_values = weighted[-policy.recent_window:]
    recent_mass = sum(w for _, w in recent_values)
    recent_score = sum(s * w for s, w in recent_values) / recent_mass if recent_mass else None
    decline = (len(items) >= policy.strong_minimum and historical >= policy.decline_history and
               recent_score is not None and recent_score < policy.decline_recent and
               sum(e.score < policy.decline_recent for e in items[-policy.decline_window:]) >= policy.decline_failures)
    return dict(score=round(score, 4), confidence=round(confidence, 4), evidence_count=len(items),
        independent_count=independent, recent_score=round(recent_score, 4) if recent_score is not None else None,
        historical_score=round(historical, 4), stability=round(consistency * confidence, 4),
        status=status(score, confidence, independent, decline=decline, policy=policy))


def calculate(topic_id, kind, evidence, policy=POLICY):
    items = sorted(evidence, key=lambda e: (e.timestamp, e.event_id, e.dimension))
    dimensions = {d: measure([e for e in items if e.dimension == d], policy) for d in DIMENSIONS[kind]}
    overall = measure(list({e.event_id: e for e in items}.values()), policy)
    known = {d: value for d, value in dimensions.items() if value['score'] is not None}
    if known:
        # Unmeasured slots use the neutral prior ONLY for conservative aggregation;
        # their displayed scores stay null. This also prevents a newly measured
        # dimension from causing a large discontinuity by changing the denominator.
        slots = {d: v['score'] if v['score'] is not None else policy.prior_mean for d, v in dimensions.items()}
        score = (1-policy.weakest_dimension_share) * sum(DIMENSIONS[kind][d] * value for d, value in slots.items()) + policy.weakest_dimension_share * min(slots.values())
        overall['score'] = round(score, 4)
        coverage = len(known) / len(dimensions)
        overall['confidence'] = round(overall['confidence'] * (.5 + .5 * coverage), 4)
        strong_coverage = (all(d in known for d in ('recognition', 'meaning', 'on_reading', 'kun_reading'))
                           if kind == 'kanji' else len(known) == len(dimensions))
        label = status(score, overall['confidence'], overall['independent_count'],
            decline=any(v['status'] == 'needs_review' for v in known.values()), policy=policy)
        if label == 'strong' and (not strong_coverage or min(v['score'] for v in known.values()) < policy.familiar_score):
            label = 'familiar'
        overall['status'] = label
    overall.update(topic_id=topic_id, topic_type=kind, dimensions=dimensions, algorithm_version=VERSION,
        first_seen_at=items[0].timestamp.isoformat() if items else None,
        last_seen_at=items[-1].timestamp.isoformat() if items else None,
        last_updated_at=items[-1].timestamp.isoformat() if items else None,
        reason='No scored evidence' if not items else 'Weighted historical and recent evidence; unknown dimensions remain unassessed',
        reading_contexts=sorted({e.reading_context for e in items if e.reading_context}))
    return overall
