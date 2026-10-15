# Phase 12C — Secure learner-account linking and restoration

Date: 13 October 2026; Gate 1 publication authorized 15 October 2026. **The owner selected Candidate A after a read-only historical review and approved the tested checkpoint-bound exception. Gate 1 now permits publication/CI/live verification only, with learner linking disabled. Migration, checkpoint provisioning, switch activation and the production ownership association remain separately gated. Phase 12C is not complete in production. Stop before Phase 12D.**

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
- The original unexpired HMAC-signed staging capability, bound to that account session, and exactly one existing learner joined through server-owned staging_resources rows. The separately reviewed Candidate A exception below additionally requires its private, exact checkpoint; it does not change ordinary selection.
- A separate explicit same-origin, CSRF-protected confirmation.

The signed capability is an existing server-validated authorization credential, not the fact of using a browser or knowing the shared code. Entering the code in a fresh browser creates a different capability and does not recover or claim the old learner. Matching email, IP, display name, localStorage or a frontend UUID never selects ownership.

A lost capability, missing learner or multiple eligible legacy profiles fails safely for owner-assisted verification. This implementation does not add an arbitrary-ID administrator claim endpoint, guess a preferred profile, merge profiles, or bypass a missing proof. A multiple-profile context requires the separately verified owner checkpoint described below.

## Schema and planned migration

One additive table: tutor_private.account_learner_links. PostgreSQL account_id is a UUID primary key referencing auth.users(id); learner_id is the existing TEXT unique learner key referencing learner_state. Both foreign keys restrict deletion. The remaining columns record creation time, association version 1, one of two fixed proof methods (ordinary or checkpoint-bound), keyed pseudonymous legacy/provider-session references and a digest of the encrypted confirmation. No credentials, raw signed capability, password, email or provider token are duplicated into this table.

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
    proof_method TEXT NOT NULL CHECK(proof_method IN ('signed_legacy_owner_v1','checkpoint_legacy_owner_v1')),
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


## 15 October 2026 — approved rollout stopped on ambiguous original context

The owner confirmed a current private application database backup and the existing session-encryption key backup, and explicitly approved publishing the tested Phase 12C implementation and applying only its reviewed additive migration. Final production ownership linking remains separately unapproved.

The canonical checkout remains on phase12c-secure-linking at local commit 48b908e. Remote main and Render Live remain on the existing Phase 12B owner-bootstrap commit. Existing Phase 12B notes and unrelated design files remain untouched. No commit was pushed and no deployment was triggered.

Read-only Render inspection confirmed ACCOUNT_AUTH_ENABLED remains true. ACCOUNT_LEARNER_LINKING_ENABLED is absent from the service configuration with no linked environment group or secret file overriding it, so the reviewed implementation would use its false default. No setting was edited or saved.

The existing in-app browser context successfully loaded its saved production Home and Settings through the legacy server authorization checks. The selected original profile was privately bound by a digest for the read-only inspection; no account/learner identifier, signed capability or token is recorded here.

A PostgreSQL transaction explicitly confirmed READ ONLY on the correct configured Supabase project. Its results were:

| Check | Outcome |
| --- | --- |
| Correct project connection | true |
| Exact previously approved owner account present | true |
| Owner email confirmed | true |
| Owner account active | true |
| Original browser-authorized profile present | true |
| Exactly one eligible learner under that legacy capability | false |
| Original legacy context ambiguous | true |
| Original legacy context missing | false |
| account_learner_links absent | true |
| Existing role can reference auth.users(id) | true |

The eligible learner set was derived from the same server-owned learner_state/staging_resources relationship used by the reviewed linking service. It contains more than one candidate. The browser's current selection alone must not resolve that ambiguity or serve as ownership proof.

**Stop condition reached:** no publication, CI run, deployment, migration, rollout-switch change or ownership insertion was performed. Existing learner/history rows were not modified; saved progress remains accessible. A full before/after migration comparison was not applicable because no migration ran. No claim is made that a single target has been verified or that a link-preview confirmation is ready.

At this historical stop, the next step required a separate, narrowly scoped owner-assisted review to distinguish the legitimate original profile using non-secret historical evidence and a deliberate server-verifiable selection checkpoint. The following preparation records that subsequent review. Final publication, migration, switch activation and ownership linking still require separate explicit approval.

## Candidate A identification and second read-only verification — 15 October 2026

