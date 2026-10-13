# Phase 12B — Invitation-controlled accounts

Status: **owner-only password bootstrap implemented and tested locally; deployment/configuration and live owner login pending. Resend/Send Email Hook work paused.**
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
displayed or committed. The owner subsequently entered the key directly into Render.
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
The owner saved all six activation settings privately in Render and redeployed with
`ACCOUNT_AUTH_ENABLED=false`. [That deployment is Live](https://dashboard.render.com/web/srv-dap75h942hec7394sdi0/deploys/dep-db17tmqd0e5s73eh77v0)
at documentation commit `4f8bc0e`; [its Tests passed](https://github.com/NekomeKozo/japanese-ai-tutor/actions/runs/37215488639).
Default-disabled deployment creates no account schema or entry point.
Account/password entry requires an owner handoff; the computer-use confirmation policy
requires the owner to enter and submit new credentials privately.
No Phase 12C work has begun.

## Saved-configuration preflight — 5 October 2026

Read-only checks after the owner's redeployment:

- All six setting names are present; the exact `false` flag and provider/frontend origins
  match. Publishable-key format matches the application validator, and a private comparison
  confirms that it is the existing project's publishable key. Encryption-key format and
  canonical invited-UUID format pass. Only pass/fail results were returned; values were
  re-hidden, and no credentials were copied into Git or this report.
- Supabase still disables public signup, anonymous sign-in, manual linking and other
  providers; Email and Confirm email remain enabled. The four approved redirects and
  Site URL remain exact, with no wildcard entries. The project remains on the Free plan.
- Health/access/manifest checks pass; unauthenticated APIs retain 401 and `no-store`.
  Signed-in Settings has no account entry or visible error.
- A SELECT-only Supabase check confirms the existing application's database role has
  Auth-schema usage and SELECT on both `auth.sessions.id` and `user_id`, plus CREATE in
  the existing private schema. Both application account tables are absent. No rows,
  schema, grants, authentication settings or learner records were changed by these checks.
- **Activation blocker:** the configured UUID identifies an existing, non-anonymous email
  user, but `invited_at` is NULL and the email is already confirmed. Phase 12B requires
  a trusted provider invitation record; this user would be rejected. The owner confirmed
  using **Create User**. Supabase's supported invitation action is **Add user → Send
  invitation**, and it rejects invitations to already-confirmed users
  ([official documentation](https://supabase.com/docs/guides/auth/users)). Do not delete,
  reset or alter that record, or weaken invitation enforcement to accept it. The owner
  supplied an alternate address and subsequently corrected its team status. The owner's
  Team screenshot confirms that the alternate address is already the organization Owner,
  so it meets the default email service's team-address requirement. No new organization
  membership, role change or custom SMTP setup is needed. The owner then reported also
  using Create User for the alternate address. The existing repository database connection
  enabled read-only dependency verification despite browser-control timeouts. The original
  manual Create User record remains unchanged; the separately approved cleanup of the
  newly created alternate-address test record is documented below.

Remaining prerequisites: resolve the invitation-record blocker through an approved
provider invitation workflow; confirm private encryption-key backup and rollback readiness;
then obtain explicit owner approval before changing the flag or starting live account/email
acceptance. No emails were sent, credentials submitted, passwords changed, account sessions
created or account features enabled during this preflight.

## Owner-authorized test-user cleanup — 5 October 2026

The owner explicitly authorized permanent deletion of only the newly created Auth test
record that passed the dependency check. No authorization was given to activate accounts
or begin Phase 12C. This was an operator cleanup, not an application account-deletion feature.

- The existing repository PostgreSQL connection matched the verified GoiGrow Supabase
  project. The existing role could perform the inspection; no additional privileged
  credential, permission grant, connection string or API key was requested or exposed.
- A fresh read-only inspection repeated all eight dependency checks and confirmed that
  the target record's creation/update timestamps predated the original check evidence.
  Its UUID and record fingerprint were bound privately as hashes, without logging the UUID.
- Immediately before deletion, a serializable transaction locked that specific record,
  reconfirmed its UUID/fingerprint and repeated the dependency checks. The DELETE was
  restricted by UUID, expected email and the confirmed, never-invited, never-signed-in
  conditions. Exactly one Auth user was deleted. No invitation timestamp was fabricated.
- Other Auth users and identities, and every existing private application table, were
  compared using row counts and content digests before and after the operation. All were
  unchanged. The project's organization membership was not accessed or modified.
- A separate read-only connection confirmed that the deleted UUID and its email were
  absent from Auth Users and reconfirmed the other-user/application comparisons.
- The local environment file is unchanged and `ACCOUNT_AUTH_ENABLED=false` remains set.
  No Render environment setting was changed; its previously verified disabled setting
  remains the intended state. `ACCOUNT_INVITED_IDS` has not been updated.

| Outcome | Result |
| --- | --- |
| Correct project connection | true |
| Target UUID reconfirmed | true |
| Exactly one intended Auth user deleted | true |
| Intended record absent after commit | true |
| Other Auth users and identities unchanged | true |
| Private application tables unchanged | true |
| Configuration unchanged | true |
| Local account authentication disabled | true |
| Invitation timestamp fabricated | false |

The owner subsequently confirmed sending the replacement through the official invitation
workflow. A read-only check using the same authorized database connection confirmed:

| Replacement invitation check | Result |
| --- | --- |
| Correct project; exactly one replacement | true |
| UUID differs from the deleted record | true |
| Replacement created after cleanup | true |
| Invitation timestamp present, at/after creation and not in the future | true |
| Non-anonymous email user | true |
| Email not yet confirmed; never signed in; no sessions | true |
| Application account tables still absent | true |
| Local account authentication still disabled | true |

The replacement UUID and invitation timestamp were bound privately as hashes; their values
were not printed or included in this report. No invitation link or credential was accessed.

The owner confirmed completing the Render `ACCOUNT_INVITED_IDS` update and deployment
after instructions to copy the newly invited user's UID directly from Supabase and retain
the exact `ACCOUNT_AUTH_ENABLED=false`. This configuration update is owner-confirmed;
its private Render value was not independently reread because browser automation times
out and no existing Render API key, connector or CLI is available.

Follow-up verification: all replacement invitation checks above still pass; no account
tables or sessions exist. Public `/health` and `/access` return 200 with `no-store`, and
health reports OK. Unauthenticated `/auth/sign-in` returns 401 with `no-store`; that is
evidence of the staging gate, not independent proof of the deployed account flag. No
account activation, invitation redemption, password submission or recovery request was
performed. The received invitation link should remain unopened and private until controlled
activation is separately approved. No Phase 12C work has begun.

## Controlled activation approval and blocker — 5 October 2026

The owner confirmed a private encryption-key backup and explicitly approved enabling
account authentication solely for the existing controlled, invitation-only Phase 12B
test. Public signup must remain disabled; the allowlist must not be broadened; existing
learner records must not be modified. This approval does not authorize Phase 12C.

Activation is blocked by unavailable Render controls. The browser inventory call again
timed out and reset its runtime. No existing Render API credential is available in the
repository environment or process, and the previous check found no Render connector or
CLI. The database connection cannot change Render's deployment environment. No new
privileged credential was requested and no alternate authentication system was introduced.

The agent has not changed `ACCOUNT_AUTH_ENABLED` or performed live account acceptance.
Invitation redemption/email verification, password setup, successful/incorrect login,
logout and recovery email acceptance remain unverified. The earlier mocked results do
not establish live completion. No account policy, provider permission, invitation
evidence, learner data or other configuration was changed during this activation attempt.

Owner handoff to resolve this blocker: Render → existing GoiGrow service → Environment →
Edit; change only `ACCOUNT_AUTH_ENABLED` from `false` to `true`, preserve the already
confirmed single-user `ACCOUNT_INVITED_IDS` and all other values, then save/redeploy.
After deployment is Live, resume the approved checks before opening the invitation link.
Rollback remains setting this same flag to `false` and redeploying, retaining account
tables and learner records. Phase 12B remains incomplete; stop before Phase 12C.

## Activated deployment preflight — 5 October 2026

The owner confirmed the authentication deployment is Live, resolving the environment-flag
handoff above. Independent public checks confirm `/health` returns 200, and all three
account screens (`/auth/sign-in`, `/auth/callback`, `/auth/recovery`) return 200 with the
account form, `Cache-Control: no-store` and `Referrer-Policy: no-referrer`. Unauthenticated
`/api/account/bootstrap` remains 401 with `no-store`, preserving the staging gate.

Read-only inspection through the existing correct-project connection confirms both
application account tables now exist and the database role retains required Auth-session
read capability. Exactly one intended test user matches the previously verified invitation
UUID, and its genuine invitation timestamp remains valid. No other beta members or
authenticated application accounts are present. At this preflight, the test email is still
unconfirmed, no provider sign-in is recorded, no approved beta membership exists and no
ready account session exists. Those are expected before invitation/password acceptance.

The local environment contains no staging access secret or Supabase publishable key, and
browser automation remains unavailable. Therefore the agent cannot submit a signed-in
live acceptance request using existing local credentials. The owner was given private
GoiGrow UI steps for invitation verification, password setup, valid login, logout and one
incorrect-password attempt. No password, access code or email link was requested in chat.
Recovery follows successful initial acceptance. Current public-signup policy is enforced
by the application on bootstrap/authentication; a completed owner flow is still required
to confirm that live policy check succeeds. No direct signup attempt or new test account
has been generated. Actual acceptance and recovery remain pending; no Phase 12C work.

## Owner-requested invitation UX investigation — 5 October 2026

The owner paused live acceptance and requested a conventional email-click → verification
→ password setup → sign-in experience. This investigation changed only this report and
used existing read-only database checks. No application code, template, SMTP setting,
provider account, billing, allowlist or Auth/learner record was modified. The manual
verification-link field remains until a replacement is safely implemented and tested.
Pausing the test did not itself change the deployed feature flag.

### Redacted diagnosis

The owner confirmed clicking the invitation button in the email. Read-only evidence:

| Check | Result |
| --- | --- |
| Correct project and original approved replacement UUID | true |
| Genuine invitation timestamp valid | true |
| Email verified by Supabase | true |
| Provider sign-in recorded | true |
| GoiGrow beta membership present | false |
| GoiGrow ready session present | false |
| Other beta members/authenticated application accounts present | false |

The default Supabase email click verifies upstream, then returns provider session tokens
in the redirect fragment. Current `frontend/account.js` removes URL query/fragment data
and never adopts that provider session; `AccountService` requires its own verified,
encrypted server session and approved UUID. Thus the clicked email verified the provider
email but did not complete GoiGrow activation. This explains the broken click experience;
it is not a missing invitation timestamp or missing database read capability.
Reusing an already consumed invitation is not a valid remedy. No link or provider token
was retrieved to test redemption again. The exact status of any later POST and its precise
internal rejection branch are unavailable: current denial errors deliberately collapse to
generic AuthenticationError responses, and accessible logs do not expose a reason code.
Do not claim a specific allowlist, CSRF, expiry or storage failure without further evidence.
Future safe diagnostic logging should record only fixed stage/reason categories and status,
never bodies, email, UUID, URL queries, credentials or provider error text.

### Existing default email configuration

Prior project inspection found templates read-only under default SMTP. Official policy
since 3 June 2026 locks templates on newly created Free projects; configuring custom SMTP
restores editing while retaining the Free plan. The existing configuration therefore cannot
provide the desired server-only handoff with editable invitation emails.
[Supabase policy](https://supabase.com/changelog/46599-changes-to-email-template-customisation-on-free-tier).

The default service remains restricted to organization-team recipients, currently two
emails/hour with best-effort delivery. Changing only Site URL or redirect allowlists does
not change the implicit session-fragment behavior. Parsing those access/refresh tokens
in JavaScript or adopting them via client storage would contradict the current architecture.
[SMTP restrictions](https://supabase.com/docs/guides/auth/auth-smtp),
[default redirect and server verification](https://supabase.com/docs/guides/auth/auth-email-templates).

### Available alternatives and prerequisites

1. **Existing SMTP account:** use an already available, owner-approved SMTP sender with
   host, TLS port, username, dedicated credential and an authorized From address. Enter
   credentials privately in Supabase's SMTP configuration; no frontend/Git secrets. This
   can avoid a new paid service, subject to the mailbox/provider's sending restrictions.
2. **Dedicated provider Free plan:** Resend is a documented Supabase SMTP integration;
   its documented setup requires an API key used as the SMTP credential plus a verified
   domain. DNS access and an authorized sender are prerequisites. Its current Free plan
   lists a 100/day limit. Domain purchase is not authorized or assumed. Keep upgrades and
   paid transactional overages disabled; no account/integration/key was created.
   [Integration prerequisites](https://resend.com/docs/send-with-supabase-smtp),
   [current pricing](https://resend.com/pricing).
3. **Retain default SMTP temporarily:** preserve the existing flow while paused. It does
   not meet the desired click experience under the current server-only session constraints.

The standard custom-template approach sends a short-lived, single-use email proof to the
application and verifies it with Supabase using a server POST; access/refresh tokens remain
backend-only. An email proof is itself sensitive even though it is not a session token.
The exact proof transport must satisfy the owner's prohibition on provider tokens in
public URLs. If that includes the provider verification hash, use an opaque application
ticket with the provider proof held encrypted server-side; that requires additional trusted
invitation/email integration and must be scoped/approved before implementation. Do not
silently treat a proof hash as public data or relax the URL requirement.

For either replacement, retain staging authorization, Origin/CSRF checks, the exact UUID
allowlist, provider signature/session checks, required email confirmation, encryption and
restricted password-setup state. Strip sensitive URL data and exclude it from all access
logs; disable link tracking, reject arbitrary redirects, and test expiry/replay and link
prefetch behavior before retiring the manual field. The user should only see GoiGrow
activation/password screens, never provider URL handling instructions.

The owner confirmed having neither a custom domain nor an SMTP provider. The existing
Render URL remains suitable for the application's HTTPS callback; it is not an owned
email domain with DNS records the owner can configure. No purchase is needed merely to
host the acceptance page.

### No-domain, free owner-test recommendation

**Prepare Resend Free with its default testing sender and Supabase's signed Send Email
Hook, subject to owner selection and approval.** Resend documents real test delivery only
to the email associated with the Resend account. Therefore that account must use the
already authorized tester's address; this is an owner-only test path, not delivery to
additional testers. No sender-domain purchase is required for that restricted test.
Use the documented HTTPS API for this proposal: the general SMTP/Supabase guides list
a verified domain as a prerequisite, so do not assume their no-domain exception works
end to end without a separate delivery check.
[Testing sender restriction](https://resend.com/docs/knowledge-base/403-error-resend-dev-domain),
[SMTP prerequisites](https://resend.com/docs/send-with-smtp).

Supabase's Send Email Hook is available on Free and replaces its built-in email sender.
It supplies verification data to a signed server request and can call Resend directly;
custom SMTP and editable default-SMTP templates are not prerequisites for this route.
This is a supported alternative to the locked templates, not an implemented replacement.
[Free hook availability](https://supabase.com/docs/guides/auth/auth-hooks),
[Send Email Hook](https://supabase.com/docs/guides/auth/auth-hooks/send-email-hook).

Proposed implementation boundary after approval:

1. Configure a dedicated sending credential and signed email hook privately. Remain on
   Free plans with paid upgrades/overages disabled. Do not use a personal mailbox password.
2. Have the hook validate its signature, action type and exact approved UUID, then issue
   a short-lived random GoiGrow ticket. Keep the Supabase verification proof encrypted
   in private server storage; store only a hash of the ticket. No Supabase proof or session
   token goes into the email link, browser storage, response bodies or logs.
3. Email only the private GoiGrow acceptance link. The ticket is still a sensitive bearer
   secret: exclude it from logs/referrers/tracking, clear it from the visible URL, and
   bind its exchange to an HttpOnly session. A scanner GET must not consume the proof
   or activate the account. A normal Continue/password form may be needed to confirm
   the learner's intent; there is no copying of verification URLs.
4. Exchange the proof with Supabase on the server, recheck invitation/email verification,
   UUID allowlist and provider session, then use existing restricted password setup and
   sign-in. Preserve staging authorization and Origin/CSRF protections. New private
   ticket storage and narrowly scoped hook access require security review; do not expose
   Auth tables or introduce invitation administration/profile linking.
5. Test signatures, expiry, replay, cross-user attempts, scanners, redirects, secret-free
   logs, rate limits, SMTP/API delivery failure and recovery before activation. Keep the
   current manual field until the replacement passes mocked and approved live tests.

HTTP hooks have a five-second execution budget. A sleeping Free Render service can take
about a minute to wake, so a synchronous hook hosted there is not a reliable default.
Investigate a narrowly scoped Supabase Edge Function in the existing project's Free
allowance, including secure private-storage access and measured cold-start/delivery
latency, before selecting its runtime. Do not upgrade Render or rely on keep-alive pings.
No new function, hook, storage, permission or credential has been created.
[Hook timeout](https://supabase.com/docs/guides/auth/auth-hooks),
[Render sleep behavior](https://render.com/docs/free),
[Supabase allowances](https://supabase.com/pricing).

For later invitations to other approved testers, Resend requires an owned, verified
sender domain. The application itself can continue using its existing Render URL.
A domain-free mailbox SMTP alternative requires an eligible mailbox, two-step
verification and a dedicated app password where supported; it grants access to the
mailbox and does not by itself implement the opaque-ticket handoff. It is not preferred
over a sending-only provider credential.
[Google app-password prerequisites](https://support.google.com/accounts/answer/185833).
Brevo Free was also researched, but its current sender guidance requires authentication
and warns about free-address deliverability; no reliable no-domain authentication-email
setup was verified, so do not present it as ready to configure.
[Brevo sender requirements](https://help.brevo.com/hc/en-us/articles/115000188150-Troubleshooting-Issues-with-Brevo-SMTP).

At the investigation checkpoint, no provider selection/configuration was approved. The current verified,
genuinely invited test account must be retained: after an approved replacement, a controlled
password-setup/recovery email may complete its activation without deletion/recreation.
No such email was sent or password operation performed during this investigation.
Live acceptance remains paused; stop within Phase 12B.

## Owner-only password bootstrap exception — 5 October 2026

The owner replaced the email-hook implementation proposal with a controlled password
login path for the existing Supabase Auth account. No Resend account, SMTP provider,
email hook or paid service was configured. No account was recreated or password changed.
Earlier invitation-only statements above describe the preceding checkpoints; this
section records the current explicitly approved exception.

### Identity and authorization boundaries

- `ACCOUNT_INVITED_IDS` remains the exact server-side authorized UUID allowlist, with
  its existing deployment name preserved. It is not an email/domain/organization-role
  allowlist. No approved IDs were added or changed in this task.
- New `ACCOUNT_OWNER_BOOTSTRAP_IDS` defaults empty and accepts exactly one canonical
  UUID already in `ACCOUNT_INVITED_IDS`. Invalid or outside-list configuration fails
  closed without printing its value, including when authentication is disabled.
- Only that explicit owner UUID may use existing password login without `invited_at`
  or prior `account_beta_members` activation. Supabase organization ownership alone
  never grants application access. The account must exist in the same Auth project.
- The existing password grant, trusted provider `/user` validation, narrowed signed
  claims, exact UUID/email match, confirmed-email timestamp and live Auth-session
  membership remain mandatory. Public signup stays disabled and Confirm email stays
  enabled; provider policy drift blocks authentication. No registration route was added.
- The normal invitation endpoint always requires a genuine invitation, even for the
  owner. Other authorized testers still require both a valid invitation timestamp and
  completed invitation activation before password login. Non-allowlisted users fail.
- Owner bootstrap creates only the usual encrypted account session; it does not insert
  a beta-membership row, grant an admin role or assign a learner. Removing the exception
  reinstates normal prerequisites for existing ready sessions and new login attempts.
- Staging access, exact Origin/CSRF, rate limits, private errors, encrypted server tokens,
  Secure/HttpOnly/SameSite cookies, refresh identity/session checks, 7-day absolute and
  24-hour idle limits and browser logout remain. No profile linking or Phase 12C work.

Owner flow: existing Supabase Auth email/password → provider verification → exact
allowlist/owner checks → encrypted GoiGrow ready session. `/auth/sign-in` shows email
and password only; neither its guidance nor login errors require pasting an invitation
link. The separate invitation/recovery screens remain for the documented future path.

### Read-only current-account prerequisite check

The existing authorized connection was used in read-only mode on the verified project.
Only booleans were returned; no password hash, UUID, email or credential was printed.

| Check | Result |
| --- | --- |
| Correct Supabase project | true |
| Exactly one existing controlled account | true |
| UUID matches the previously verified replacement account | true |
| `email_confirmed_at` present | true |
| `encrypted_password` present | true |

This establishes that the preserved account already has a password and confirmed email;
it does not prove a particular password supplied by the owner will succeed. No password
was requested, inspected or tested against the live provider. No recreation/password
setup is needed based on this check. If the owner cannot sign in with their known password,
stop for an owner-controlled recovery/dashboard decision; do not change Auth tables,
disable email confirmation, delete users or automate a password change.

### Configuration and release checkpoint

After reviewed deployment of this change, the owner privately sets
`ACCOUNT_OWNER_BOOTSTRAP_IDS` in the existing Render service to the **same existing
controlled owner UUID already approved in `ACCOUNT_INVITED_IDS`**. Copy it from the
matching Supabase Authentication → Users detail, verifying the account privately;
do not change the original allowlist or paste its value into chat/Git. Preserve
`ACCOUNT_AUTH_ENABLED` at its owner-selected value. It remains false locally; the
previous live enabled deployment was not changed by this task. The new setting does
not toggle the feature. Leave Allow new users to sign up off and Confirm email on.

The implementation is local only at this checkpoint: no push/deployment, Render setting
change or live login/email test was performed. Owner configuration and controlled live
login/logout acceptance are pending. Safari/PWA sign in independently; neither restores
legacy learning profiles through this account path.

### Verification and files

- Focused offline backend suite: **154 passed, 1 skipped** (the opt-in disposable
  PostgreSQL test was skipped because `TEST_POSTGRES_URL` was not configured).
- Full frontend suite: **165 passed**, including **10 account UI checks**.
  No real provider requests or emails in tests. Final diff formatting check passed.
- Tests cover owner login without invitation/membership, wrong passwords, unconfirmed
  email, signature/identity/email/UUID rejection, missing provider sessions, refresh
  identity changes, owner deselection, policy drift, staging/Origin/CSRF protections,
  no registration, private configuration errors and retained non-owner invitation flow.
- Existing learner records remain unchanged in the owner-login fixture; the ready
  account still reports `linking_pending`. Live database inspection performed no writes.
- Changed account service/configuration, sign-in UI and its settings entry copy, `.env.example`,
  README, account backend/UI tests and this report. No actual `.env`, credentials,
  migrations, learning algorithms, unrelated design files or deployment flags changed.

Stop within Phase 12B. Live acceptance remains unverified; do not mark this phase complete.


## Owner configuration and release verification — 6 October 2026

The owner confirmed saving ACCOUNT_OWNER_BOOTSTRAP_IDS as the same single authorized
UUID in ACCOUNT_INVITED_IDS, with ACCOUNT_AUTH_ENABLED unchanged. Values were entered
privately into Render; no allowlist/feature flag was edited by the agent.

Initial read-only checks found a release mismatch: GitHub main was still at 4f8bc0e
and the live sign-in HTML/account script lacked the owner-bootstrap copy. The completed
owner-bootstrap patch remained uncommitted locally, so the owner's environment redeploy
had not published the implementation. The previous readiness checkpoint was therefore
not satisfied. Health was 200; unauthenticated account bootstrap was 401. Protected
responses retained no-store, no-referrer, CSP and nosniff. Account static JavaScript is
public authored code, with no user values or provider credentials; its separate static
cache policy is expected.

The tested Phase 12B patch is being published through the existing main/Render workflow,
with only its ten named tracked files staged. Existing untracked design material is
preserved. No Resend hook, SMTP change, Auth-user change, password change or Phase 12C.
The controlled owner acceptance test must wait for live patch/CI verification.

The available browser session is not signed in to Render, so private runtime environment
values cannot be independently inspected there. Owner assertions must be distinguished
from live startup/configuration evidence; no secrets or broad privileged credentials
were requested. A healthy deployment of the new code enforces canonical UUID/subset
validation, but does not alone prove the optional owner setting is nonempty.
