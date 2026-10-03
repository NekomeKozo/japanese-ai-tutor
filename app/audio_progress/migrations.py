"""Schema 8 adds only an index over existing activity records."""
def migrate(db):
    version = db.execute('PRAGMA user_version').fetchone()[0]
    if version == 8:
        return
    if version != 7:
        raise ValueError('Unsupported audio progress database version')
    db.execute('CREATE INDEX IF NOT EXISTS ix_audio_events ON learning_events(learner_id,source,event_type,created_at DESC)')
    db.execute('PRAGMA user_version=8')
