# Phase 12C — Secure learner-account linking and restoration

Date: 13 October 2026. **Implementation and isolated verification complete; production migration, deployment and first ownership link await owner approval. Phase 12C is not yet complete in production. Stop before Phase 12D.**

## Phase 12B preflight

Started on main at fbc1a85; work is isolated on phase12c-secure-linking. Existing uncommitted Phase 12B acceptance notes and unrelated untracked design files are preserved and excluded from this checkpoint.

Read PHASE12A_AUTH_ARCHITECTURE.md, PHASE12A_REPORT.md and PHASE12B_REPORT.md. Read-only verification confirmed Render Live at the deployed owner-bootstrap patch; account authentication retains its owner-approved enabled state. The single canonical owner-bootstrap account exactly matches the authorized allowlist and the privately hashed previously approved account. The configured Supabase project matches. The approved Auth record exists, is active and has confirmed email. Public signup, anonymous login and manual provider-identity linking remain disabled; Confirm email and Email remain enabled. Staging access and scope enforcement remain enabled. All revealed dashboard values were rehidden; no setting was changed.

Account-session/beta tables exist. The association table does not yet exist in production. Existing database permissions can read the required Auth session columns and reference auth.users(id); no additional privileged credential or permission was requested. A separate PostgreSQL transaction explicitly verified READ ONLY. No production Auth, learner or learning-history record was changed. No real account session or current browser hint was assumed to prove ownership.

The controlled Phase 12B login/logout, incorrect-password denial and subsequent successful login remain owner-reported acceptance. End-to-end recovery, physical iPhone Safari account acceptance and installed-PWA account acceptance remain separately unconfirmed.

## Existing identity and ownership proof

The stable learner_state.learner_id owns the existing placement, preferences, study, mastery, review, Tutor, JLPT and audio activity history. It is distinct from the provider-verified Supabase account UUID. Browser learner/session IDs are selection hints only.

For this owner-only rollout, an eligible link requires all of:

- The existing exact owner-bootstrap UUID, still in ACCOUNT_INVITED_IDS.
- A ready server-side account session: verified password login, provider identity/signature, confirmed email, active provider session, application expiry/idle limits and current provider signup policy.
- A fresh account sign-in within ten minutes.
- The original unexpired HMAC-signed staging capability, bound to that account session, and exactly one existing learner joined through server-owned staging_resources rows.
- A separate explicit same-origin, CSRF-protected confirmation.

The signed capability is an existing server-validated authorization credential, not the fact of using a browser or knowing the shared code. Entering the code in a fresh browser creates a different capability and does not recover or claim the old learner. Matching email, IP, display name, localStorage or a frontend UUID never selects ownership.

A lost capability, missing learner or multiple eligible legacy profiles fails safely for owner-assisted verification. This implementation does not add an arbitrary-ID administrator claim endpoint, guess a preferred profile, merge profiles, or bypass a missing proof. Such a real context is a blocker requiring a separate narrowly verified owner checkpoint.

## Schema and planned migration

One additive table: tutor_private.account_learner_links. PostgreSQL account_id is a UUID primary key referencing auth.users(id); learner_id is the existing TEXT unique learner key referencing learner_state. Both foreign keys restrict deletion. The remaining columns record creation time, association version 1, fixed proof method, keyed pseudonymous legacy/provider-session references and a digest of the encrypted confirmation. No credentials, raw signed capability, password, email or provider token are duplicated into this table.

SQLite isolated fixtures use a non-null TEXT primary account key and mocked provider identity. Disposable PostgreSQL fixtures use minimal synthetic Auth tables to test the actual foreign keys; provider-managed production tables are never recreated or edited.

The planned Supabase DDL is:

```sql
BEGIN;
SET LOCAL search_path TO tutor_private;
CREATE TABLE IF NOT EXISTS account_learner_links (
    account_id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE RESTRICT,
    learner_id TEXT UNIQUE NOT NULL REFERENCES learner_state(learner_id) ON DELETE RESTRICT,
    created_at DOUBLE PRECISION NOT NULL,
    link_version INTEGER NOT NULL CHECK(link_version=1),
    proof_method TEXT NOT NULL CHECK(proof_method='signed_legacy_owner_v1'),
    legacy_owner_digest TEXT NOT NULL,
    provider_session_digest TEXT NOT NULL,
    confirmation_digest TEXT NOT NULL UNIQUE
);
REVOKE ALL ON account_learner_links FROM PUBLIC, anon, authenticated;
COMMIT;
```

The migration utility handles absent local fixture roles safely. It does not backfill ownership, modify learner rows, rewrite historical timestamps or change the existing application schema version 8. Application startup only inspects presence; it never applies this migration. Enabling new linking without the migration refuses startup.

Operator utility, run from the repository root:

