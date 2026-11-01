# Security and privacy

GoiGrow's deployment is a controlled private beta. Staging entry, account identity
and learner ownership are separate checks. Do not interpret a hidden UI control,
an account email, a browser-selected ID or the shared staging code as learner ownership.

## Accounts and sessions

The browser calls same-origin FastAPI account endpoints; passwords are sent over
HTTPS to the backend for Supabase Auth password authentication. GoiGrow has no local
password table. Modern publishable provider keys and configured project origins
are validated; privileged service-role credentials are not accepted as substitutes.

The backend verifies eligible JWT claims and checks the trusted configured provider's
user/session state. Decoding claims alone is not authentication. Exact UUID allowlists,
confirmed email, non-anonymous active identity and current provider policy are required.
Public signup must stay disabled and email confirmation enabled; policy drift fails closed.
No public registration endpoint exists.

The ordinary invitation path checks invitation/activation state. An explicit single
owner-bootstrap setting permits an already allowlisted account to sign in with its
confirmed email/password without an invitation timestamp. It cannot expand the
allowlist or grant organization administration rights. Owner-only sign-in does not
require pasting an email link. Existing invitation/recovery link handling is a separate
limited flow; it is not a completed general-purpose one-click registration product.

Provider access/refresh tokens are encrypted in private server-side session records.
The browser receives an opaque `__Host-goigrow_session` cookie: Secure, HttpOnly,
SameSite=Lax, Path=/, no Domain. Absolute lifetime is at most seven days, with a
24-hour idle limit. Password/recovery sessions have a restricted purpose and shorter
lifetime. Logout revokes the current browser's application session; do not promise
unimplemented global-device logout.

Unsafe account actions also require the exact configured Origin, appropriate Fetch
Metadata and a session-bound CSRF token. Refresh/expiry and provider-session checks
remain server-side. No provider token, password or account ID is stored in browser
local storage. Auth responses are no-store and auth pages use a restrictive referrer policy.

## Staging and learner authorization

The signed staging cookie contains a browser ownership context with server-enforced
expiry. Re-entering the shared code with an authentic retained cookie can renew that
same context; losing it can create a different context. Cookie retention is not an
indefinite grant of access. `staging_resources` and request-scoped database checks
enforce ownership across learner records and nested resources.

Account sign-in does not silently create or claim a learner. Linking is independently
controlled and currently disabled. When authorized, the implementation requires fresh
verified authentication, server-owned proof of the original learner context, explicit
confirmation and transactional one-account/one-learner uniqueness. Ambiguity and
conflicts fail closed. Never accept a frontend learner selector or email match as
proof; never merge or reset profiles to resolve an access problem.

Linked records must use account ownership, including descendant operations. Retained
legacy staging rows must not bypass it. Disabling linking prevents new associations;
it must not remove enforcement for links that already exist. Do not drop association
tables or roll back to a staging-only authorizer once linked data exists without a
reviewed access/restoration plan.

## Data, input and external services

Application tables reside in private `tutor_private`, with public/browser-role access
restricted. Keep that schema outside Supabase's exposed Data API. Only the backend
uses the database connection; use TLS and the intended project/role. Supabase owns
its managed Auth tables. Do not fabricate invitation state or manually edit provider
credentials. Normal migrations and administration are separately authorized operations.

Pydantic bounds requests and structured responses. Ownership, idempotency, optimistic
versions and transactions protect data writes. Provider failure is not a wrong learner
answer. Native DOM/text rendering keeps model/user markup inert. CSP, same-origin
mutations, bounded request bodies, generic failures and application/provider rate limits
reduce exposure. Process-local limits require a single worker/instance; scale-out
requires an explicit coordination design rather than assuming quotas are global.

Microphone permission requires an explicit Record action. Preview is local; Transcribe
is a separate explicit upload disclosed as being sent to Groq. The backend accepts
validated 16 kHz mono PCM16 WAV, at most 60 seconds and 2 MiB, with concurrency,
per-learner and global rate limits. It uses Japanese transcription, not English
translation. Raw audio is not permanently stored by GoiGrow. Learners can inspect/edit
text before confirmation or sending. Provider retention is governed separately by
that account's policy/settings; do not promise zero retention solely from app behavior.

Optional reference retrieval treats source excerpts as untrusted data, bounds context,
filters suspicious instructions and checks copying. These controls do not prove perfect
injection resistance or permission to redistribute private reference material.

## PWA and browser storage

The worker caches only versioned public offline HTML, its CSS and one icon, with
integrity/response checks. Protected pages, API data, sessions, learner history,
recordings, transcripts and private sources are not worker-cached. It is an offline
reconnection screen, not offline authenticated study.

Browser local storage can retain selection/preferences and an account-mode hint;
these never authorize access. Safari, an installed iOS PWA, other browsers and a new
hostname can have independent storage/cookies. Do not copy tokens between them or
claim that sign-in alone restores original progress.

## Secret handling and operational boundaries

- Keep credentials, database URLs, encryption keys, access codes and private evidence
  in authorized secret storage, never source, public docs, Git or screenshots.
- Logs should use route templates and safe categories, not request/response bodies,
  provider error text, email links, account/learner identifiers or private conversations.
- Keep `.env`, data, references, private indexes and internal journals ignored. The
  source/history audit does not replace review of new documentation and assets.
- Retain database and session-encryption-key backups privately and separately. Restoring
  database state does not automatically restore provider sessions or original cookies.
- Do not weaken Auth/staging, rotate credentials, provision email providers, activate
  linking, delete accounts or alter production data as a side effect of documentation.

Configuration and deployment boundaries are in [deployment](deployment.md); the
identity model's source of truth is [architecture](architecture.md).
