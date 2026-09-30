"""Additive version 2 migration in the existing assessment database."""

DDL = [
    '''CREATE TABLE IF NOT EXISTS learner_state (
        learner_id TEXT PRIMARY KEY, profile_source TEXT NOT NULL, placement_id TEXT,
        estimated_level TEXT NOT NULL, overall_score REAL, placement_confidence REAL NOT NULL,
        preferences_json TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, last_activity_at TEXT)''',
    '''CREATE TABLE IF NOT EXISTS skill_state (
        learner_id TEXT NOT NULL REFERENCES learner_state(learner_id), skill TEXT NOT NULL,
        baseline REAL, estimate REAL, confidence REAL NOT NULL, placement_evidence INTEGER NOT NULL,
        learning_count INTEGER NOT NULL DEFAULT 0, recent_json TEXT NOT NULL DEFAULT '[]',
        updated_at TEXT NOT NULL, PRIMARY KEY(learner_id, skill))''',
    '''CREATE TABLE IF NOT EXISTS learning_topics (
        topic_key TEXT PRIMARY KEY, label TEXT NOT NULL, skill TEXT NOT NULL, kind TEXT NOT NULL,
        difficulty REAL NOT NULL, reading TEXT, meaning TEXT)''',
    '''CREATE TABLE IF NOT EXISTS learner_topics (
        learner_id TEXT NOT NULL REFERENCES learner_state(learner_id), topic_key TEXT NOT NULL REFERENCES learning_topics(topic_key),
        encounters INTEGER NOT NULL, correct_count INTEGER NOT NULL, incorrect_count INTEGER NOT NULL,
        recent_json TEXT NOT NULL, status TEXT NOT NULL, first_seen_at TEXT NOT NULL, last_seen_at TEXT NOT NULL,
        last_correct_at TEXT, PRIMARY KEY(learner_id, topic_key))''',
    '''CREATE TABLE IF NOT EXISTS mistake_state (
        learner_id TEXT NOT NULL REFERENCES learner_state(learner_id), mistake_key TEXT NOT NULL REFERENCES learning_topics(topic_key),
        occurrences INTEGER NOT NULL, recent_json TEXT NOT NULL, last_seen_at TEXT NOT NULL,
        status TEXT NOT NULL, PRIMARY KEY(learner_id, mistake_key))''',
    '''CREATE TABLE IF NOT EXISTS learning_events (
        event_id TEXT PRIMARY KEY, learner_id TEXT NOT NULL REFERENCES learner_state(learner_id),
        event_type TEXT NOT NULL, topic_key TEXT, skill TEXT, score REAL, difficulty REAL,
        source TEXT NOT NULL, session_id TEXT, fingerprint TEXT NOT NULL, metadata_json TEXT NOT NULL,
        created_at TEXT NOT NULL)''',
    '''CREATE INDEX IF NOT EXISTS ix_learning_events_learner_time ON learning_events(learner_id, created_at DESC)''',
    '''CREATE TABLE IF NOT EXISTS tutor_sessions (
        session_id TEXT PRIMARY KEY, learner_id TEXT NOT NULL REFERENCES learner_state(learner_id),
        started_at TEXT NOT NULL, ended_at TEXT, interaction_count INTEGER NOT NULL DEFAULT 0,
        version INTEGER NOT NULL DEFAULT 0)''',
    '''CREATE INDEX IF NOT EXISTS ix_tutor_sessions_learner_time ON tutor_sessions(learner_id, started_at DESC)''',
    '''CREATE TABLE IF NOT EXISTS conversation_turns (
        request_id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES tutor_sessions(session_id),
        turn_number INTEGER NOT NULL, fingerprint TEXT NOT NULL, user_text TEXT NOT NULL,
        mode TEXT NOT NULL, reply_json TEXT NOT NULL, created_at TEXT NOT NULL,
        UNIQUE(session_id, turn_number))''',
    '''CREATE TABLE IF NOT EXISTS skill_history (
        learner_id TEXT NOT NULL REFERENCES learner_state(learner_id), skill TEXT NOT NULL,
        learning_count INTEGER NOT NULL, estimate REAL, recorded_at TEXT NOT NULL,
        reason TEXT NOT NULL, PRIMARY KEY(learner_id, skill, learning_count))''',
]


def migrate(db):
    from app.learner.catalog import TOPICS
    from app.learner.initialization import initialize_placement
    version = db.execute('PRAGMA user_version').fetchone()[0]
    if version not in (1, 2, 3, 4, 5, 6):
        raise ValueError('Unsupported database version')
    if version == 1:
        for statement in DDL:
            db.execute(statement)
        for topic in TOPICS.values():
            db.execute('INSERT OR IGNORE INTO learning_topics VALUES (?, ?, ?, ?, ?, ?, ?)',
                (topic.key, topic.label, topic.skill, topic.kind, topic.difficulty, topic.reading, topic.meaning))
        for learner_id, profile_json, state_json in db.execute(
                'SELECT p.learner_id, p.profile_json, a.state_json FROM learner_profiles p JOIN assessments a ON a.id=p.assessment_id').fetchall():
            initialize_placement(db, profile_json, state_json)
        db.execute('PRAGMA user_version=2')