- `python scripts/migrate_account_links.py`: print the fixed plan without even loading private environment configuration or connecting.
- Add `--check`: read-only presence and prerequisite inspection; output only booleans and column names.
- Only after the production checkpoint: `--apply --owner-approved --backup-confirmed`. New linking must remain disabled during migration. All DDL commits atomically or rolls back. Do not run apply until approval.

## Linking and account resolution

ACCOUNT_LEARNER_LINKING_ENABLED defaults false, independently of ACCOUNT_AUTH_ENABLED. No real environment flag or allowlist was changed in this phase.

GET /api/account/link-preview selects the sole eligible legacy learner on the server and displays only its study estimate and profile source. It creates no association. Its five-minute encrypted confirmation is bound to the account, account-session nonce, signed legacy identity and exact server-selected learner. It remains in page memory only, never a URL or browser storage.

POST /api/account/link-learner requires literal boolean confirmation, the opaque proof, ready owner session, current policy, exact Origin and CSRF. Extra account/learner ID fields are rejected. Eligibility, freshness, existence and both ownership conflicts are rechecked in the transaction. PostgreSQL uses the same advisory lock as learner operations; SQLite holds its write lock. Database uniqueness/FKs provide additional protection. Identical retries return the existing link; conflicting requests do not overwrite it. An interrupted browser confirmation retains the same proof for an explicit retry.

GET /api/account/learner derives the primary learner from verified account identity. It returns linked/unlinked state, never a browser-selected account. The existing me response reports linked status without an account identifier.

Linked resources always require their owning verified account, even if new linking is disabled. Original legacy capability access alone ceases to authorize linked learner, placement, saved Tutor and nested resources. Authorization is rechecked inside data transactions, including application logout/expiry, to close the gap between an initial request check and a concurrent link/write. Upload ownership is checked before buffering recording data. Public catalogs and health do not acquire unnecessary remote account-verification dependencies.

Unlinked accounts are redirected to their account screen. Creating a beginner/replacement learner or replacement placement while authenticated is deliberately deferred; no automatic duplicate profile is created. No self-service unlink, transfer or merge exists.

## Restoration and frontend privacy

After independent sign-in, the application asks the server for the linked learner before reading learning data. Stale legacy hints cannot override it. Account mode keeps learner/session identifiers in runtime only; its optional persistent marker is merely a boolean sign-in hint and grants no authorization. Blocked browser storage does not prevent restoration.

Tutor restores active practice or the latest saved conversation. If no conversation exists it asks for an explicit New conversation action, without silently creating one. Restoring closed history likewise does not rewrite it. Original placement evidence remains on Progress; replacement placement and legacy ID-recovery controls are hidden for the linked account.

Account changes/logout clear private runtime state, drafts, history DOM, old hints and media/transcription state. Late account/API responses cannot reinstate the previous context. BroadcastChannel, focus/visibility revalidation and page lifecycle handling cover shared-browser cookie changes and back navigation. Valid revalidation preserves the current draft. Failed account access clears the context and requires sign-in. Auth/API responses remain no-store; service-worker caching remains restricted to its existing anonymous offline resources, with no private-response cache or synchronization.

Safari and an installed iPhone app can have separate storage/cookies. Each independently passes the staging gate and signs into the same approved account; the server relationship restores the same stable learner. No cookie, localStorage, learner ID or provider-token copying is needed.

## Verification results

- Full backend regression suite with a disposable loopback PostgreSQL 18 instance: **783 passed**, no skipped tests. Two existing FastAPI/Starlette/AnyIO deprecation warnings remain.
- Focused Phase 12C ownership/migration tests: **53 passed**, included in the full suite. SQLite and PostgreSQL cover explicit consent, invalid/expired account and legacy contexts, arbitrary-ID claims, fresh login, cross-account access, replay, conflicting ownership, identical/concurrent retries, database rollback, FK constraints, migration repeatability and independent clients.
- Frontend suite: **176 passed**. Includes explicit preview/confirm, interrupted retries/double taps, conflict states, server-selected restoration, stale hints, blocked storage, logout/account-switch clearing, late responses, focus revalidation and restoring saved Tutor history without creation/closure.
- Source and available Git-history secret/private-file audit passed. Whitespace/diff checks passed.
- Local browser visual fixture: desktop and requested 390 × 844 phone-sized viewport. Explicit confirmation, success, restored Home, Study and Settings checked; no horizontal overflow; confirm button exceeds 44px height. Study form defaults remain intact; advanced legacy ID tools are hidden. Desktop shell/theme preserved. This visual fixture uses a simulated account and disposable learner data, not a production ownership link or a physical iPhone pass.

