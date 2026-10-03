"""Additive learner schema 7. Full question snapshots preserve past attempts."""
DDL = [
    '''CREATE TABLE IF NOT EXISTS jlpt_sessions (
        session_id TEXT PRIMARY KEY, learner_id TEXT NOT NULL REFERENCES learner_state(learner_id),
        request_id TEXT NOT NULL UNIQUE, request_json TEXT NOT NULL, bank_version TEXT NOT NULL,
        status TEXT NOT NULL CHECK(status IN ('in_progress','completed','abandoned')),
        started_at TEXT NOT NULL, deadline_at TEXT, completed_at TEXT, version INTEGER NOT NULL DEFAULT 0)''',
    "CREATE UNIQUE INDEX IF NOT EXISTS ix_jlpt_active ON jlpt_sessions(learner_id) WHERE status='in_progress'",
    'CREATE INDEX IF NOT EXISTS ix_jlpt_history ON jlpt_sessions(learner_id,started_at)',
    '''CREATE TABLE IF NOT EXISTS jlpt_session_questions (
        session_id TEXT NOT NULL REFERENCES jlpt_sessions(session_id), question_id TEXT NOT NULL,
        order_index INTEGER NOT NULL, question_json TEXT NOT NULL,
        PRIMARY KEY(session_id,question_id), UNIQUE(session_id,order_index))''',
    '''CREATE TABLE IF NOT EXISTS jlpt_attempts (
        session_id TEXT NOT NULL, question_id TEXT NOT NULL, submission_id TEXT NOT NULL UNIQUE,
        answer TEXT NOT NULL, correct INTEGER NOT NULL CHECK(correct IN (0,1)), created_at TEXT NOT NULL,
        PRIMARY KEY(session_id,question_id),
        FOREIGN KEY(session_id,question_id) REFERENCES jlpt_session_questions(session_id,question_id))''',
]


def migrate(db):
    version = db.execute('PRAGMA user_version').fetchone()[0]
    if version not in (6, 7, 8):
        raise ValueError('Unsupported JLPT database version')
    # Older databases seeded their catalog before the Phase 9 identities existed.
    # Run on v7 too so an already-deployed upgrade repairs itself without deleting
    # sessions, changing existing topic metadata, or replaying learner evidence.
    from app.learner.catalog import TOPICS
    from app.jlpt.topics import VOCAB, KANJI
    for key in [item[0] for item in VOCAB + KANJI]:
        topic = TOPICS[key]
        db.execute('INSERT OR IGNORE INTO learning_topics VALUES (?,?,?,?,?,?,?)',
                   (topic.key, topic.label, topic.skill, topic.kind,
                    topic.difficulty, topic.reading, topic.meaning))
    if version in (7, 8):
        return
    for sql in DDL:
        db.execute(sql)
    db.execute('PRAGMA user_version=7')
