import json
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from app.assessment.scoring import level_name
from app.errors import TutorError
from app.learner.catalog import TOPICS
from app.learner.events import process_event
from app.learner.initialization import initialize_default, now_iso
from app.learner.schemas import LearningEvent, Preferences, PreferencesPatch


class LearnerService:
    def __init__(self, repository):
        self.repository = repository

    def create(self):
        self.repository.require_ready()
        learner_id = uuid4()
        with self.repository.connection() as db:
            initialize_default(db, str(learner_id))
        return self.profile(learner_id)

    def profile(self, learner_id: UUID):
        self.repository.require_ready()
        key = str(learner_id)
        with self.repository.connection() as db:
            row = db.execute('SELECT profile_source,placement_id,estimated_level,overall_score,placement_confidence,preferences_json,created_at,updated_at,last_activity_at FROM learner_state WHERE learner_id=?', (key,)).fetchone()
            if not row:
                raise TutorError('learner_not_found', 'Learner not found. Create a profile or complete placement.', 404)
            source, placement_id, level, score, confidence, preferences, created, updated, active = row
            baseline_row = db.execute('SELECT profile_json FROM learner_profiles WHERE learner_id=?', (key,)).fetchone()
            baseline = json.loads(baseline_row[0]) if baseline_row else None
            skills = {}
            for skill, initial, estimate, certainty, count, learning_count, recent_json, recorded in db.execute(
                'SELECT skill,baseline,estimate,confidence,placement_evidence,learning_count,recent_json,updated_at FROM skill_state WHERE learner_id=? ORDER BY skill', (key,)):
                recent = json.loads(recent_json)
                label = level_name(estimate) if estimate is not None and count >= 2 else 'Not assessed'
                if baseline and skill in ('hiragana', 'katakana'):
                    label = baseline['skills'][skill]['estimated_level']
                skills[skill] = {'estimate': estimate, 'placement_baseline': initial, 'estimated_level': label,
                    'confidence': certainty, 'placement_evidence': count, 'learning_count': learning_count,
                    'recent_average': round(sum(recent) / len(recent), 3) if recent else None,
                    'recent_correct': sum(s >= .8 for s in recent), 'recent_incorrect': sum(s < .6 for s in recent),
                    'recent_count': len(recent), 'updated_at': recorded}
            # Indexed learner-scoped state only; never load lifetime event/transcript history.
            rows = db.execute('SELECT topic_key,encounters,correct_count,incorrect_count,recent_json,status,first_seen_at,last_seen_at,last_correct_at FROM learner_topics WHERE learner_id=? ORDER BY last_seen_at DESC,topic_key LIMIT 200', (key,)).fetchall()
            topics = []
            for topic_key, encounters, correct, incorrect, recent_json, status, first, last, last_correct in rows:
                topic = TOPICS[topic_key]
                recent = json.loads(recent_json)
                topics.append({'topic_key': topic_key, 'display_name': topic.label, 'topic_type': topic.kind,
                    'skill': topic.skill, 'reading': topic.reading, 'meaning': topic.meaning,
                    'encounters': encounters, 'correct_count': correct, 'incorrect_count': incorrect,
                    'recent_score': round(sum(recent) / len(recent), 3) if recent else None,
                    'status': status, 'first_seen_at': first, 'last_seen_at': last, 'last_correct_at': last_correct})
            cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
            mistakes = [{'mistake_key': key, 'display_name': TOPICS[key].label, 'occurrences': n,
                         'recent_occurrences': sum(date >= cutoff for date in json.loads(recent)), 'last_seen_at': last,
                         'status': 'inactive' if last < cutoff and status != 'improving' else status}
                for key, n, recent, last, status in db.execute('SELECT mistake_key,occurrences,recent_json,last_seen_at,status FROM mistake_state WHERE learner_id=? ORDER BY last_seen_at DESC LIMIT 20', (key,))]
        return {'learner_id': key, 'profile_source': source, 'estimated_level': level, 'overall_score': score,
            'placement_confidence': confidence, 'initial_placement': baseline, 'skills': skills,
            'preferences': json.loads(preferences), 'strong_topics': [t for t in topics if t['status'] == 'strong'],
            'weak_topics': [t for t in topics if t['status'] == 'needs_review'], 'recent_topics': topics[:10],
            'topic_memory': topics, 'common_mistakes': mistakes,
            'created_at': created, 'updated_at': updated, 'last_activity_at': active}

    def preferences(self, learner_id, patch: PreferencesPatch):
        self.repository.require_ready()
        with self.repository.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT preferences_json FROM learner_state WHERE learner_id=?', (str(learner_id),)).fetchone()
            if not row:
                raise TutorError('learner_not_found', 'Learner not found.', 404)
            prefs = Preferences.model_validate({**json.loads(row[0]), **patch.model_dump(exclude_unset=True)})
            db.execute('UPDATE learner_state SET preferences_json=?,updated_at=? WHERE learner_id=?',
                (prefs.model_dump_json(), now_iso(), str(learner_id)))
        return prefs

    def record(self, event: LearningEvent):
        self.repository.require_ready()
        with self.repository.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            return process_event(db, event)

    def activity(self, learner_id, limit=20, offset=0):
        self.repository.require_ready()
        with self.repository.connection() as db:
            if not db.execute('SELECT 1 FROM learner_state WHERE learner_id=?', (str(learner_id),)).fetchone():
                raise TutorError('learner_not_found', 'Learner not found.', 404)
            rows = db.execute("SELECT event_type,topic_key,source,created_at FROM learning_events WHERE learner_id=? AND source<>'speech_receipt' ORDER BY created_at DESC,event_id DESC LIMIT ? OFFSET ?",
                (str(learner_id), limit, offset)).fetchall()
        return [{'event_type': kind, 'topic': TOPICS[topic].label if topic in TOPICS else None,
                 'source': source, 'created_at': created} for kind, topic, source, created in rows]
