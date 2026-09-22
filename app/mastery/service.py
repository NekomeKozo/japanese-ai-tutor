import json
from app.errors import TutorError
from app.mastery.calculator import calculate
from app.mastery.catalog import canonical, topic_type
from app.mastery.normalizer import normalize
from app.mastery.policy import POLICY
from app.mastery.schemas import Evidence

EVENT_COLUMNS = 'event_id,learner_id,event_type,topic_key,skill,score,difficulty,source,metadata_json,created_at'


def event_row(values):
    return dict(zip(EVENT_COLUMNS.split(','), values))


def evidence_for(db, learner_id, topic_id):
    return [Evidence.model_validate_json(row[0]) for row in db.execute(
        'SELECT payload FROM mastery_evidence WHERE learner_id=? AND topic_id=? ORDER BY recorded_at,event_id,dimension',
        (learner_id, topic_id))]


def save_state(db, learner_id, topic_id, items):
    state = calculate(topic_id, topic_type(topic_id), items)
    db.execute('INSERT INTO topic_mastery VALUES (?,?,?) ON CONFLICT(learner_id,topic_id) DO UPDATE SET state_json=excluded.state_json',
        (learner_id, topic_id, json.dumps(state)))
    previous = db.execute('SELECT snapshot_json FROM mastery_history WHERE learner_id=? AND topic_id=? ORDER BY recorded_at DESC,event_id DESC LIMIT 1',
        (learner_id, topic_id)).fetchone()
    old = json.loads(previous[0]) if previous else None
    if not old or old['status'] != state['status'] or abs((old['score'] or 0) - (state['score'] or 0)) >= POLICY.history_score_change or abs(old['confidence'] - state['confidence']) >= POLICY.history_confidence_change:
        snapshot = {k: state[k] for k in ('score','confidence','status','evidence_count','algorithm_version')}
        db.execute('INSERT OR REPLACE INTO mastery_history VALUES (?,?,?,?,?)',
            (learner_id, topic_id, items[-1].event_id, items[-1].timestamp.isoformat(), json.dumps(snapshot)))
    return state


def process_stored_event(db, event_id, *, recalculate=True):
    # Earlier migrations seed Phase 3 events before schema v4 exists.
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='mastery_evidence'").fetchone():
        return set()
    values = db.execute(f'SELECT {EVENT_COLUMNS} FROM learning_events WHERE event_id=?', (str(event_id),)).fetchone()
    if not values:
        return set()
    row = event_row(values)
    try:
        metadata = json.loads(row['metadata_json'])
    except (ValueError, TypeError):
        metadata = {}
    if not isinstance(metadata, dict):
        metadata = {}
    changed = set()
    for item in normalize(row, metadata):
        inserted = db.execute('INSERT OR IGNORE INTO mastery_evidence VALUES (?,?,?,?,?,?)',
            (item.event_id, item.learner_id, item.topic_id, item.dimension, item.timestamp.isoformat(), item.model_dump_json())).rowcount
        if inserted:
            changed.add((item.learner_id, item.topic_id))
    for learner, topic in changed:
        if recalculate:
            save_state(db, learner, topic, evidence_for(db, learner, topic))
    return changed


def recompute_topic(db, learner_id, topic_id):
    items = evidence_for(db, learner_id, topic_id)
    db.execute('DELETE FROM mastery_history WHERE learner_id=? AND topic_id=?', (learner_id, topic_id))
    if not items:
        db.execute('DELETE FROM topic_mastery WHERE learner_id=? AND topic_id=?', (learner_id, topic_id))
        return
    for end in range(1, len(items) + 1):
        if end == len(items) or items[end].event_id != items[end - 1].event_id:
            save_state(db, learner_id, topic_id, items[:end])


class MasteryService:
    def __init__(self, repository):
        self.repository = repository

    def _owned(self, db, learner_id):
        if not db.execute('SELECT 1 FROM learner_state WHERE learner_id=?', (str(learner_id),)).fetchone():
            raise TutorError('learner_not_found', 'Learner not found.', 404)

    def get_topic_mastery(self, learner_id, topic_id):
        from app.learner.catalog import TOPICS
        topic_id = canonical(topic_id)
        self.repository.require_ready()
        with self.repository.connection() as db:
            self._owned(db, learner_id)
            kind = topic_type(topic_id)
            if not kind:
                raise TutorError('mastery_topic_not_found', 'This topic has no supported mastery record.', 404)
            row = db.execute('SELECT state_json FROM topic_mastery WHERE learner_id=? AND topic_id=?', (str(learner_id), topic_id)).fetchone()
            state = json.loads(row[0]) if row else calculate(topic_id, kind, [])
            topic = TOPICS[topic_id]
            state.update(display_name=topic.label, reading=topic.reading, meaning=topic.meaning)
            return state

    def list(self, learner_id, kind=None, status=None, limit=100, offset=0):
        from app.learner.catalog import TOPICS
        self.repository.require_ready()
        with self.repository.connection() as db:
            self._owned(db, learner_id)
            saved = {key: json.loads(data) for key, data in db.execute(
                'SELECT topic_id,state_json FROM topic_mastery WHERE learner_id=?', (str(learner_id),))}
        results = []
        for key, topic in TOPICS.items():
            category = topic_type(key)
            if not category or canonical(key) != key or (kind and category != kind):
                continue
            state = saved.get(key) or calculate(key, category, [])
            if status and state['status'] != status:
                continue
            state.update(display_name=topic.label, reading=topic.reading, meaning=topic.meaning)
            results.append(state)
        results.sort(key=lambda s: (s['evidence_count'] == 0, s['topic_type'], s['topic_id']))
        return {'items': results[offset:offset + limit], 'total': len(results), 'limit': limit, 'offset': offset}

    def curriculum_signals(self, learner_id):
        self.repository.require_ready()
        with self.repository.connection() as db:
            self._owned(db, learner_id)
            return {key: json.loads(data) for key, data in db.execute(
                'SELECT topic_id,state_json FROM topic_mastery WHERE learner_id=?', (str(learner_id),))}

    def get_mastery_dimensions(self, learner_id, topic_id):
        return self.get_topic_mastery(learner_id, topic_id)['dimensions']

    def get_topics_needing_review(self, learner_id):
        return self.list(learner_id, status='needs_review')['items']

    def get_low_confidence_topics(self, learner_id):
        return [s for s in self.list(learner_id)['items'] if s['confidence'] < POLICY.familiar_confidence]

    def get_topic_last_seen(self, learner_id, topic_id):
        return self.get_topic_mastery(learner_id, topic_id)['last_seen_at']

    def get_recent_mastery_changes(self, learner_id, topic_id=None, limit=20):
        self.repository.require_ready()
        with self.repository.connection() as db:
            self._owned(db, learner_id)
            rows = db.execute('SELECT topic_id,recorded_at,snapshot_json FROM mastery_history WHERE learner_id=? '
                'AND (? IS NULL OR topic_id=?) ORDER BY recorded_at DESC,event_id DESC LIMIT ?',
                (str(learner_id), topic_id, topic_id, limit))
            return [dict(topic_id=key, recorded_at=date, **json.loads(data)) for key, date, data in rows]

    def recalculate_mastery(self, learner_id):
        self.repository.require_ready()
        with self.repository.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            self._owned(db, learner_id)
            topics = [row[0] for row in db.execute('SELECT DISTINCT topic_id FROM mastery_evidence WHERE learner_id=?', (str(learner_id),))]
            for topic in topics:
                recompute_topic(db, str(learner_id), topic)
        return len(topics)
