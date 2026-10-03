"""Additive v6; transcripts stay in conversation_turns."""

DDL = [
    '''CREATE TABLE IF NOT EXISTS conversation_states (
        session_id TEXT PRIMARY KEY REFERENCES tutor_sessions(session_id),
        learner_id TEXT NOT NULL REFERENCES learner_state(learner_id),
        scenario_key TEXT NOT NULL, status TEXT NOT NULL CHECK(status IN ('active','completed')),
        starting_level TEXT NOT NULL CHECK(starting_level IN ('beginner','N5','N4','N3','N2','N1')),
        correction_policy TEXT NOT NULL CHECK(correction_policy IN ('important_only','balanced','every_turn')),
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL, ended_at TEXT)''',
    "CREATE UNIQUE INDEX IF NOT EXISTS ix_one_active_conversation ON conversation_states(learner_id) WHERE status='active'",
    'CREATE INDEX IF NOT EXISTS ix_conversation_evidence ON learning_events(session_id,event_type,created_at)',
]


def migrate(db):
    version = db.execute('PRAGMA user_version').fetchone()[0]
    if version in (6, 7, 8):
        return
    if version != 5:
        raise ValueError('Unsupported conversation database version')
    for sql in DDL:
        db.execute(sql)
    db.execute('PRAGMA user_version=6')
