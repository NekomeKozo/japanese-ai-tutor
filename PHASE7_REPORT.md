# Phase 7 — Product application and UI overhaul

Status: implementation and local verification complete; live deployment acceptance and actual-phone check pending.

## UI audit and architecture

The original frontend was a small vanilla HTML/CSS/JavaScript application, served by
FastAPI. Four equal navigation buttons led to Placement, Tutor, Study, and a long
My Learning page. Placement was the default entry point. Scripts shared DOM IDs,
request helpers, structured tutor rendering, browser-stored resource IDs, and mutable
in-memory state. Separate startup paths restored placement and learner sessions.

Existing flows already supported adaptive placement, saved tutor conversations,
deterministic study planning, cached activities, answer idempotency, mastery, and due
reviews. The weaknesses were presentation and coordination: one mobile breakpoint,
fixed narrow desktop width, mixed settings/history/knowledge, no URL navigation,
repeated read requests on panel switches, resetting visible study activities, and
loading states that could briefly suggest no saved data. Native forms and live regions
were useful foundations, but focus handling, touch targets, recovery feedback, and
heading hierarchy needed attention.

The smallest safe architecture retains all existing modules and backend contracts.
`frontend/shell.js` now owns startup, hash navigation, Home, and Settings loading.
The API helper and text-only DOM renderer remain shared. Existing DOM contracts are
preserved and tested. No framework, external UI dependency, remote font, or icon library
was added. No backend endpoint, schema, learning algorithm, deployment configuration,
secret, or security middleware changed.

## Final information architecture

- Home: deterministic next action, study estimate, goal, due-review count, focus, and recent activity.
- Study: time/focus selection, saved plan, activity, feedback, next step, recap, and Return Home.
- Tutor: structured teaching responses, correction original/suggestion/why, examples, exercises and hints; compact native mode selector.
- Progress: Overview, Skills, Knowledge, and History. Placement estimates, topic status, and confidence remain distinct.
- Settings: Japanese display, tutor behavior, learning preferences; advanced profile recovery and temporary chat.
- Placement: goal, experience, adaptive placement or beginner start, uncertain results, Home.

Desktop uses a persistent sidebar. Below 960px, four primary destinations use bottom
navigation with safe-area spacing; Placement and Settings remain in the header.
Hash URLs support direct navigation and browser Back/Forward. Learner and placement restoration run concurrently; saved tutor history loads only when Tutor is opened. Unsent tutor and study
answers, settings drafts, and active study content remain in memory during navigation.
Server-saved progress restores after reload; unsent drafts do not persist across reload.

## Design and accessibility

CSS tokens define ink, muted text, calm green accent, surfaces, borders, error colors,
radii, card spacing, and minimum control height. Japanese uses system fonts. Cards,
forms, alerts, loading states and buttons share consistent rules. Technical phase labels
and prominent provider setup details were removed from learner screens.

Keyboard checks covered navigation, native selects, placement radios and submission,
study answers, tutor submission, settings, and Back/Forward. The skip link focuses main
content without changing the route. Current destinations use aria-current. Panels have
accessible labels; controls have labels; asynchronous results use status/alert regions.
Focus moves to visible page headings, new questions, activities and knowledge details.
Controls have at least 44px targets (checkbox/radio targets include their labels).
Reduced motion is explicitly respected. This is practical accessibility verification,
not a formal WCAG certification or an actual screen-reader/device audit.

## APIs and state preservation

Home only reads existing learner profile, due-review queue, active study, and activity
endpoints. It never calls a model or creates a plan on load. Its primary action follows
unfinished placement, no profile, active study, due review, then new planning.

Study navigation reuses in-memory activities and drafts. Content generation still occurs
only through the existing explicit activity-open route, with server caching. Existing
request/submission IDs and retry behavior are preserved. Progress summaries are cached
in memory between subsections and invalidated by successful learning mutations. No
learner data is cached by a service worker.

Recovery retains browser ownership enforcement. A saved profile ID is shown only in
Advanced settings and does not authorize access from another browser. Selecting another
profile keeps existing server records.

## Files changed