The owner reviewed anonymized historical summaries and explicitly selected Candidate A. Its recognizable markers included an Early N5 estimate, completed placement, Travel goal and saved learning activity. No browser-selected learner, frontend identifier, profile ordering, recent activity guess or email match established ownership.

The second review used the existing authorized connection to the correct Supabase project in two fresh, explicitly READ ONLY, repeatable-read transactions. It independently rechecked the previously approved owner binding, confirmed active/confirmed account state, the original server-recorded legacy context and the exact eligible candidate set. Candidate A remained in that set; the owner and selected learner were unlinked, with no conflicts. Candidate A's content fingerprints across 22 learner/history tables matched the original review. Fresh before/after snapshots also confirmed no learner/history/timestamp or account-session state changes during that verification. No association table, migration or link was created.

The owner selection was HMAC-bound to the original review, approved account state, legacy context, exact eligible set, Candidate A digest and full history digest. This private backend/tool-side checkpoint remains outside Git. It is not a production database record or a substitute for a current authenticated account session. Its signature and original-review binding were checked offline again during implementation; both matched. No private identifier, key, email, capability or checkpoint payload is recorded here.

## Checkpoint-bound exception — preparation only

The normal path is unchanged: exactly one eligible learner permits preview; multiple learners reject. The optional exception consumes only the independently reviewed Candidate A checkpoint. It cannot discover, choose or approve a different candidate. There is no learner picker, new claim endpoint, transfer, merge, deletion or replacement-profile operation.

`scripts/prepare_account_link_checkpoint.py` is an offline operator utility, not an API. It requires both original review evidence and the second-verification selection, validates their version, signature, exact review hash and selected history binding, and requires the exact existing bootstrap owner already in the authorized account allowlist. Evidence must be less than 24 hours old; it never silently renews historical verification. The resulting envelope uses the existing session-encryption key ring, expires after at most one hour, and includes a versioned purpose. It cannot overwrite an existing artifact and will not write inside the checkout. It never connects to the database or provider. This preparation did **not** seal a production envelope, upload a secret file, change an environment variable or enable linking.

`ACCOUNT_LEARNER_CHECKPOINT_PATH` defaults empty. A future separately approved deployment may point it to an encrypted private server file outside the checkout/static paths. Runtime rejects missing, oversized, altered, expired, wrongly versioned or mismatched evidence; it reloads the file on preview and confirmation. A bad configured checkpoint never falls back to the ordinary path. Removing or replacing it also invalidates a pending checkpoint confirmation.

At runtime the account must remain exactly allowlisted, bootstrap-approved, confirmed and active. A valid ready account session, provider identity/session, current signup policy, fresh sign-in within ten minutes and the original signed legacy capability remain mandatory. The server derives the learner exclusively by matching the private checkpoint digest against the current server-owned eligible set. It compares the complete eligible-set digest, selected learner's 22-table history fingerprint and reviewed Auth state, and rejects new associations elsewhere in that eligible set. It never accepts an account, learner or candidate selector from the browser.

Preview acquires the existing learner-operation advisory lock, revalidates the ready/provider session and integrity evidence, and returns only the existing safe level/source summary with “Verified existing learning profile” plus an encrypted, five-minute confirmation. It creates no ownership link. Existing account-session refresh/touch behavior is retained; learner/history rows and timestamps are not rewritten. The opaque confirmation remains in page memory, never public URLs or browser storage.

Final confirmation still requires explicit literal consent, exact same Origin and CSRF protection. In the final transaction it repeats account/provider/session/freshness validation after acquiring the learner lock, holds Auth user/session shared row locks, reloads the exact checkpoint, rechecks context/set/history and both ownership directions, then inserts only the association. The planned additive DDL now permits the fixed `checkpoint_legacy_owner_v1` proof method alongside the original method. No production schema was altered. An identical retry succeeds only for the same account, learner, proof method and exact confirmation digest while the checkpoint and confirmation remain valid. Changed ownership, other proofs or changed history fail safely.

The Auth shared-row locks require the existing role's read/row-lock permissions; no grant or privileged credential is introduced. Before any approved rollout, inspect those existing privileges read-only and stop if unavailable. Never change Supabase-managed rows to make a checkpoint pass.

## Isolated checkpoint verification

