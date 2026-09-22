"""Additive v4 migration; original events, topic states and study plans are preserved."""
DDL = [
    '''CREATE TABLE IF NOT EXISTS mastery_evidence (
        event_id TEXT NOT NULL REFERENCES learning_events(event_id),
        learner_id TEXT NOT NULL REFERENCES learner_state(learner_id),
        topic_id TEXT NOT NULL REFERENCES learning_topics(topic_key), dimension TEXT NOT NULL,
        recorded_at TEXT NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(event_id,topic_id,dimension))''',
    '''CREATE INDEX IF NOT EXISTS ix_mastery_evidence_topic ON mastery_evidence(learner_id,topic_id,recorded_at,event_id)''',
    '''CREATE TABLE IF NOT EXISTS topic_mastery (
        learner_id TEXT NOT NULL REFERENCES learner_state(learner_id),
        topic_id TEXT NOT NULL REFERENCES learning_topics(topic_key), state_json TEXT NOT NULL,
        PRIMARY KEY(learner_id,topic_id))''',
    '''CREATE TABLE IF NOT EXISTS mastery_history (
        learner_id TEXT NOT NULL REFERENCES learner_state(learner_id),
        topic_id TEXT NOT NULL REFERENCES learning_topics(topic_key), event_id TEXT NOT NULL,
        recorded_at TEXT NOT NULL, snapshot_json TEXT NOT NULL, PRIMARY KEY(learner_id,topic_id,event_id))''',
]


def migrate(db):
    if db.execute('PRAGMA user_version').fetchone()[0] in (4,5):
        return
    from app.learner.catalog import TOPICS
    from app.mastery.service import process_stored_event, recompute_topic
    for statement in DDL:
        db.execute(statement)
    for t in TOPICS.values():
        db.execute('INSERT OR IGNORE INTO learning_topics VALUES (?,?,?,?,?,?,?)',
            (t.key,t.label,t.skill,t.kind,t.difficulty,t.reading,t.meaning))
    affected = set()
    # Old source metadata is deliberately not invented or rewritten.
    for (event_id,) in db.execute('SELECT event_id FROM learning_events ORDER BY created_at,event_id').fetchall():
        affected.update(process_stored_event(db, event_id, recalculate=False))
    for learner, topic in sorted(affected):
        recompute_topic(db, learner, topic)
    db.execute('PRAGMA user_version=4')
