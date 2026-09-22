import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone

from app.errors import TutorError
from app.learner.catalog import TOPICS, normalize_topic
from app.learner.initialization import now_iso
from app.learner.schemas import LearningEvent

logger = logging.getLogger(__name__)
WINDOW = 8


def topic_status(scores):
    if not scores:
        return 'new'
    mean = sum(scores) / len(scores)
    if len(scores) >= 3 and mean < .6:
        return 'needs_review'
    if len(scores) >= 4 and mean >= .8 and all(s >= .6 for s in scores[-3:]):
        return 'strong'
    if len(scores) >= 3 and mean >= .7:
        return 'familiar'
    return 'learning'


def update_skill_state(db, learner_id, skill, score, difficulty, now):
    row = db.execute('SELECT baseline,estimate,learning_count,recent_json FROM skill_state WHERE learner_id=? AND skill=?',
                     (learner_id, skill)).fetchone()
    if not row:
        return
    baseline, estimate, count, recent_json = row
    count += 1
    recent = (json.loads(recent_json) + [score])[-WINDOW:]
    if count % 5 == 0 and baseline is not None:
        average = sum(recent) / len(recent)
        # Chat evidence is noisy. No automatic overall-level promotion; bounded skill drift.
        delta = .15 if average >= .8 and difficulty >= estimate - 1 else -.15 if average < .4 and difficulty <= estimate + 1 else 0
        new_value = round(max(0, min(14, max(baseline - 1, min(baseline + 1, estimate + delta)))), 2)
        if new_value != estimate:
            db.execute('INSERT INTO skill_history VALUES (?,?,?,?,?,?)',
                (learner_id, skill, count, new_value, now, 'conservative_learning_update'))
        estimate = new_value
    db.execute('UPDATE skill_state SET estimate=?,learning_count=?,recent_json=?,updated_at=? WHERE learner_id=? AND skill=?',
               (estimate, count, json.dumps(recent), now, learner_id, skill))


def process_event(db, event: LearningEvent, *, session_id=None, update_skill=True, metadata_extra=None):
    learner_id = str(event.learner_id)
    if not db.execute('SELECT 1 FROM learner_state WHERE learner_id=?', (learner_id,)).fetchone():
        raise TutorError('learner_not_found', 'Learner not found. Create a profile or complete placement.', 404)
    fingerprint = hashlib.sha256(event.model_dump_json().encode()).hexdigest()
    existing = db.execute('SELECT learner_id,fingerprint FROM learning_events WHERE event_id=?', (str(event.event_id),)).fetchone()
    if existing:
        if existing != (learner_id, fingerprint):
            raise TutorError('event_conflict', 'That event ID was already used for different evidence.', 409)
        return False
    topic_key, known = normalize_topic(event.topic_key, event.skill)
    topic = TOPICS[topic_key]
    if not known:
        logger.info('Unknown learning tag mapped to a bounded generic category')
    # Unknown taxonomy is exposure only; arbitrary model labels cannot become scored evidence.
    score = event.score if known else None
    errors = []
    if score is not None and score < .6:
        for tag in event.error_tags:
            key, recognized = normalize_topic(tag, topic.skill)
            if recognized and TOPICS[key].skill == topic.skill and key not in errors:
                errors.append(key)
        if not errors:
            errors = [topic_key]
    now = now_iso()
    metadata = json.dumps({**(metadata_extra or {}), 'error_tags': errors, 'unknown_topic': not known}, ensure_ascii=False)
    db.execute('INSERT INTO learning_events VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
        (str(event.event_id), learner_id, event.event_type, topic_key, topic.skill, score,
         event.difficulty if event.source in ('placement_assessment','curriculum') else topic.difficulty,
         event.source, str(session_id) if session_id else None, fingerprint, metadata, now))
    row = db.execute('SELECT encounters,correct_count,incorrect_count,recent_json,first_seen_at,last_correct_at FROM learner_topics WHERE learner_id=? AND topic_key=?',
                     (learner_id, topic_key)).fetchone()
    encounters, correct, incorrect, recent_json, first, last_correct = row or (0, 0, 0, '[]', now, None)
    recent = json.loads(recent_json)
    if score is not None:
        recent = (recent + [score])[-WINDOW:]
        correct += int(score >= .8)
        incorrect += int(score < .6)
        if score >= .8:
            last_correct = now
    status = topic_status(recent)
    if score is None and status == 'new' and encounters >= 1:
        status = 'learning'
    db.execute('INSERT INTO learner_topics VALUES (?,?,?,?,?,?,?,?,?,?) ON CONFLICT(learner_id,topic_key) DO UPDATE SET '
        'encounters=excluded.encounters,correct_count=excluded.correct_count,incorrect_count=excluded.incorrect_count,'
        'recent_json=excluded.recent_json,status=excluded.status,last_seen_at=excluded.last_seen_at,last_correct_at=excluded.last_correct_at',
        (learner_id, topic_key, encounters + 1, correct, incorrect, json.dumps(recent), status, first, now, last_correct))
    cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    for key in errors:
        old = db.execute('SELECT occurrences,recent_json FROM mistake_state WHERE learner_id=? AND mistake_key=?', (learner_id, key)).fetchone()
        occurrences, dates = (old[0], json.loads(old[1])) if old else (0, [])
        dates = ([date for date in dates if date >= cutoff] + [now])[-50:]
        db.execute('INSERT INTO mistake_state VALUES (?,?,?,?,?,?) ON CONFLICT(learner_id,mistake_key) DO UPDATE SET '
            'occurrences=excluded.occurrences,recent_json=excluded.recent_json,last_seen_at=excluded.last_seen_at,status=excluded.status',
            (learner_id, key, occurrences + 1, json.dumps(dates), now, 'active' if len(dates) >= 3 else 'observed'))
    if status in ('familiar', 'strong'):
        db.execute("UPDATE mistake_state SET status='improving' WHERE learner_id=? AND mistake_key=?", (learner_id, topic_key))
    if update_skill and score is not None:
        update_skill_state(db, learner_id, topic.skill, score,
            event.difficulty if event.source=='curriculum' and event.difficulty is not None else topic.difficulty, now)
    db.execute('UPDATE learner_state SET updated_at=?,last_activity_at=? WHERE learner_id=?', (now, now, learner_id))
    from app.mastery.service import process_stored_event
    process_stored_event(db, event.event_id)
    from app.review.service import process_event as schedule_event
    schedule_event(db, event.event_id)
    logger.info('Learning event processed (%s)', event.event_type)
    return True
