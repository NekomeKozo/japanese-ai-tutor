import hashlib
import json
from pathlib import Path
from uuid import NAMESPACE_URL, UUID, uuid5

from app.errors import TutorError
from app.learner.initialization import now_iso

CATALOG = json.loads(Path(__file__).with_name('catalog.json').read_text(encoding='utf-8'))
EXERCISES = {e['id']: {**e, 'kind': kind} for kind, items in CATALOG.items() for e in items}
SOURCES = ('listening', 'speaking_read', 'speaking_answer', 'speaking_repeat', 'voice_conversation')


def event_key(key, kind):
    return str(uuid5(NAMESPACE_URL, f'audio:{kind}:{key}'))


def write_event(db, key, learner, kind, source, metadata, *, score=None, session=None):
    """Use existing append-only activity infrastructure, outside mastery processing."""
    encoded = json.dumps(metadata, sort_keys=True, separators=(',', ':'))
    fingerprint = hashlib.sha256(encoded.encode()).hexdigest()
    old = db.execute('SELECT learner_id,fingerprint,event_type,source FROM learning_events WHERE event_id=?', (key,)).fetchone()
    if old:
        if old != (str(learner), fingerprint, kind, source):
            raise TutorError('audio_conflict', 'This activity identifier was already used. Reload your practice.', 409)
        return False
    db.execute('INSERT INTO learning_events VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
        (key, str(learner), kind, None, None, score, None, source,
         str(session) if session else None, fingerprint, encoded, now_iso()))
    return True


def require_receipt(db, learner, transcription, target=None):
    row = db.execute("SELECT 1 FROM learning_events WHERE event_id=? AND learner_id=? AND event_type='speech_transcribed'",
                     (event_key(transcription, 'receipt'), str(learner))).fetchone()
    if not row:
        raise TutorError('audio_transcription_required', 'Transcribe your recording successfully before confirming.', 422)
    if target is not None:
        used = db.execute('SELECT metadata_json FROM learning_events WHERE event_id=?', (event_key(transcription, 'used'),)).fetchone()
        if used and json.loads(used[0]).get('target') != str(target):
            raise TutorError('audio_conflict', 'This transcription already completed another activity.', 409)


def consume_receipt(db, learner, transcription, target):
    require_receipt(db, learner, transcription)
    write_event(db, event_key(transcription, 'used'), learner, 'speech_used', 'speech_receipt', {'target': str(target)})


