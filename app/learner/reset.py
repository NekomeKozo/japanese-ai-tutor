"""Explicit local developer reset; stop the server and back up the database first."""
import argparse
from pathlib import Path
from uuid import UUID

from app.assessment.repository import AssessmentRepository
from app.learner.initialization import initialize_default, initialize_placement


def reset_learner(repository, learner_id, confirmation):
    key = str(UUID(str(learner_id)))
    if str(confirmation) != key:
        raise ValueError('Confirmation must exactly match the learner UUID.')
    repository.require_ready()
    with repository.connection() as db:
        db.execute('BEGIN IMMEDIATE')
        if not db.execute('SELECT 1 FROM learner_state WHERE learner_id=?', (key,)).fetchone():
            raise ValueError('Learner not found.')
        baseline = db.execute('SELECT p.profile_json,a.state_json FROM learner_profiles p JOIN assessments a ON a.id=p.assessment_id WHERE p.learner_id=?', (key,)).fetchone()
        if db.execute('PRAGMA user_version').fetchone()[0]>=5:
            for table in ('review_attempts','review_schedules'):
                db.execute(f'DELETE FROM {table} WHERE learner_id=?',(key,))
        if db.execute('PRAGMA user_version').fetchone()[0] >= 4:
            for table in ('mastery_history', 'topic_mastery', 'mastery_evidence'):
                db.execute(f'DELETE FROM {table} WHERE learner_id=?', (key,))
        if db.execute('PRAGMA user_version').fetchone()[0]>=3:
            db.execute('DELETE FROM study_activities WHERE session_id IN (SELECT session_id FROM study_sessions WHERE learner_id=?)',(key,))
            db.execute('DELETE FROM study_sessions WHERE learner_id=?',(key,))
        db.execute('DELETE FROM conversation_turns WHERE session_id IN (SELECT session_id FROM tutor_sessions WHERE learner_id=?)', (key,))
        for table in ('tutor_sessions', 'learning_events', 'mistake_state', 'learner_topics', 'skill_history', 'skill_state', 'learner_state'):
            db.execute(f'DELETE FROM {table} WHERE learner_id=?', (key,))
        if baseline:
            initialize_placement(db, *baseline)
        else:
            initialize_default(db, key)


def main():
    parser = argparse.ArgumentParser(description='Reset one learner’s learning memory, sessions and preferences; preserve original placement. Stop the server and back up the database first.')
    parser.add_argument('--database', type=Path, required=True)
    parser.add_argument('--learner-id', type=UUID, required=True)
    parser.add_argument('--confirm-reset', type=UUID, required=True, help='Repeat the exact learner ID to confirm deletion.')
    args = parser.parse_args()
    if not args.database.is_file():
        parser.error('Database must already exist.')
    repository = AssessmentRepository(str(args.database.resolve()))
    with repository.connection() as db:
        if db.execute('PRAGMA user_version').fetchone()[0] not in (2,3,4,5):
            parser.error('Run the current application once to migrate this database before resetting.')
    repository.ready = True
    reset_learner(repository, args.learner_id, args.confirm_reset)
    print('Selected learner reset to original placement or unassessed defaults. Other learners and assessments preserved.')


if __name__ == '__main__':
    main()
