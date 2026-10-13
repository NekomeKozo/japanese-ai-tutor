"""Explicit Phase 12C migration; planning never connects or changes data.

Run from the repository root. --apply requires the owner checkpoint and backup;
application startup deliberately never calls this migration.
"""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.account_link_migration import POSTGRES_DDL, migrate, present
from app.assessment.repository import AssessmentRepository
from app.config import Settings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group()
    action.add_argument('--check', action='store_true', help='Read-only presence/prerequisite check')
    action.add_argument('--apply', action='store_true', help='Apply only the additive association schema')
    parser.add_argument('--owner-approved', action='store_true')
    parser.add_argument('--backup-confirmed', action='store_true')
    args = parser.parse_args()
    if not args.check and not args.apply:
        print('BEGIN;\nSET LOCAL search_path TO tutor_private;')
        print(POSTGRES_DDL.replace('account_learner_links', 'tutor_private.account_learner_links', 1).replace('REAL', 'DOUBLE PRECISION') + ';')
        print('REVOKE ALL ON tutor_private.account_learner_links FROM PUBLIC, anon, authenticated;')
        print('COMMIT;')
        print('-- Application schema version 8 and all learner records remain unchanged.')
        return 0
    if args.apply and not (args.owner_approved and args.backup_confirmed):
        parser.error('--apply requires the explicit owner checkpoint and a confirmed restorable backup')
    settings = Settings()
    if args.apply and settings.account_learner_linking_enabled:
        parser.error('Keep new linking disabled while applying the separately approved migration')
    repo = AssessmentRepository(settings.assessment_db_path, settings.database_url.get_secret_value())
    if args.check:
        with repo.connection() as db:
            db.execute('SET TRANSACTION READ ONLY' if repo.database_url else 'PRAGMA query_only=ON')
            exists = present(db, bool(repo.database_url))
            # Queries contain no learner/account identifiers or private values.
            db.execute('SELECT learner_id FROM learner_state LIMIT 0')
            auth_fk = bool(repo.database_url and db.execute("SELECT has_column_privilege(current_user,'auth.users','id','REFERENCES')").fetchone()[0])
        print('learner_id_available=true')
        print('account_learner_links_present=' + str(exists).lower())
        print('account_id_auth_reference_available=' + str(auth_fk).lower())
    else:
        migrate(repo)
        print('account_learner_links_present=true; learning_records_modified=false')
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception:
        # Never display database exception details, connection strings or values.
        print('Migration/check failed. No partial migration was committed; inspect safe server diagnostics.', file=sys.stderr)
        raise SystemExit(1) from None
