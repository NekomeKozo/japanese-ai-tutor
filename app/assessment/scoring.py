import math

from app.assessment.schemas import Evidence, GRAMMAR_PARTS, MAJORS, SCRIPTS, SKILLS, SkillEstimate

LEVELS = ['Absolute Beginner', 'Early N5', 'N5', 'High N5', 'Early N4', 'N4', 'High N4',
          'Early N3', 'N3', 'High N3', 'Early N2', 'N2', 'High N2', 'Early N1', 'N1']
GRID = [i / 4 for i in range(57)]


def level_name(value: float) -> str:
    return LEVELS[max(0, min(14, int(value + 0.5)))]


def evidence_for(skill: str, evidence: list[Evidence]) -> list[Evidence]:
    return [e for e in evidence if e.question.skill == skill or (skill == 'grammar' and e.question.skill in GRAMMAR_PARTS)]


def estimate(skill: str, evidence: list[Evidence]) -> SkillEstimate:
    observations = evidence_for(skill, evidence)
    available = [e for e in observations if e.evaluation.score is not None]
    unavailable = len(observations) - len(available)
    if not available:
        return SkillEstimate(difficulty_estimate=None, estimated_level='Not assessed', evidence_count=0,
                             unavailable_count=unavailable, confidence=0)
    weight = sum(e.evaluation.weight for e in available)
    skipped = sum(e.dont_know for e in available) / len(available)
    if skill in SCRIPTS:
        score = sum(e.evaluation.score * e.evaluation.weight for e in available) / weight
        confidence = min(0.85, weight / 4) * (1 - 0.3 * skipped)
        label = 'Strong on sampled items' if score >= .8 else 'Developing' if score >= .4 else 'Needs foundations'
        return SkillEstimate(difficulty_estimate=None, recognition_score=round(score, 3), estimated_level=label,
            evidence_count=len(available), unavailable_count=unavailable, confidence=round(confidence, 3))
    # Discrete Bayesian ability grid, with a broad fixed prior independent of self-report.
    log_weights = [-0.5 * ((theta - 3) / 5) ** 2 for theta in GRID]
    for item in available:
        guess = 1 / len(item.question.choices) if item.question.evaluation == 'choice' else 0.02
        for i, theta in enumerate(GRID):
            p = guess + (0.97 - guess) / (1 + math.exp(-(theta - item.question.difficulty) / 1.1))
            score = item.evaluation.score
            log_weights[i] += item.evaluation.weight * (score * math.log(p) + (1 - score) * math.log(1 - p))
    weights = [math.exp(w - max(log_weights)) for w in log_weights]
    total = sum(weights)
    weights = [w / total for w in weights]
    mean = sum(theta * w for theta, w in zip(GRID, weights))
    cumulative, low, high = 0., None, None
    for theta, w in zip(GRID, weights):
        cumulative += w
        if low is None and cumulative >= .15:
            low = theta
        if high is None and cumulative >= .85:
            high = theta
    # Penalize inversions: an easier error paired with a harder success.
    pairs = [(a, b) for a in available for b in available if a.question.difficulty + 1 < b.question.difficulty]
    inversions = sum(a.evaluation.score < .4 and b.evaluation.score > .8 for a, b in pairs)
    consistency = 1 - .6 * inversions / max(1, len(pairs))
    bounded = any(e.evaluation.score >= .65 for e in available) and any(e.evaluation.score < .65 for e in available)
    confidence = min(1, weight / 4) * max(.1, 1 - (high - low) / 14) * consistency * (1 - .3 * skipped)
    if not bounded:
        confidence = min(confidence, .55)
    confidence *= len(available) / max(1, len(observations))
    ceiling = any(e.question.difficulty >= 14 and e.evaluation.score >= .8 for e in available)
    return SkillEstimate(difficulty_estimate=round(mean, 2),
        estimated_level=level_name(mean) if len(available) >= 2 else 'Insufficient evidence',
        evidence_count=len(available), unavailable_count=unavailable, confidence=round(confidence, 3),
        interval=[low, high], ceiling_reached=ceiling)


def all_estimates(evidence: list[Evidence]) -> dict[str, SkillEstimate]:
    return {skill: estimate(skill, evidence) for skill in SKILLS}


def overall_confidence(skills: dict[str, SkillEstimate], evidence: list[Evidence]) -> float:
    # Includes the production skill for coverage, but not in the JLPT-reference score.
    confidence = sum(skills[s].confidence for s in MAJORS) / len(MAJORS)
    available = sum(e.evaluation.score is not None for e in evidence)
    return round(confidence * available / max(1, len(evidence)), 3)


def beginner_screen(evidence: list[Evidence]) -> bool:
    scripts = [e for e in evidence if e.question.skill in SCRIPTS and e.evaluation.score is not None]
    return all(sum(e.question.skill == skill for e in scripts) >= 2 for skill in SCRIPTS) and all(e.evaluation.score == 0 for e in scripts)
