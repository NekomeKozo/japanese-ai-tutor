"""Private, expiring owner-assisted exception. No browser-selected identities.

Consumes the independently reviewed Candidate A evidence; cannot discover or
approve a candidate. The optional encrypted artifact lives outside the checkout.
History SQL intentionally matches the read-only identification review exactly.
"""
from datetime import datetime, timezone
import hashlib
import hmac
import json
from pathlib import Path

from app.config import PROJECT_ROOT
from app.errors import TutorError

KIND = 'owner_assisted_candidate_a_v1'
METHOD = 'checkpoint_legacy_owner_v1'
DIRECT = ('learner_state', 'learner_profiles', 'assessments', 'skill_state',
          'skill_history', 'learner_topics', 'mistake_state', 'learning_events',
          'tutor_sessions', 'study_sessions', 'mastery_evidence', 'topic_mastery',
          'mastery_history', 'review_schedules', 'review_attempts',
          'conversation_states', 'jlpt_sessions')
CHILDREN = {'assessment_answers': ('assessments', 'assessment_id', 'id'),
            'conversation_turns': ('tutor_sessions', 'session_id', 'session_id'),
            'study_activities': ('study_sessions', 'session_id', 'session_id'),
            'jlpt_session_questions': ('jlpt_sessions', 'session_id', 'session_id'),
            'jlpt_attempts': ('jlpt_sessions', 'session_id', 'session_id')}


def rejected():
    return TutorError('link_checkpoint_invalid',
        'The verified profile checkpoint is unavailable or changed. Owner review is required; nothing was linked.', 409)


def keyed(key, value):
    return hmac.new(key, str(value).encode(), hashlib.sha256).hexdigest()


def history(db, learner, key):
    result = {}
    for table in (*DIRECT, *CHILDREN):
        # Identifiers are exclusively the fixed table/column literals above.
        if table in DIRECT:
            query = f"SELECT encode(sha256(convert_to(row_to_json(t)::text,'UTF8')),'hex') FROM {table} t WHERE t.learner_id=?"
        else:
            parent, foreign, pk = CHILDREN[table]
            query = f"SELECT encode(sha256(convert_to(row_to_json(t)::text,'UTF8')),'hex') FROM {table} t JOIN {parent} p ON t.{foreign}=p.{pk} WHERE p.learner_id=?"
        hashes = sorted(row[0] for row in db.execute(query, (learner,)).fetchall())
        result[table] = {'count': len(hashes), 'digest': keyed(key, json.dumps(hashes))}
    return keyed(key, json.dumps(result, sort_keys=True))


def owner_state(db, account, key):
    row = db.execute('SELECT id,created_at,email_confirmed_at,deleted_at,banned_until,is_anonymous FROM auth.users WHERE id=? FOR SHARE', (account,)).fetchone()
    if (not row or row[2] is None or row[3] is not None or row[5] is not False
            or (row[4] is not None and row[4] > datetime.now(timezone.utc))):
        raise rejected()
    return keyed(key, tuple(str(value) for value in row))


def seal_review(review_bytes, selection, accounts, *, now):
    """Offline operator preparation only; never mounted as an HTTP endpoint.

    Requires BOTH original review and independently bound second verification.
    Does not connect to a database, refresh evidence, or authorize a real link.
    """
    try:
        review = json.loads(review_bytes)
        key = bytes.fromhex(review['key'])
        unsigned = {k: v for k, v in selection.items() if k != 'selection_binding_digest'}
        if (review['version'] != 1 or selection['version'] != 1 or len(key) != 32
                or selection['candidate'] != 'Candidate A'
                or not hmac.compare_digest(keyed(key, json.dumps(unsigned, sort_keys=True)), selection['selection_binding_digest'])
                or hashlib.sha256(review_bytes).hexdigest() != selection['review_checkpoint_sha256']):
            raise ValueError()
        selected = review['candidates']['Candidate A']
        expected = {'approved_owner_sha256': review['approved_owner_sha256'],
                    'approved_owner_state_digest': review['approved_owner_state_digest'],
                    'legacy_context_digest': review['legacy_context_digest'],
                    'eligible_set_digest': review['eligible_set_digest'],
                    'selected_learner_digest': selected['learner_digest'],
                    'selected_history_digest': keyed(key, json.dumps(selected['history'], sort_keys=True))}
        if any(selection.get(k) != v for k, v in expected.items()):
            raise ValueError()
        owners = accounts.bootstrap_owners & accounts.allowed
        if len(owners) != 1 or hashlib.sha256(next(iter(owners)).encode()).hexdigest() != expected['approved_owner_sha256']:
            raise ValueError()
        verified_at = datetime.fromisoformat(selection['verified_at'])
        if verified_at.tzinfo is None:
            raise ValueError()
        verified = verified_at.timestamp()
        if not 0 <= now - verified < 86400:
            raise ValueError()
        return accounts.encrypt({'kind': KIND, 'version': 1, 'key': key.hex(),
            'issued': now, 'expires': min(now + 3600, verified + 86400),
            'binding': selection, 'evidence': expected})
    except (ValueError, KeyError, TypeError, OverflowError, AttributeError):
        raise rejected() from None


