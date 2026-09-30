"""Schema v3: additive study plans/activities in the existing transaction."""
DDL = [
    '''CREATE TABLE study_sessions (
        session_id TEXT PRIMARY KEY, learner_id TEXT NOT NULL REFERENCES learner_state(learner_id),
        status TEXT NOT NULL CHECK(status IN ('planned','in_progress','completed','abandoned')),
        request_json TEXT NOT NULL, plan_json TEXT NOT NULL, catalog_version TEXT NOT NULL,
        created_at TEXT NOT NULL, started_at TEXT, completed_at TEXT)''',
    '''CREATE UNIQUE INDEX ix_one_active_study ON study_sessions(learner_id)
        WHERE status IN ('planned','in_progress')''',
    '''CREATE INDEX ix_study_learner_time ON study_sessions(learner_id,created_at DESC)''',
    '''CREATE TABLE study_activities (
        activity_id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES study_sessions(session_id),
        order_index INTEGER NOT NULL, topic_id TEXT NOT NULL REFERENCES learning_topics(topic_key),
        skill TEXT NOT NULL, activity_type TEXT NOT NULL, difficulty REAL NOT NULL, duration_minutes INTEGER NOT NULL,
        status TEXT NOT NULL CHECK(status IN ('not_started','in_progress','completed','skipped')),
        content_json TEXT, result_json TEXT, submission_id TEXT UNIQUE, fingerprint TEXT, completed_at TEXT,
        UNIQUE(session_id,order_index))''',
]


def migrate(db):
    version=db.execute('PRAGMA user_version').fetchone()[0]
    if version in (3,4,5,6): return
    if version!=2: raise ValueError('Unsupported curriculum database version')
    from app.learner.catalog import TOPICS
    for topic in TOPICS.values():
        db.execute('INSERT OR IGNORE INTO learning_topics VALUES (?,?,?,?,?,?,?)',
            (topic.key,topic.label,topic.skill,topic.kind,topic.difficulty,topic.reading,topic.meaning))
    for statement in DDL: db.execute(statement)
    db.execute('PRAGMA user_version=3')
