"""Owner-only, explicit legacy-capability linking and account profile resolution."""
import hashlib
import hmac

from app.accounts import digest
from app.auth import AuthenticationError
from app.errors import TutorError
from app.account_link_migration import present

CONFIRMATION_SECONDS = 300
FRESH_AUTH_SECONDS = 600


class AccountLinks:
    def __init__(self, repository, settings, accounts=None):
        self.repository, self.settings, self.accounts = repository, settings, accounts

    def inspect(self):
        if not self.repository.ready:
            if self.settings.account_learner_linking_enabled or self.settings.account_auth_enabled:
                raise RuntimeError('Account ownership requires available storage.')
            return
        with self.repository.connection() as db:
            self.repository.account_links_ready = present(db, bool(self.repository.database_url))
            if self.repository.account_links_ready:
                db.execute('SELECT account_id,learner_id,link_version FROM account_learner_links LIMIT 0')
        if self.settings.account_learner_linking_enabled and not self.repository.account_links_ready:
            raise RuntimeError('Learner linking requires its separately approved additive migration.')

    def principal(self, request, *, required=False):
        if not getattr(request.state, 'account_checked', False):
            request.state.account_checked = True
            request.state.account_principal = None
            if self.accounts:
                from app.accounts import COOKIE
                from app.api.accounts import owner
                value = request.cookies.get(COOKIE)
                if value:
                    try:
                        request.state.account_principal = self.accounts.principal(value, owner(request))
                    except AuthenticationError as exc:
                        if exc.status == 503:
                            raise
        result = getattr(request.state, 'account_principal', None)
        if required and not result:
            raise AuthenticationError()
        return result

    def owned(self, db, account):
        if not self.repository.account_links_ready:
            return None
        row = db.execute('SELECT learner_id FROM account_learner_links WHERE account_id=?', (account,)).fetchone()
        return str(row[0]) if row else None

    def context(self, nonce, owner):
        principal = self.accounts.principal(nonce, owner)
        with self.repository.connection() as db:
            learner = self.owned(db, principal.account_id)
        return {'state': 'linked' if learner else 'unlinked',
                **({'learner_id': learner} if learner else {}),
                'linking_enabled': self.settings.account_learner_linking_enabled}

    def eligible(self, db, owner):
        rows = db.execute("SELECT l.learner_id,l.estimated_level,l.profile_source FROM learner_state l JOIN staging_resources r ON r.resource_id=l.learner_id AND r.kind='learner' WHERE r.owner_id=? ORDER BY l.learner_id", (owner,)).fetchall()
        if not rows:
            raise TutorError('link_context_missing', 'Open the original browser with your saved progress. No eligible learning profile was found here.', 409)
        if len(rows) != 1:
            raise TutorError('link_context_ambiguous', 'Several legacy profiles are present. Owner-assisted verification is required; no profile was selected or changed.', 409)
        return rows[0]

    def linking_allowed(self, row, owner):
        if not self.settings.account_learner_linking_enabled or not self.repository.account_links_ready:
            raise TutorError('linking_unavailable', 'Learning-profile linking is awaiting owner activation.', 503)
        if row[4] != 'ready' or str(row[2]) not in self.accounts.bootstrap_owners:
            raise AuthenticationError()
        if not self.settings.staging_access_enabled or not owner or owner == 'development':
            raise AuthenticationError()
        if row[6] + FRESH_AUTH_SECONDS <= self.accounts.clock():
            raise TutorError('link_reauthentication_required', 'Sign out and sign in again before linking your learning profile.', 401)

    def preview(self, nonce, owner):
        self.accounts.provider.policy()
        with self.accounts.transaction() as db:
            row, _ = self.accounts.resolve(db, nonce, owner)
            self.linking_allowed(row, owner)
            linked = self.owned(db, str(row[2]))
            if linked:
                return {'state': 'linked', 'message': 'Your learning profile is already linked.'}
            learner, level, source = self.eligible(db, owner)
            if db.execute('SELECT 1 FROM account_learner_links WHERE learner_id=?', (learner,)).fetchone():
                raise TutorError('link_conflict', 'This learning profile cannot be linked. No ownership was changed.', 409)
            proof = {'kind': 'learner_link_v1', 'account': str(row[2]), 'learner': learner,
                     'owner': self.audit(owner), 'nonce': digest(nonce),
                     'expires': self.accounts.clock() + CONFIRMATION_SECONDS}
            return {'state': 'eligible', 'summary': {'estimated_level': level, 'profile_source': source},
                    'confirmation': self.accounts.encrypt(proof)}

    def audit(self, value):
        return hmac.new(self.accounts.csrf_key, ('learner-link:' + value).encode(), hashlib.sha256).hexdigest()

    def confirm(self, nonce, owner, confirmation):
        self.accounts.provider.policy()
        proof = self.accounts.decrypt(confirmation)
        if not isinstance(proof, dict):
            raise AuthenticationError()
        with self.accounts.transaction() as db:
            row, _ = self.accounts.resolve(db, nonce, owner)
            self.linking_allowed(row, owner)
            if (proof.get('kind') != 'learner_link_v1' or proof.get('account') != str(row[2])
                    or proof.get('owner') != self.audit(owner) or proof.get('nonce') != digest(nonce)):
                raise AuthenticationError()
            # Same lock as learner repository transactions: authorization is
            # rechecked within those transactions, so a link cannot race a
            # legacy-authorized write. Account refresh keeps its existing lock.
            if self.repository.database_url:
                db.execute('SELECT pg_advisory_xact_lock(650065)')
            linked = self.owned(db, str(row[2]))
            if linked:
                if linked != proof.get('learner'):
                    raise TutorError('link_conflict', 'Your account already has a different learning profile. No ownership was changed.', 409)
                return {'state': 'linked', 'message': 'Your learning profile is already linked.'}
            if not isinstance(proof.get('expires'), (int, float)) or proof['expires'] <= self.accounts.clock():
                raise TutorError('link_confirmation_expired', 'Refresh the linking page and confirm again. Nothing was changed.', 409)
            learner, _, _ = self.eligible(db, owner)
            if learner != proof.get('learner'):
                raise TutorError('link_context_changed', 'The learning context changed. Refresh before linking; nothing was changed.', 409)
            if db.execute('SELECT 1 FROM account_learner_links WHERE learner_id=?', (learner,)).fetchone():
                raise TutorError('link_conflict', 'This learning profile cannot be linked. No ownership was changed.', 409)
            db.execute('INSERT INTO account_learner_links VALUES (?,?,?,?,?,?,?,?)',
                (str(row[2]), learner, self.accounts.clock(), 1, 'signed_legacy_owner_v1',
                 self.audit(owner), self.audit(row[3]), digest(confirmation)))
        return {'state': 'linked', 'message': 'Learning profile linked successfully.'}
