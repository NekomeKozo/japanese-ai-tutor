# Phase 12B — Invitation-controlled accounts

Status: **implementation verified; live account activation and real email acceptance pending**.
Stop before Phase 12C. No learner linking, data migration, public beta or paid service.

## Foundation and approvals

Canonical `main` began at `cf3d0fc`, with Phase 12A implementation `4c061d3` present.
Tracked working tree was clean; unrelated untracked design references were preserved.
Read both Phase 12A documents. Baseline: 103 foundation/staging/hardening tests passed.
Owner approved administrative invitations, encrypted server sessions, 7-day absolute /
24-hour idle limits, current-browser logout and team-only testing without paid services.

Owner explicitly approved turning off **Allow new users to sign up**, while keeping
**Confirm email** enabled. Saved and verified in the existing Supabase project on
4 October 2026. Anonymous sign-in/manual linking remain off; Email is enabled.
Owner also approved/saved Site URL:
`https://japanese-ai-tutor.onrender.com/auth/callback`, with four exact redirect entries:

- `https://japanese-ai-tutor.onrender.com/auth/callback`
- `https://japanese-ai-tutor.onrender.com/auth/recovery`
- `http://localhost:8012/auth/callback`
- `http://localhost:8012/auth/recovery`

No signing keys, passwords, access codes, billing settings or existing users changed.

## Implementation and enforcement

FastAPI BFF implements bootstrap, invitation acceptance, email/password login,
restricted password setup/recovery, verified account status and logout under
`/api/account/`. No public registration route or provider `/signup` request exists.
Every account API still requires the existing staging cookie when the gate is on.
Public email landing shells provide no account data or staging authorization.
All account mutations additionally require exact Origin, Fetch Metadata checks and
a session-bound CSRF token. Per-client, keyed email-hash and global application limits supplement Supabase
limits; recovery requests have a two-per-hour global application limit.

Before bootstrap/login/verification/status/password/recovery, the server checks
Supabase `/settings`: signup disabled, email confirmation required, email provider
enabled and other reported providers disabled. Configuration drift fails closed.
Trusted `/user` verifies signatures, email confirmation, immutable provider invitation
timestamp and account ID; local JWT checks narrow issuer/audience/role/expiry/session.
Exact operator-approved user UUID allowlist and server beta membership enforce access.
Login cannot precede successful invitation/password activation.

`ACCOUNT_AUTH_ENABLED=false` remains the default. Disabled startup creates **no new
account tables**, exposes no Settings entry and leaves learning authorization unchanged.
Enabling requires provider origin/publishable key, exact frontend origin, separate
encryption keys and up to 20 canonical invited account UUIDs. No admin key is required.

## Email and recovery

