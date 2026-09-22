import json
import logging
from datetime import datetime, timezone
from uuid import NAMESPACE_URL, uuid5

from app.assessment.schemas import LearnerProfile, SKILLS
from app.learner.schemas import Preferences

logger = logging.getLogger(__name__)


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec='microseconds')


def initialize_default(db, learner_id: str, profile=None):
    now = now_iso()
    changed = db.execute('INSERT OR IGNORE INTO learner_state VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
        (learner_id, 'placement_assessment' if profile else 'default', str(profile.assessment_id) if profile else None,
         profile.overall_estimate if profile else 'Beginner', profile.overall_score if profile else None,
         profile.confidence if profile else 0, Preferences().model_dump_json(), now, now, None)).rowcount
    if not changed:
        return False
    for skill in SKILLS:
        value = profile.skills.get(skill) if profile else None
        baseline = value.difficulty_estimate if value else None
        db.execute('INSERT INTO skill_state (learner_id,skill,baseline,estimate,confidence,placement_evidence,updated_at) VALUES (?,?,?,?,?,?,?)',
            (learner_id, skill, baseline, baseline, value.confidence if value else 0,
             value.evidence_count if value else 0, now))
    logger.info('Learner profile created (%s)', 'placement' if profile else 'default')
    return True


def initialize_placement(db, profile_json: str, state_json: str):
    from app.learner.events import process_event
    from app.learner.catalog import normalize_topic
    from app.learner.schemas import LearningEvent
    profile = LearnerProfile.model_validate_json(profile_json)
    learner_id = str(profile.learner_id)
    if not initialize_default(db, learner_id, profile):
        return
    # Seed topic evidence without reapplying assessment scores to skill estimates.
    state = json.loads(state_json)
    for item in state.get('evidence', []):
        if item['evaluation']['score'] is None:
            continue
        question = item['question']
        topic, known = normalize_topic(question['topic'], question['skill'])
        if not known:
            continue
        event = LearningEvent(event_id=uuid5(NAMESPACE_URL, f'placement:{profile.assessment_id}:{question["id"]}'),
            learner_id=profile.learner_id, event_type='performance', topic_key=topic, skill=question['skill'],
            score=item['evaluation']['score'], difficulty=question['difficulty'], source='placement_assessment')
        from app.mastery.context import task_context
        mastery = task_context(topic, question['skill'], question['prompt'], question['question_type'],
            question['evaluation'], level=question['difficulty'])
        process_event(db, event, update_skill=False, metadata_extra={'mastery': mastery})
    event_id = str(uuid5(NAMESPACE_URL, f'placement-completed:{profile.assessment_id}'))
    db.execute('INSERT INTO learning_events VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
        (event_id, learner_id, 'assessment_completed', None, None, None, None, 'placement_assessment', None,
         event_id, '{}', now_iso()))
    logger.info('Persistent profile initialized from placement')