Final focused backend security/linking regression: **234 passed**, no skips, including **37 new checkpoint tests**. This ran the account, account-authentication, staging, existing linking and new checkpoint modules against SQLite/disposable loopback PostgreSQL with mocked providers. The two existing FastAPI/Starlette/AnyIO deprecation warnings remain. Full frontend suite: **177 passed**, no skips, including the new verified-profile description/opaque-confirmation check. Source and all available Git-history secret audit passed; Git whitespace checks passed. The earlier 783-test full-backend baseline is recorded above; the whole backend suite was not repeated for this scoped preparation.

All new tests use generated identities, mocked Supabase responses and disposable loopback PostgreSQL databases. Production credentials, private checkpoints and real accounts are not test fixtures. Candidate A-only resolution, B/C exclusion, history preservation and ordinary multiple-candidate rejection all passed. Initial test-fixture issues (alternate mock identity, timestamp precision and cleanup scope) were corrected before the final clean run; no production security control was relaxed.

Coverage includes correct preview/A-only resolution; arbitrary browser IDs and Candidate B/C selectors; encrypted proofs pointing at B/C; modified/missing/replaced/expired checkpoints; stale evidence; wrong owner; changed eligible set; removal of A; ownership conflicts for A, owner or another candidate; changed history/Auth metadata; stale account and legacy sessions; unconfirmed email; revoked provider session; provider-policy drift; disabled linking; CSRF/Origin/cross-site rejection; session-bound replay; expired confirmation; concurrent identical final attempts; idempotent retry; default multiple-profile rejection; offline artifact preparation and overwrite prevention.

Preservation verification includes populated placement, study, Tutor conversations/turns, vocabulary/grammar/kanji mastery, flashcard/spaced reviews, JLPT, listening and speaking records. It compares complete fixture learner/history rows before and after linking and independent account restoration, not just counts of empty tables. Candidate B and C cannot be linked through the exception or accessed as the linked account's learning profile.

Files changed for this preparation: `app/account_link_checkpoint.py`, `app/account_links.py`, `app/account_link_migration.py`, `app/config.py`, `scripts/prepare_account_link_checkpoint.py`, `frontend/account.js`, `tests/test_account_link_checkpoint.py`, `tests/accounts-ui.test.cjs`, `.env.example`, and this report. Existing Phase 12B notes and untracked design files remain untouched and excluded. Work remains on `phase12c-secure-linking`; nothing was committed, pushed or published in this preparation.

## Remaining production approval gates

1. Separate approval to publish the reviewed/tested implementation through existing main/Render workflow, keeping linking disabled; verify CI and Live without changing the authentication flag or account allowlists.
2. Separate approval for the revised, additive association-table migration after backup, existing-role privilege checks and fresh read-only integrity comparison. Stop on any changed schema, role limitation or mismatch; verify existing learner/history rows remain unchanged afterward.
3. Separate approval to provision the private short-lived checkpoint and enable linking for the controlled owner preview. Recheck the original owner/browser capability and exact selected evidence first. Expired evidence needs a fresh read-only verification; changed history or context needs a new owner review, never automatic reselection.
4. Show the safe server-resolved Candidate A preview and obtain separate final explicit approval for the real production association. Until then, do not submit confirmation or create a link. After confirmation, verify the single intended association and unchanged history.

No production connection, Auth user change, Render change, migration, linking activation or association occurred during this preparation. Phase 12D and email/SMTP/recovery work remain out of scope.

## Production Gate 1 — publication-only authorization, 15 October 2026

The owner explicitly approved publishing only the reviewed Phase 12C implementation through the existing main/Render workflow. The existing Phase 12B notes and unrelated untracked design files must remain excluded. The authentication flag, exact account allowlists, Auth users and learner/history data are outside this approval. No migration, association table, Candidate A checkpoint file, real Candidate A preview or association may be created.

Before publication, remote main and Render Live both matched the existing Phase 12B owner-bootstrap commit. Read-only Render inspection showed account authentication, staging access and scope enforcement enabled. The learner-linking flag and checkpoint path were absent, retaining their false/empty defaults. No linked environment groups or secret-file overrides were present. Only the three non-secret boolean flags were briefly revealed and rehidden; no setting was edited. The existing owner account session remained ready and email-verified before publication.

Publication preflight rerun: **234 focused backend security/linking tests passed**, **177 frontend tests passed**, no skips; the same two existing deprecation warnings remain. The source/available-Git-history secret audit and whitespace checks passed. Only the ten reviewed preparation files were staged. Publication verification results will be appended after the exact commit passes CI and is confirmed Live. Gate 2 (the additive association migration) is not authorized.