Dashboard inspection found default templates are read-only without custom SMTP.
Default sending is for authorized Supabase team addresses only, capped at two emails
per hour with no delivery SLA. No custom SMTP, upgrade or paid provider was added.
[Official SMTP restrictions](https://supabase.com/docs/guides/auth/auth-smtp).

For this initial free team test, users **copy the original email verification link
without opening it** and paste it into GoiGrow. The backend parses only the configured
project's exact `/auth/v1/verify` link and expected invite/recovery type, rejects
duplicate/invalid parameters, and POSTs its token hash to Supabase. It never follows
the submitted URL or redirect destination. Provider access/refresh credentials arrive
only at the server. No link/password is persisted or included in logs or HTTP queries.
Default links normally redirect with session credentials in browser fragments;
GoiGrow immediately removes/rejects such fragments and asks for a fresh original link.
Click-to-verify template polish requires separately approved SMTP/configuration.
[Official email-link/POST verification behavior](https://supabase.com/docs/guides/auth/auth-email-templates).

Forgot-password requests return the same generic response for known/unknown addresses
and delivery/quota failures. A verified recovery session lasts ten minutes and can
only set a new password. New passwords require 12–128 characters plus any additional
provider policy. Provider owns password storage/comparison. Reset revokes all local
account sessions and requests provider-global logout; sign in afresh after completion.
**Actual invitation and reset email delivery has not been verified.**

## Sessions and database safety

Opaque `__Host-goigrow_session`: Secure, HttpOnly, SameSite=Lax, Path=/, no Domain.
Only nonce hashes are stored; provider credentials use versioned authenticated Fernet
encryption with current/older keys via MultiFernet. Separate operator secret; no token
storage in browser localStorage/sessionStorage, public HTML or worker cache.
Rotate nonce on authentication/verification. Preauth/restricted sessions last ten minutes;
normal sessions expire at seven days or 24 hours idle. Current status revalidates provider
identity; expired JWTs refresh inside a locked transaction and retain account/session ID.
Minimal successful security events log category/outcome only, with no account ID,
email, password, verification link or provider credential; existing server-log retention applies.
PostgreSQL row locks serialize each session's refresh without holding the legacy
application's global advisory lock during provider requests. SQLite uses BEGIN IMMEDIATE.

Additive `account_sessions` and `account_beta_members` plus one index live in the existing
private application schema; legacy migration version remains 8. No managed Auth tables
are created or modified. Activation checks read access to `auth.sessions` and account
requests verify exact live provider session/user membership. Missing privileges fail closed;
no automatic grant is issued. Provider logout revocation is therefore not inferred from
`/user` alone. Logout commits local deletion even if provider logout is unavailable.
[Supabase session semantics](https://supabase.com/docs/guides/auth/sessions).

Application account status exposes no email, learner IDs or saved history. Account changes
reload other open account pages and clear password/link fields. Legacy pages remain explicitly
the existing browser learning space, never claimed by or labelled as the signed-in account.
Safari and installed iOS PWA contexts sign in independently. Original-profile restoration
remains unresolved until separately authorized Phase 12C; no resets or merges performed.

Rollback: set account flag false. Additive tables remain; old staging learning continues.
Re-enabling retains membership/data; do not delete tables or reopen public provider signup.

## Validation

- Full offline backend suite: **689 passed, 20 optional/local PostgreSQL skips**;
  existing two dependency deprecation warnings only.
- Frontend/worker suite: **164 passed**, including nine new account interaction cases.
- Separate disposable local PostgreSQL run: **8 passed**, covering additive migration,
  repeat/rollback, concurrent refresh, mocked managed-session revocation and existing
  learning/storage regressions. Managed Supabase session existence is mocked in a generic
  local PostgreSQL instance; production read permission/revocation remains a live gate.
- Final focused account/foundation/staging/hardening run including local PostgreSQL:
  **128 passed**. Six additional upstream-response/deadline cases subsequently passed
  in the 30-case account suite (one optional PostgreSQL skip in that run).
- Invitation reuse/invalid/expired links, email verification, invalid credentials, invitation
  allowlist, signature rejection, Origin/CSRF/gate denial, expiry, cookie/owner isolation,
  generic recovery, rate limits, password/reset/logout, key rotation and no auto-link tested.
- Browser preview uses only mocked providers and disposable SQLite. Desktop at 1912px and
  iPhone-width 390px: no horizontal overflow; visible buttons exceed 44px. Native labels,
  status/alert states, invitation/recovery selection checked. No real credential entered.
- Actual iPhone Safari/PWA account login/email delivery **not yet verified**.
- Whitespace/source/history secret audit passed before commit; final release details below.

## Owner activation checkpoint

After disabled deployment is verified, the owner must privately provision one authorized
Supabase team invitation and configure Render's server environment:

| Setting | Required value / action |
| --- | --- |
| `SUPABASE_AUTH_URL` | Existing project HTTPS origin |
| `SUPABASE_AUTH_PUBLISHABLE_KEY` | Project publishable key, copied privately; never service-role |
| `FRONTEND_URL` | Existing GoiGrow HTTPS origin (already needed for staging) |
| `ACCOUNT_SESSION_ENCRYPTION_KEYS` | Separate Fernet key; generate with `python scripts/create_account_key.py`, copy ignored `.env.account-key` privately |
| `ACCOUNT_INVITED_IDS` | Exact UUID of the owner-invited team test user, not email/access code |
| `ACCOUNT_AUTH_ENABLED` | Keep false until preceding values, backup/rollback and provider session-read capability are verified; then enable for controlled acceptance |

The key generator refuses to overwrite an existing key and prints no key material.
On 5 October 2026 it created the Git-ignored `.env.account-key` locally; no value was
displayed, committed or sent to Render. The owner must copy it privately.
Keep a private key backup for rollback; lost keys require fresh account sign-in, never
resetting learner records. Retain older encryption keys during rotation until old sessions
expire/re-encrypt. Default team email service is not approval for outside testers.

Complete one controlled invitation → verification → password → login → logout → recovery
test, including invalid credentials and independent Safari/PWA login. Do not paste keys,
passwords, verification links or access codes into chat. Provider email quotas require
spacing invitation and recovery tests. No real accounts/emails were created by automation.

## Files and Phase 12C handover

New backend `app/accounts.py`, `app/api/accounts.py`; config/main/staging/storage integration;
new account HTML/CSS/JS and conditional Settings link; pinned cryptography dependency;
focused Python/Node tests; private key generator; environment example/README/this report.
Existing Phase 12A documents and all design references preserved.

Phase 12C must explicitly authorize and implement account-to-learner ownership/linking,
conflicts and cross-device restoration. Do not reuse a shared staging code or email match
as proof of profile ownership. No Phase 12C implementation is included.

## Release status

Implementation committed and pushed as `e6ac9d8341e9480aa730f287496718719963df3a`:
`Phase 12B - implement secure account registration and login`.
[GitHub Tests passed](https://github.com/NekomeKozo/japanese-ai-tutor/actions/runs/37211633655).
[Render deployment succeeded and is Live](https://dashboard.render.com/web/srv-dap75h942hec7394sdi0/deploys/dep-db16ltrtqb8s7390t9bg).
Verified on 5 October 2026: healthy `/health`, access page and manifest return 200;
unauthenticated learner/account APIs return 401, all with `Cache-Control: no-store`.
The free service initially needed to wake up; subsequent health checks passed.
Read-only signed-in browser checks restored the saved Home, Study, Tutor and Progress
views, and Settings had no account entry or visible error. No study answers, messages,
preferences or learner histories were changed for these checks. The final account preview
was checked again at 390px with no horizontal overflow and visible 47.59px buttons.

Live account activation and actual invitation/recovery email acceptance are pending.
Render environment inspection found no account activation/provider/key/allowlist
settings present; default-disabled deployment creates no account schema or entry point.
These settings and account/password entry require an owner handoff; the computer-use
confirmation policy requires the owner to enter and submit new credentials privately.
No Phase 12C work has begun.
