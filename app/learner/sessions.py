import hashlib
import json
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from app.errors import TutorError
from app.learner.catalog import TOPICS, normalize_topic
from app.learner.events import process_event, update_skill_state
from app.learner.initialization import now_iso
from app.learner.schemas import LearningEvent
from app.llm.base import Message
from app.tutor.prompts import format_request
from app.tutor.schemas import TutorResponse

MAX_HISTORY_CHARS = 12000


def request_fingerprint(request):
    return hashlib.sha256(request.model_dump_json(exclude={'request_id'}).encode()).hexdigest()


class SessionService:
    def __init__(self, repository):
        self.repository = repository

    def _lifecycle(self, db, key, learner_id, kind):
        event_id = str(uuid5(NAMESPACE_URL, f'{kind}:{key}'))
        db.execute('INSERT OR IGNORE INTO learning_events VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
            (event_id, str(learner_id), kind, None, None, None, None, 'tutor_chat', str(key), event_id, '{}', now_iso()))

    def create(self, learner_id):
        self.repository.require_ready()
        key = uuid4()
        with self.repository.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            if not db.execute('SELECT 1 FROM learner_state WHERE learner_id=?', (str(learner_id),)).fetchone():
                raise TutorError('learner_not_found', 'Learner not found.', 404)
            now = now_iso()
            db.execute('INSERT INTO tutor_sessions VALUES (?,?,?,?,?,?)', (str(key), str(learner_id), now, None, 0, 0))
            self._lifecycle(db, key, learner_id, 'tutor_session_started')
            db.execute('UPDATE learner_state SET last_activity_at=?,updated_at=? WHERE learner_id=?', (now, now, str(learner_id)))
        return {'session_id': str(key), 'learner_id': str(learner_id)}

    def exists(self, session_id):
        self.repository.require_ready()
        with self.repository.connection() as db:
            return bool(db.execute('SELECT 1 FROM tutor_sessions WHERE session_id=?', (str(session_id),)).fetchone())

    def _owned(self, db, learner_id, session_id):
        row = db.execute('SELECT started_at,ended_at,interaction_count,version FROM tutor_sessions WHERE session_id=? AND learner_id=?',
            (str(session_id), str(learner_id))).fetchone()
        if not row:
            raise TutorError('saved_session_not_found', 'Saved session not found for this learner.', 404)
        return row

    def get(self, learner_id, session_id, limit=12):
        self.repository.require_ready()
        with self.repository.connection() as db:
            start, end, count, version = self._owned(db, learner_id, session_id)
            rows = db.execute('SELECT request_id,user_text,reply_json,created_at,mode FROM conversation_turns WHERE session_id=? ORDER BY turn_number DESC LIMIT ?',
                (str(session_id), limit)).fetchall()
        return {'session_id': str(session_id), 'learner_id': str(learner_id), 'started_at': start, 'ended_at': end,
            'interaction_count': count, 'version': version,
            'turns': [{'request_id': key, 'message': text, 'response': json.loads(reply), 'created_at': date, 'mode': mode}
                      for key, text, reply, date, mode in reversed(rows)]}

    def list(self, learner_id, limit=20):
        self.repository.require_ready()
        with self.repository.connection() as db:
            if not db.execute('SELECT 1 FROM learner_state WHERE learner_id=?', (str(learner_id),)).fetchone():
                raise TutorError('learner_not_found', 'Learner not found.', 404)
            return [{'session_id': key, 'started_at': start, 'ended_at': end, 'interaction_count': count}
                for key, start, end, count in db.execute('SELECT session_id,started_at,ended_at,interaction_count FROM tutor_sessions WHERE learner_id=? ORDER BY started_at DESC LIMIT ?',
                                                       (str(learner_id), limit))]

    def close(self, learner_id, session_id):
        self.repository.require_ready()
        with self.repository.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            self._owned(db, learner_id, session_id)
            db.execute('UPDATE tutor_sessions SET ended_at=COALESCE(ended_at,?),version=version+1 WHERE session_id=? AND ended_at IS NULL', (now_iso(), str(session_id)))
            self._lifecycle(db, session_id, learner_id, 'tutor_session_completed')

    def replay(self, request):
        self.repository.require_ready()
        with self.repository.connection() as db:
            self._owned(db, request.learner_id, request.session_id)
            row = db.execute('SELECT session_id,fingerprint,reply_json FROM conversation_turns WHERE request_id=?', (str(request.request_id),)).fetchone()
            if not row:
                return None
            if row[:2] != (str(request.session_id), request_fingerprint(request)):
                raise TutorError('turn_conflict', 'This request ID was used for a different message.', 409)
            return TutorResponse.model_validate_json(row[2])

    def history(self, saved, max_turns):
        messages, total = [], 0
        for turn in reversed(saved['turns'][-max_turns:]):
            reply = turn['response']
            # Rehydrate a concise teaching reply, not model observations or lifetime history.
            compact = {'message': reply['message'][:1200], 'explanation': (reply.get('explanation') or '')[:600],
                       'correction': reply.get('correction'), 'exercise': reply.get('exercise')}
            assistant = json.dumps(compact, ensure_ascii=False)
            if len(assistant) > 6000:
                compact['correction'] = None
                compact['message'] = compact['message'][:600]
                assistant = json.dumps(compact, ensure_ascii=False)
            if len(assistant) > 6000:
                # Keep the actual practice question, drop oversized choices/extras.
                compact['exercise'] = {'question': (reply.get('exercise') or {}).get('question', '')[:2000]}
                assistant = json.dumps(compact, ensure_ascii=False)
            user = format_request(turn['mode'], turn['message'])
            if total + len(user) + len(assistant) > MAX_HISTORY_CHARS:
                break
            messages[0:0] = [Message('user', user), Message('assistant', assistant)]
            total += len(user) + len(assistant)
        return messages

    def commit(self, request, reply, observations, expected_version):
        self.repository.require_ready()
        with self.repository.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT session_id,fingerprint,reply_json FROM conversation_turns WHERE request_id=?', (str(request.request_id),)).fetchone()
            if row:
                if row[:2] != (str(request.session_id), request_fingerprint(request)):
                    raise TutorError('turn_conflict', 'This request ID was used for a different message.', 409)
                return TutorResponse.model_validate_json(row[2])
            self._owned(db, request.learner_id, request.session_id)
            changed = db.execute('UPDATE tutor_sessions SET interaction_count=interaction_count+1,version=version+1 WHERE session_id=? AND learner_id=? AND version=? AND ended_at IS NULL',
                (str(request.session_id), str(request.learner_id), expected_version)).rowcount
            if not changed:
                raise TutorError('session_conflict', 'The saved session changed or ended. Reload it before continuing.', 409)
            count = db.execute('SELECT interaction_count FROM tutor_sessions WHERE session_id=?', (str(request.session_id),)).fetchone()[0]
            now = now_iso()
            db.execute('INSERT INTO conversation_turns VALUES (?,?,?,?,?,?,?,?)',
                (str(request.request_id), str(request.session_id), count, request_fingerprint(request), request.message,
                 request.mode, reply.model_dump_json(), now))
            by_skill = {}
            for observation in observations:
                key, known = normalize_topic(observation.topic_key, observation.skill)
                event = LearningEvent(event_id=uuid5(request.request_id, key), learner_id=request.learner_id,
                    event_type=observation.event_type, topic_key=observation.topic_key, skill=observation.skill,
                    score=observation.score, difficulty=observation.difficulty, error_tags=observation.error_tags,
                    source=request.mode if request.mode in ('quiz', 'exercise') else 'tutor_chat')
                # Only explicit correction of a submitted Japanese sentence supports
                # production. Other chat observations retain conservative legacy quality.
                metadata = {}
                if request.mode == 'correct' and reply.evaluation is not None:
                    from app.mastery.catalog import topic_type
                    if topic_type(key) in ('grammar', 'vocabulary'):
                        import hashlib
                        metadata = {'mastery': {'dimension': 'production', 'evidence_type': 'production',
                            'activity_type': 'sentence_correction',
                            'context_id': hashlib.sha256(request.message.strip().encode()).hexdigest(),
                            'hint_used': None, 'quality': .7}}
                process_event(db, event, session_id=request.session_id, update_skill=False, metadata_extra=metadata)
                if known and observation.score is not None:
                    by_skill.setdefault(TOPICS[key].skill, []).append((observation.score, TOPICS[key].difficulty))
            # Many tags in one reply still count as at most one skill observation per turn.
            for skill, scores in by_skill.items():
                update_skill_state(db, str(request.learner_id), skill,
                    sum(s for s, _ in scores) / len(scores), sum(d for _, d in scores) / len(scores), now)
            db.execute('UPDATE learner_state SET last_activity_at=?,updated_at=? WHERE learner_id=?', (now, now, str(request.learner_id)))
        return reply