class CandidateCheckpoint:
    def __init__(self, links):
        self.links = links

    def load(self):
        try:
            path = Path(self.links.settings.account_learner_checkpoint_path)
            # No static/public/repository path, including symlinks into it.
            if not path.is_absolute() or path.resolve().is_relative_to(PROJECT_ROOT):
                raise ValueError()
            with path.open('rb') as stream:
                raw = stream.read(32769)
            if len(raw) > 32768:
                raise ValueError()
            payload = self.links.accounts.decrypt(raw.decode())
            now = self.links.accounts.clock()
            if (payload['kind'] != KIND or payload['version'] != 1
                    or not payload['issued'] <= now < payload['expires']
                    or payload['expires'] - payload['issued'] > 3600):
                raise ValueError()
            key = bytes.fromhex(payload['key'])
            binding = payload['binding']
            unsigned = {k: v for k, v in binding.items() if k != 'selection_binding_digest'}
            evidence = payload['evidence']
            if (len(key) != 32 or binding['version'] != 1 or binding['candidate'] != 'Candidate A'
                    or set(evidence) != {'approved_owner_sha256', 'approved_owner_state_digest',
                        'legacy_context_digest', 'eligible_set_digest', 'selected_learner_digest', 'selected_history_digest'}
                    or not hmac.compare_digest(keyed(key, json.dumps(unsigned, sort_keys=True)), binding['selection_binding_digest'])
                    or any(binding.get(k) != v for k, v in evidence.items())):
                raise ValueError()
            return payload, key, hashlib.sha256(raw).hexdigest()
        except (OSError, ValueError, KeyError, TypeError, AttributeError, TutorError):
            raise rejected() from None

    def resolve(self, db, account, owner):
        if not self.links.repository.database_url:
            raise rejected()  # Original review is PostgreSQL evidence, never portable.
        payload, key, checkpoint_digest = self.load()
        evidence = payload['evidence']
        if (account not in self.links.accounts.allowed
                or account not in self.links.accounts.bootstrap_owners
                or hashlib.sha256(account.encode()).hexdigest() != evidence['approved_owner_sha256']
                or keyed(key, owner) != evidence['legacy_context_digest']
                or owner_state(db, account, key) != evidence['approved_owner_state_digest']):
            raise rejected()
        rows = self.links.candidates(db, owner)
        ids = [str(row[0]) for row in rows]
        if keyed(key, json.dumps(sorted(keyed(key, value) for value in ids))) != evidence['eligible_set_digest']:
            raise rejected()
        selected = [row for row in rows if hmac.compare_digest(keyed(key, str(row[0])), evidence['selected_learner_digest'])]
        if len(selected) != 1 or history(db, str(selected[0][0]), key) != evidence['selected_history_digest']:
            raise rejected()
        # The reviewed eligible set was wholly unlinked. A new association for
        # another candidate invalidates that review; never infer a substitute.
        others = [value for value in ids if value != str(selected[0][0])]
        if others and db.execute('SELECT 1 FROM account_learner_links WHERE learner_id IN (' + ','.join('?' for _ in others) + ') LIMIT 1', tuple(others)).fetchone():
            raise rejected()
        return selected[0], checkpoint_digest
