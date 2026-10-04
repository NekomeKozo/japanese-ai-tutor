# Phase 11G — GoiGrow PWA foundation

## Inspection and scope
Started on clean tracked `main` at 80402da, with Phase 11F implementation 568c359 present. Read its report and inspected static routing, caching/security headers, access protection, existing branding and representative original iPhone 13 screenshots. Existing untracked design references were preserved and excluded from staging. No database, provider, authentication, learning algorithm or infrastructure changes.

## Installation
Manifest at `/manifest.webmanifest`: GoiGrow — Japanese Tutor; short name GoiGrow; description “A little, every day. Your Japanese learning companion.”; id/scope `/`; start URL `/#home`; standalone; any orientation; English; green #285d4e and existing background #f5f6f1. Served with the manifest content type and no-store.

Reused the existing white あ brand mark. PNGs: 192, 512, maskable 512 with central padding, Apple Touch 180, favicon 32 and ICO. Reproducible local glyph generator in scripts/generate_pwa_icons.ps1; no downloaded artwork. Both app and access page include installation metadata. Existing viewport-fit, safe-area bottom navigation and mobile layout remain; installed mobile header/access spacing also honors the top inset.

Settings has optional installation guidance. Chromium's button appears only after a real beforeinstallprompt; explicit click opens its prompt. Accepted prompt alone does not claim installation. Installed/standalone sessions hide the entry. Safari instructions use Share → Add to Home Screen, with Open as Web App if shown. No repeated prompts or onboarding changes.

## Worker, privacy and updates
Root `/service-worker.js`, explicit scope `/`, updateViaCache none, no-store. Registration runs once after window load on supported secure browsers. CSP explicitly permits same-origin worker/manifest, retaining existing protections.

Exact versioned precache: `/offline?v=VERSION`, `/static/pwa/offline.css?v=VERSION`, `/static/pwa/icon-192.png?v=VERSION`. Only these three public resources are written. Anonymous requests use redirect:error and SHA-256 integrity checks; invalid/cookie/redirect/error responses fail closed. Their server routes never set cookies. Fetch hides Set-Cookie in browsers, so security also relies on the exact public routes and authored-body integrity.

Authenticated app HTML, APIs, profiles, queues/submissions, conversations/history, credentials, private references, audio/transcripts and core frontend scripts/catalog are never worker-cached. Non-GET, cross-origin, authorization/range requests bypass it. Public exceptions in the staging gate are exact GET/HEAD paths, not a folder wildcard. Navigation to root/access always reaches the server and preserves redirects/errors. Network failure alone returns generic public 503 offline help. No learner storage, automatic review retry, background sync or fabricated save.

Content-derived 20-character cache version. Activation deletes only obsolete goigrow-public-v1 caches. No skipWaiting, clients.claim, auto-reload or polling. A waiting update gives unobtrusive guidance: finish activity, close all GoiGrow tabs/app windows and reopen. HTML and worker remain network-fresh; existing Phase 11F versioned browser asset caching/gzip remain.

## Verification
Baseline: 139 frontend tests and 40 relevant backend tests passed. Final focused coverage: 145 frontend + 8 worker tests passed; 148 relevant backend tests passed, 4 optional skips. After fixing offline retry navigation, two PWA backend tests and eight worker tests passed again. CI includes all tests/*.test.cjs. Syntax and whitespace checks passed.

Real desktop Edge: manifest install eligibility produced the Add GoiGrow button; registration/three-asset precache reached ready. Disposable local learner: Free Practice reveal and server-backed Due Reviews worked. Stopped only the local server: failed rating remained 0 completed / 4 remaining, with explicit retry. Reload produced generic offline page. A plain GET retry form corrected a discovered fragment-only navigation problem and reconnected successfully; no ratings replayed. Changed build: waiting update notice appeared without forced reload, and closing/reopening adopted the new worker. Settings had no horizontal overflow at 320/390/430/768/1440 widths. Original phone screenshots untouched.

Initial compressed frontend resources approximately 58.5 KB versus Phase 11F 57.4 KB (+1.1 KB); one small deferred script, no dependency/polling. Three public offline assets approximately 8.5 KB, fetched after load. Repeat versioned browser responses remain bodyless 304. Local measurements are not production Core Web Vitals.

## Deployment and limitations
Existing main → Render auto-deploy workflow; live HTTPS verification recorded below after release. Browser automation verifies installation eligibility but cannot operate the native installation dialog/standalone app window. Actual installed desktop/Android display remains an owner acceptance check; no claim that emulation is a physical device. Learning requires internet. Browser storage/worker availability may be restricted or evicted; ordinary online usage remains supported. Installed browser contexts may require sign-in/profile recovery separately.

## Physical iPhone 13 checklist — pending owner acceptance
Owner agreed to test after deployment. In Safari open the existing live origin, Share → Add to Home Screen → Add (Open as Web App if offered). Launch icon; check name/icon, standalone display, notch/top spacing, bottom navigation, Tutor/Progress and Study/Flashcards. Reveal/rate online, then disable connectivity: failed rating must not count as saved; reloading shows generic offline help. Reconnect and press Try again; progress must not replay automatically. After a later update, finish work and close all app windows/tabs before reopening. Keep access codes private.

## Files and handover
Changed app/main.py, safeguards.py, web_assets.py; frontend/index.html, access.html, styles.css; added pwa.js, service-worker.js, pwa icons/offline files; icon generator; focused Python/Node tests, frontend test harness, performance resource count and CI Node test glob. This report records Phase 11G only. No Phase 11H work; wait for explicit approval.

Platform references: [MDN installability](https://developer.mozilla.org/en-US/docs/Web/Progressive_web_apps/Guides/Making_PWAs_installable), [MDN worker lifecycle](https://developer.mozilla.org/en-US/docs/Web/API/Service_Worker_API/Using_Service_Workers), [Apple iPhone web apps](https://support.apple.com/guide/iphone/open-as-web-app-iphea86e5236/27/ios/27).
