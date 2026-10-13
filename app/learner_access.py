"""Request-scoped authorization, rechecked inside learner data transactions.

No browser identifier is an ownership proof. Linked resources always require the
verified account, including when new linking or account authentication is disabled.
"""
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Callable

from app.errors import TutorError


@dataclass(frozen=True)
class Principal:
    account_id: str
    nonce_hash: str
    provider_session: str
    created_at: float


@dataclass(frozen=True)
class AccessScope:
    owner: str | None
    principal: Principal | None
    resources: tuple
    account_mode: bool = False
    now: float | Callable[[], float] = 0


scope = ContextVar('learner_access_scope', default=None)


def unavailable():
    raise TutorError('learner_access_required', 'Sign in to the account that owns this learning profile.', 401)


def resource_learner(db, kind, identifier):
    if kind == 'learner':
        return str(identifier)
    # Fixed SQL identifiers only; values stay parameterized.
    if kind == 'assessment':
        row = db.execute('SELECT learner_id FROM assessments WHERE id=?', (str(identifier),)).fetchone()
    elif kind == 'session':
        row = db.execute('SELECT learner_id FROM tutor_sessions WHERE session_id=?', (str(identifier),)).fetchone()
    else:
        row = None
    return str(row[0]) if row else None


def authorize(db, kind, identifier, context, *, links_ready):
    learner = resource_learner(db, kind, identifier) if links_ready else None
    link = db.execute('SELECT account_id FROM account_learner_links WHERE learner_id=?', (learner,)).fetchone() if learner else None
    if link:
        principal = context.principal
        if not principal or str(link[0]) != principal.account_id:
            unavailable()
        # Logout/expiry between the request's provider verification and a data
        # transaction cannot reuse the previous account's learner authorization.
        now = context.now() if callable(context.now) else context.now
        active = db.execute("SELECT 1 FROM account_sessions WHERE nonce_hash=? AND account_id=? AND staging_owner=? AND purpose='ready' AND absolute_expiry>? AND touched_at>?",
            (principal.nonce_hash, principal.account_id, context.owner or 'development', now, now - 86400)).fetchone()
        if not active:
            unavailable()
        return
    if context.principal and learner and (context.account_mode or links_ready):
        # An authenticated unlinked account is not a fallback legacy identity.
        raise TutorError('learner_not_linked', 'Link your approved learning profile before continuing.', 409)
    if context.owner:
        row = db.execute('SELECT owner_id FROM staging_resources WHERE kind=? AND resource_id=?', (kind, str(identifier))).fetchone()
        if not row or row[0] != context.owner:
            raise TutorError('not_found', 'This study resource is unavailable in your staging session.', 404)


def check_transaction(db, *, links_ready):
    context = scope.get()
    if context:
        for kind, identifier in context.resources:
            authorize(db, kind, identifier, context, links_ready=links_ready)