- `frontend/index.html`: application shell and reorganized screen structure.
- `frontend/styles.css`: shared tokens, desktop/mobile layouts, forms, teaching cards and focus states.
- `frontend/shell.js`: new startup, navigation, dashboard, Settings and onboarding coordination.
- `frontend/app.js`: friendly errors, correction styling, visible-only focus and mutation notifications.
- `frontend/assessment.js`: onboarding integration, focused questions/results and centralized startup.
- `frontend/learner.js`: Progress grouping/cache, separate Settings, recovery and removal of competing boot path.
- `frontend/study.js`: draft-preserving navigation, real progress, contextual states and recap.
- `frontend/reviews.js`: loading feedback and integration with active study.
- `frontend/mastery.js`: detail focus, loading states and friendly errors.
- `frontend/access.html`, `frontend/access.js`: matching private-alpha access screen and submission feedback.
- `tests/frontend.test.cjs`: dependency-free Node regression tests.
- `.github/workflows/tests.yml`: frontend tests alongside backend tests and syntax checks.
- `README.md`, `PHASE7_REPORT.md`: current product flow and verification record.

## Local verification — 2026-09-28

- Full pinned-environment backend suite with disposable PostgreSQL 18 on loopback:
  **419 passed**, two existing dependency deprecation warnings.
- Earlier SQLite-only run: 414 passed, five PostgreSQL tests skipped; superseded by the full run above.
- Node built-in frontend regression suite: **14 passed**. Covers DOM contracts, startup,
  next-action priority, routing, failed restoration, study/tutor/placement/settings draft
  retention, 401 handling, friendly provider errors, read-only Home, chat retry IDs,
  failed dashboard loading, and deferred conversation restoration.
- JavaScript syntax checks: passed for all frontend scripts.
- Source and available Git-history secret/private-file audit: passed.
- Browser preview used an isolated `phase7-preview.sqlite3`, fake provider and synthetic
  due-review evidence. It did not use real learner data or model quota.
- Beginner onboarding captured a goal and returned Home. Preferences retained unsaved
  changes across navigation, saved, and survived reload.
- Placement choice submission and unknown answers advanced questions; beginner completion
  showed low confidence, unassessed skills, and the non-official-JLPT limitation.
- Study generated a five-minute plan, opened cached content, retained an answer across
  Tutor navigation, graded it, completed, and restored the saved plan after reload.
- Tutor retained its draft through Study navigation and rendered structured corrections.
- Review selected an actually due synthetic item, accepted recall, showed its persisted
  next-review date, completed, and updated Home to zero due items.
- Progress separated sections and loaded real mastery/history from the disposable profile.
- Browser Back/Forward restored the correct section.

Responsive checks used viewport widths 320, 390, 430, 768, 1024 and 1366px. Windows
scrollbars reduce available content width by 15px when present. Settings, placement
choices, review activity, knowledge list/details and tutor had no page-level horizontal
overflow at these widths. Home also passed mobile/tablet/desktop checks, including 1024px. Access passed 320px.
A representative 390px Home screenshot was saved as a task artifact. No browser console errors were observed.

## Live acceptance checklist

Pending deployment of the Phase 7 commit, CI confirmation, and checks on the actual
Render service: access, Home CTA, placement, study, due review, tutor correction/exercise,
Progress, Settings, persistence, unauthorized access and scope enforcement.

The owner chose to test on an actual phone later (2026-09-28), so this acceptance item remains pending. Actual-phone verification remains owner-assisted: open the deployed site on a phone,
use bottom navigation, type Japanese with the on-screen keyboard, send a message, submit
a study/review answer, and confirm Settings and Progress remain usable without horizontal
scrolling. Desktop viewport emulation does not substitute for this check.

## Deliberate limits

PWA installation, service worker, offline data caching and dark mode are deferred. The
core online learning experience takes priority, and no offline AI behavior is implied.
The offline notice describes the need to reconnect. No RAG, reference ingestion,
embeddings, speech, accounts, subscriptions or Phase 7.5 work is included.

## Rollback

Pre-Phase-7 checkpoint: `dfea4e6` (Phase 6.5 private-alpha acceptance). Changes are limited
to frontend, tests, CI and documentation. Use a normal revert commit for Phase 7 commits
or Render's rollback to the verified prior deployment. Do not reset/force-push history
or delete learner data. There are no new database migrations to reverse.
