import logging
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from uuid import UUID

from pydantic import ValidationError

from app.assessment.questions import BANK_VERSION, QuestionBank
from app.assessment.schemas import AssessmentState, LearnerProfile
from app.errors import TutorError
from app.storage import postgres_connection
import psycopg

logger = logging.getLogger(__name__)


class AssessmentRepository:
    """SQLite snapshots plus append-only evidence, committed in one transaction."""

    def __init__(self, path: str, database_url: str = ''):
        self.path = Path(path)
        self.database_url = database_url
        self.ready = False
        self.account_links_ready = False

    @contextmanager
    def connection(self, *, initialize=False):
        connection = None
        try:
            if self.database_url:
                with postgres_connection(self.database_url, initialize=initialize) as db:
                    from app.learner_access import check_transaction
                    check_transaction(db, links_ready=self.account_links_ready)
                    yield db
                return
            connection = sqlite3.connect(str(self.path), timeout=3)
            connection.execute('PRAGMA foreign_keys=ON')
            with connection:
                from app.learner_access import check_transaction
                # Hold SQLite's write lock from authorization through the data
                # operation, mirroring the PostgreSQL transaction advisory lock.
                from app.learner_access import scope
                if scope.get() is not None and scope.get().resources:
                    connection.execute('BEGIN IMMEDIATE')
                check_transaction(connection, links_ready=self.account_links_ready)
                from app.storage import SQLiteConnection
                yield SQLiteConnection(connection)
        except (sqlite3.Error, psycopg.Error, OSError, ValidationError, ValueError) as exc:
            logger.error('Assessment storage failure: %s', type(exc).__name__)
            raise TutorError('assessment_storage', 'Assessment storage is unavailable. Please retry; ordinary chat is still available.', 503) from exc
        finally:
            if connection:
                connection.close()

    def initialize(self, bank: QuestionBank):
        try:
            if not self.database_url:
                self.path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise TutorError('assessment_storage', 'Cannot create assessment storage. Check ASSESSMENT_DB_PATH.', 503) from exc
        with self.connection(initialize=True) as db:
            version = db.execute('PRAGMA user_version').fetchone()[0]
            if version not in (0, 1, 2, 3, 4, 5, 6, 7, 8):
                raise TutorError('database_version', 'This assessment database version is not supported by this app.', 503)
            # First additive migration. Phase 1 has no database or migration framework.
            if version == 0:
                db.executescript('''
                CREATE TABLE IF NOT EXISTS assessment_questions (
                    bank_version TEXT NOT NULL, id TEXT NOT NULL, payload TEXT NOT NULL,
                    PRIMARY KEY (bank_version, id));
                CREATE TABLE IF NOT EXISTS assessments (
                    id TEXT PRIMARY KEY, learner_id TEXT NOT NULL, version INTEGER NOT NULL,
                    state_json TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS assessment_answers (
                    assessment_id TEXT NOT NULL REFERENCES assessments(id),
                    question_id TEXT NOT NULL, submission_id TEXT NOT NULL, payload TEXT NOT NULL,
                    PRIMARY KEY (assessment_id, question_id), UNIQUE (assessment_id, submission_id));
                CREATE TABLE IF NOT EXISTS learner_profiles (
                    learner_id TEXT PRIMARY KEY, assessment_id TEXT NOT NULL REFERENCES assessments(id),
                    profile_json TEXT NOT NULL);
                PRAGMA user_version=1;
            ''')
            db.execute('BEGIN IMMEDIATE')
            from app.learner.migrations import migrate
            migrate(db)
            from app.curriculum.migrations import migrate as migrate_curriculum
            migrate_curriculum(db)
            from app.mastery.migrations import migrate as migrate_mastery
            migrate_mastery(db)
            from app.review.migrations import migrate as migrate_reviews
            migrate_reviews(db)
            from app.conversation.migrations import migrate as migrate_conversation
            migrate_conversation(db)
            from app.jlpt.migrations import migrate as migrate_jlpt
            migrate_jlpt(db)
            from app.audio_progress.migrations import migrate as migrate_audio
            migrate_audio(db)
            # Bound batches preserve INSERT OR IGNORE semantics while avoiding one
            # remote round trip per question. No existing question/history is replaced.
            for offset in range(0, len(bank.items), 100):
                batch = bank.items[offset:offset + 100]
                values = tuple(value for question in batch for value in
                               (BANK_VERSION, question.id, question.model_dump_json()))
                db.execute('INSERT OR IGNORE INTO assessment_questions VALUES ' +
                           ','.join('(?,?,?)' for _ in batch), values)
        self.ready = True

    def require_ready(self):
        if not self.ready:
            raise TutorError('assessment_storage', 'Assessment storage is unavailable. Check the server configuration; ordinary chat is still available.', 503)

    def create(self, state: AssessmentState):
        self.require_ready()
        with self.connection() as db:
            db.execute('INSERT INTO assessments VALUES (?, ?, ?, ?)',
                (str(state.assessment_id), str(state.learner_id), state.version, state.model_dump_json()))

    def get(self, assessment_id: UUID) -> AssessmentState:
        self.require_ready()
        with self.connection() as db:
            row = db.execute('SELECT state_json FROM assessments WHERE id=?', (str(assessment_id),)).fetchone()
            if not row:
                raise TutorError('assessment_not_found', 'Assessment not found. Start a new placement assessment.', 404)
            return AssessmentState.model_validate_json(row[0])

    def save_answer(self, state: AssessmentState, expected_version: int):
        self.require_ready()
        with self.connection() as db:
            changed = db.execute('UPDATE assessments SET version=?, state_json=? WHERE id=? AND version=?',
                (state.version, state.model_dump_json(), str(state.assessment_id), expected_version)).rowcount
            if changed != 1:
                raise TutorError('assessment_conflict', 'The assessment changed in another request. Reload to continue.', 409)
            evidence = state.evidence[-1]
            db.execute('INSERT INTO assessment_answers VALUES (?, ?, ?, ?)',
                (str(state.assessment_id), evidence.question.id, str(evidence.submission_id), evidence.model_dump_json()))
            if state.profile:
                db.execute('INSERT INTO learner_profiles VALUES (?, ?, ?)',
                    (str(state.learner_id), str(state.assessment_id), state.profile.model_dump_json()))
                from app.learner.initialization import initialize_placement
                initialize_placement(db, state.profile.model_dump_json(), state.model_dump_json())

    def profile(self, learner_id: UUID) -> LearnerProfile:
        self.require_ready()
        with self.connection() as db:
            row = db.execute('SELECT profile_json FROM learner_profiles WHERE learner_id=?', (str(learner_id),)).fetchone()
            if not row:
                raise TutorError('profile_not_found', 'No completed placement profile exists for this learner.', 404)
            return LearnerProfile.model_validate_json(row[0])