class AudioProgressService:
    def __init__(self, repository):
        self.repository = repository

    def owned(self, db, learner):
        if not db.execute('SELECT 1 FROM learner_state WHERE learner_id=?', (str(learner),)).fetchone():
            raise TutorError('learner_not_found', 'Learner not found.', 404)

    def receipt(self, learner, transcription):
        self.repository.require_ready()
        with self.repository.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            self.owned(db, learner)
            write_event(db, event_key(transcription, 'receipt'), learner, 'speech_transcribed', 'speech_receipt', {})

    def start(self, learner, body):
        exercise = EXERCISES.get(body.exercise_id)
        if not exercise:
            raise TutorError('audio_exercise', 'Choose an available audio exercise.', 422)
        metadata = {key: exercise[key] for key in ('id', 'level', 'kind')}
        metadata['mode'] = exercise.get('mode', 'listening')
        source = 'listening' if exercise['kind'] == 'listening' else 'speaking_' + exercise['mode']
        self.repository.require_ready()
        with self.repository.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            self.owned(db, learner)
            write_event(db, str(body.attempt_id), learner, 'audio_attempted', source, metadata)
        return {'attempt_id': str(body.attempt_id), **metadata}

    def complete(self, learner, attempt, body):
        self.repository.require_ready()
        with self.repository.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            self.owned(db, learner)
            row = db.execute("SELECT source,metadata_json FROM learning_events WHERE event_id=? AND learner_id=? AND event_type='audio_attempted'",
                             (str(attempt), str(learner))).fetchone()
            if not row:
                raise TutorError('audio_attempt', 'This practice attempt was not found for this learner.', 404)
            source, encoded = row
            metadata = json.loads(encoded)
            exercise = EXERCISES[metadata['id']]
            key = event_key(attempt, 'completed')
            old = db.execute('SELECT metadata_json,score FROM learning_events WHERE event_id=?', (key,)).fetchone()
            if metadata['kind'] == 'listening':
                if body.choice is None or body.choice >= len(exercise['choices']) or body.transcription_id is not None:
                    raise TutorError('audio_answer', 'Choose one available listening answer.', 422)
                metadata.update(choice=body.choice, assisted=body.assisted)
                correct = body.choice == exercise['answer']
                kind, score = ('listening_assisted' if body.assisted else 'listening_unassisted'), int(correct)
                result = {'correct': correct, 'answer': exercise['answer'], 'feedback': exercise['feedback'], 'assisted': body.assisted}
            else:
                if body.transcription_id is None or body.choice is not None:
                    raise TutorError('audio_answer', 'Confirm a successfully transcribed speaking answer.', 422)
                metadata.update(transcription_id=str(body.transcription_id), assisted=body.assisted)
                kind, score, result = 'speaking_completed', None, {'completed': True}
            if old:
                if json.loads(old[0]) != metadata:
                    raise TutorError('audio_conflict', 'This exercise was already confirmed with another answer.', 409)
                return result
            if metadata['kind'] == 'speaking':
                consume_receipt(db, learner, body.transcription_id, 'speaking:'+str(attempt))
            write_event(db, key, learner, kind, source, metadata, score=score)
            now = now_iso()
            db.execute('UPDATE learner_state SET last_activity_at=?,updated_at=? WHERE learner_id=?', (now, now, str(learner)))
            return result

    def progress(self, learner):
        self.repository.require_ready()
        placeholders = ','.join('?' for _ in SOURCES)
        with self.repository.connection() as db:
            self.owned(db, learner)
            groups = db.execute(f'SELECT source,event_type,COUNT(*),SUM(score) FROM learning_events WHERE learner_id=? AND source IN ({placeholders}) GROUP BY source,event_type',
                                (str(learner), *SOURCES)).fetchall()
            rows = db.execute(f"SELECT event_type,source,metadata_json,created_at,score FROM learning_events WHERE learner_id=? AND source IN ({placeholders}) AND event_type<>'audio_attempted' ORDER BY created_at DESC,event_id DESC LIMIT 20",
                              (str(learner), *SOURCES)).fetchall()
        counts = {(source, kind): (count, int(total or 0)) for source, kind, count, total in groups}
        listening = {}
        for mode in ('unassisted', 'assisted'):
            total, correct = counts.get(('listening', 'listening_' + mode), (0, 0))
            listening[mode] = {'completed': total, 'correct': correct, 'accuracy': round(correct / total * 100) if total else None}
        listening['attempts'] = counts.get(('listening', 'audio_attempted'), (0, 0))[0]
        speaking = {mode: {'attempts': counts.get(('speaking_' + mode, 'audio_attempted'), (0, 0))[0],
                          'completed': counts.get(('speaking_' + mode, 'speaking_completed'), (0, 0))[0]}
                    for mode in ('read', 'answer', 'repeat')}
        voice = {'completed_conversations': counts.get(('voice_conversation', 'voice_conversation_completed'), (0, 0))[0],
                 'confirmed_turns': counts.get(('voice_conversation', 'voice_turn_completed'), (0, 0))[0]}
        return {'listening': listening, 'speaking': speaking, 'voice': voice,
                'recent': [{'type': kind, 'source': source,
                            **{key: value for key, value in json.loads(metadata).items() if key in ('id', 'level', 'mode', 'assisted', 'scenario')},
                            'created_at': date, 'score': score} for kind, source, metadata, date, score in rows]}
