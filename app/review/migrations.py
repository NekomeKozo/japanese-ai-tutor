import logging
from app.review.clock import Clock

DDL = [
    '''CREATE TABLE IF NOT EXISTS review_schedules (
       schedule_id TEXT PRIMARY KEY, learner_id TEXT NOT NULL REFERENCES learner_state(learner_id),
       topic_id TEXT NOT NULL REFERENCES learning_topics(topic_key), dimension TEXT NOT NULL,
       due_at TEXT NOT NULL, suspended INTEGER NOT NULL DEFAULT 0, version INTEGER NOT NULL,
       state_json TEXT NOT NULL, UNIQUE(learner_id,topic_id,dimension))''',
    '''CREATE INDEX IF NOT EXISTS ix_reviews_due ON review_schedules(learner_id,suspended,due_at)''',
    '''CREATE TABLE IF NOT EXISTS review_attempts (
       schedule_id TEXT NOT NULL REFERENCES review_schedules(schedule_id),
       event_id TEXT NOT NULL REFERENCES learning_events(event_id), learner_id TEXT NOT NULL,
       reviewed_at TEXT NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(schedule_id,event_id))''',
    '''CREATE INDEX IF NOT EXISTS ix_review_attempts_learner ON review_attempts(learner_id,reviewed_at)''',
]

def migrate(db, now=None):
    if db.execute('PRAGMA user_version').fetchone()[0] in (5,6):
        return
    for sql in DDL:
        db.execute(sql)
    from app.review.service import bootstrap
    bootstrap(db,now or Clock().now())
    db.execute('PRAGMA user_version=5')
    logging.getLogger(__name__).info('Review schedule migration completed')
