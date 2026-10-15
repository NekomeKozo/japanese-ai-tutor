"""Explicit additive migration. Never called automatically by application startup."""

VERSION = 1
SQLITE_DDL = '''CREATE TABLE IF NOT EXISTS account_learner_links (
    account_id TEXT PRIMARY KEY NOT NULL,
    learner_id TEXT UNIQUE NOT NULL REFERENCES learner_state(learner_id) ON DELETE RESTRICT,
    created_at REAL NOT NULL,
    link_version INTEGER NOT NULL CHECK(link_version=1),
    proof_method TEXT NOT NULL CHECK(proof_method IN ('signed_legacy_owner_v1','checkpoint_legacy_owner_v1')),
    legacy_owner_digest TEXT NOT NULL,
    provider_session_digest TEXT NOT NULL,
    confirmation_digest TEXT NOT NULL UNIQUE)'''

POSTGRES_DDL = SQLITE_DDL.replace('account_id TEXT PRIMARY KEY NOT NULL',
    'account_id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE RESTRICT')


def present(db, postgres=False):
    if postgres:
        return bool(db.execute("SELECT to_regclass('tutor_private.account_learner_links') IS NOT NULL").fetchone()[0])
    return bool(db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='account_learner_links'").fetchone())


def migrate(repository):
    """Run only in isolated fixtures or after an explicit operator approval/backup."""
    with repository.connection() as db:
        db.execute('BEGIN IMMEDIATE')
        db.execute(POSTGRES_DDL if repository.database_url else SQLITE_DDL)
        if repository.database_url:
            db.execute('REVOKE ALL ON account_learner_links FROM PUBLIC')
            for role in ('anon', 'authenticated'):
                if db.execute('SELECT 1 FROM pg_roles WHERE rolname=?', (role,)).fetchone():
                    # Fixed role names; never user input.
                    db.execute(f'REVOKE ALL ON account_learner_links FROM {role}')
        db.execute('SELECT account_id,learner_id,created_at,link_version,proof_method,legacy_owner_digest,provider_session_digest,confirmation_digest FROM account_learner_links LIMIT 0')
    repository.account_links_ready = True