Preservation tests seed actual placement answers/results, preferences, study plans, Tutor conversation turns/practice, vocabulary/grammar/kanji mastery evidence, review schedules/attempts, flashcard review receipts, JLPT results, listening and speaking completion events. Sorted row snapshots of every application table except account session/association metadata match before linking and after independent restoration, on both SQLite and PostgreSQL. They verify these histories are populated rather than comparing only empty tables. No interval recalculation, replacement learner, replacement conversation or history/timestamp rewrite occurs during linking/restoration.

The complete regression also preserves the existing development-only temporary-chat fallback when study storage is unavailable; production staging still refuses unavailable storage.

Local evidence (outside Git): work/phase12c under this Codex task contains backend-final.txt, frontend-final.txt, audit-final.txt and labelled simulated desktop/mobile screenshots. No production IDs or secrets are in this report.

## Changed files

- app/account_link_migration.py, scripts/migrate_account_links.py: explicit additive migration/plan/check.
- app/account_links.py, app/learner_access.py: confirmation, server relationship and transactional ownership guards.
- app/accounts.py, app/api/accounts.py: verified principal, link status and protected link/context endpoints.
- app/config.py, .env.example: separate default-off new-link rollout switch.
- app/main.py, app/safeguards.py, app/assessment/repository.py, app/storage.py: startup inspection, ownership precedence and transaction boundaries.
- app/api/learner.py, app/api/assessment.py: authenticated duplicate/replacement profile creation deferred.
- frontend/account.html, account.js, account.css, account-context.js: linking UI, restore and privacy lifecycle.
- frontend/index.html, app.js, learner.js, shell.js: boot resolution, safe requests, saved-history restore and context controls.
- tests/test_account_links.py, accounts-ui.test.cjs, frontend.test.cjs, test_web_performance.py: security, persistence, frontend and asset checks.
- README.md and this report: operational instructions and acceptance evidence.

## Backup, deployment and rollback checkpoint

No Phase 12C production deployment, migration, real association, Auth-user change or allowlist/flag change has occurred. The earlier Phase 12B backup must not be assumed current.

Before production work, confirm a current encrypted/restorable application PostgreSQL backup covering tutor_private and its learner/history tables, with existing session-encryption keys retained separately and the restore procedure available. Validate restore in a separate disposable database, never by overwriting production. Keep the approved Supabase Auth account and original signed legacy browser context intact. Pause owner learning activity for the first-link integrity snapshot/verification. Never paste backup contents, identifiers, keys or URLs into chat/Git.

After explicit approval, publish the isolated tested change through the existing workflow, keeping new linking disabled; verify CI/Live. Apply only the reviewed additive migration through the existing authorized database role, verify it, and restart the account-aware deployment before enabling the new linking switch. Do not change ACCOUNT_AUTH_ENABLED or either UUID allowlist.

Before the first actual link, freshly verify the approved owner account and the ORIGINAL browser context with saved progress. Display the server-detected eligible profile; if missing or ambiguous, stop. Obtain the owner's explicit approval of that profile and association, then confirm through the protected flow. Learning records are not modified by the association; normal account-session touch/refresh metadata is the only other intended operational change. Compare private row-count/content fingerprints without printing learner data. Stop on any discrepancy.

Rollback before any association: leave new linking false and the additive table empty; it can stay in place. Rollback after an association: turn only new linking off and retain the table AND the account-aware authorizer. Existing owners continue to restore; legacy-only access remains denied. Do not drop the association table, restore old staging-only code, unlink, transfer or merge. If no safe account-aware release can run, restrict service availability while repairing; a destructive restore requires a separate approved recovery plan.

The pending approval is for this existing approved owner only, and its unique server-verified original learner context, not every profile accessible with the staging code. That real context has not yet been inspected through the new flow, so this report does not invent a target or assert that it has already been linked.

## Physical iPhone 13 acceptance — pending after approved deployment/link

1. Desktop: independently sign in, explicitly link only the verified original profile, inspect representative original placement, saved Tutor, review/flashcard, JLPT, mastery and audio history.
2. Safari: pass the staging gate and sign in independently. Confirm the same original history/preferences without copying IDs or creating a profile.
3. Installed PWA: launch and sign in independently. Confirm the same original history/preferences. Separate Safari/PWA sessions are expected.
4. Sign out of one context. Confirm it cannot retrieve linked progress, old drafts/media/history do not reappear, and another independent session remains signed in according to the existing current-browser logout policy.
5. Check keyboard-open Tutor/Study/Settings navigation and a reconnect. No private learner response should be available offline, and no duplicate learner should be created.
6. Record the owner's actual observations; do not mark physical Safari/PWA acceptance passed in advance.

Password recovery remains a separate Phase 12B limitation. No Resend, SMTP, email-hook, public-registration or recovery redesign was added. Phase 12D is not started or authorized.
