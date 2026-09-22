import time
from collections import defaultdict

from app.assessment.schemas import AssessmentState, LearnerProfile, SCRIPTS
from app.assessment.scoring import all_estimates, beginner_screen, level_name, overall_confidence


def build_profile(state: AssessmentState, reason: str) -> LearnerProfile:
    skills = all_estimates(state.evidence)
    core = [skills[s] for s in ('vocabulary', 'grammar', 'kanji', 'reading') if skills[s].evidence_count >= 2]
    score = round(sum(s.difficulty_estimate for s in core) / len(core), 2) if core else None
    confidence = overall_confidence(skills, state.evidence)
    beginner = beginner_screen(state.evidence)
    label = 'Absolute Beginner' if beginner else level_name(score) if score is not None else 'Insufficient evidence'
    # Range is intentionally broad; this is a model interval, not a calibrated JLPT probability.
    if core:
        low = sum(s.interval[0] for s in core) / len(core)
        high = sum(s.interval[1] for s in core) / len(core)
        study_range = f'{level_name(low)} – {level_name(high)}'
    else:
        study_range = 'Foundations; other skills not assessed' if beginner else 'Not enough evidence'
    topics = defaultdict(list)
    for item in state.evidence:
        if item.evaluation.score is not None:
            topics[item.question.topic].append(item)
    strong, weak = [], []
    for topic, entries in sorted(topics.items()):
        if len(entries) < 2:
            continue
        average = sum(e.evaluation.score for e in entries) / len(entries)
        if average >= .8:
            strong.append(topic)
        if average <= .45:
            weak.append(topic)
    if beginner:
        recommendation = 'Start with hiragana and katakana recognition, then introductory vocabulary and simple sentences. Other skills still need assessment.'
    elif score is None:
        recommendation = 'Use beginner tutoring for now and repeat placement when more evidence is available.'
    else:
        ordered = sorted(((s, v) for s, v in skills.items() if s not in SCRIPTS and v.evidence_count >= 2),
                         key=lambda item: item[1].difficulty_estimate)
        weakest, low_skill = ordered[0]
        strongest, high_skill = ordered[-1]
        recommendation = f'Begin around {level_name(score)} material with a short review of foundations.'
        if high_skill.difficulty_estimate - low_skill.difficulty_estimate >= 2:
            recommendation = (f'Try {high_skill.estimated_level} {strongest.replace("_", " ")} while strengthening '
                              f'{weakest.replace("_", " ")} around {low_skill.estimated_level}.')
        if weak:
            recommendation += ' Prioritize ' + ', '.join(weak[:3]) + '.'
        script_gaps = [s for s in SCRIPTS if skills[s].recognition_score is not None and skills[s].recognition_score < .5]
        if script_gaps:
            recommendation = 'Review ' + ' and '.join(script_gaps) + ' recognition first. ' + recommendation
    limitations = ['Learning estimate only; not an official JLPT result.',
                  'Item difficulties and confidence are provisional and have not been calibrated on learners.',
                  'Listening and speaking are not assessed. Written production is reported separately from the JLPT-reference summary.']
    if any(s.evidence_count < 2 for s in skills.values()):
        limitations.append('Some skills have limited or no evidence; their estimates remain tentative.')
    if any(s.unavailable_count for s in skills.values()):
        limitations.append('Some free responses could not be evaluated; they did not count as incorrect.')
    if any(s.ceiling_reached for s in skills.values()):
        limitations.append('The bank ceiling was reached in at least one skill; ability above that range is unresolved.')
    if any(e.evaluation.romaji_used for e in state.evidence):
        limitations.append('Romaji answers received reduced evidence weight; kana production remains uncertain.')
    return LearnerProfile(learner_id=state.learner_id, assessment_id=state.assessment_id, created_at=time.time(),
        overall_estimate=label, overall_score=0 if beginner else score, probable_study_range=study_range,
        confidence=confidence, confidence_label='High' if confidence >= .75 else 'Moderate' if confidence >= .4 else 'Low',
        skills=skills, strong_topics=strong, weak_topics=weak, recommended_starting_point=recommendation,
        stopping_reason=reason, questions_answered=len(state.evidence), limitations=limitations)
