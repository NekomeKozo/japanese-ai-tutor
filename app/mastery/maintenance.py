"""Local-only deterministic recomputation. No public mutation/debug endpoint."""
import argparse
from pathlib import Path
from uuid import UUID
from app.assessment.repository import AssessmentRepository
from app.mastery.service import MasteryService


def main():
    parser = argparse.ArgumentParser(description='Recompute one learner mastery from stored normalized evidence; stop server first.')
    parser.add_argument('--database', type=Path, required=True)
    parser.add_argument('--learner-id', type=UUID, required=True)
    args = parser.parse_args()
    if not args.database.is_file():
        parser.error('Database must already exist')
    repo = AssessmentRepository(str(args.database))
    with repo.connection() as db:
        if db.execute('PRAGMA user_version').fetchone()[0] not in (4,5):
            parser.error('Run the current app to migrate first')
    repo.ready = True
    print('Topics recomputed:', MasteryService(repo).recalculate_mastery(args.learner_id))


if __name__ == '__main__':
    main()
