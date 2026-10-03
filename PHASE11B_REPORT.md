# Phase 11B — Mobile UI/UX refinement

## Baseline and audit

Canonical checkout: `main`, starting at `0906ad9`; tracked working tree was clean. Latest Phase 10G changes (`4e88516`) were present and remote main matched. No completed Phase 11A desktop implementation/report was present. This discrepancy was reported before edits; the user explicitly authorized Phase 11B using the deployed desktop layout as the functional baseline.

Inspected `design/PHASE11_DESIGN_DISCOVERY.md`, original screenshots and `design/mockups/goigrow-concept-v01.png`. These were untracked and are preserved without overwriting or staging. The supplied concept depicts a purple Kioki flashcard dashboard: inspiration only, not evidence of implemented GoiGrow features. Existing green/cream branding, tokens and navigation remain authoritative. Practice remains within Study; no new route or flashcards.

## Findings and changes

Mobile Home spacing and large headings consumed unnecessary space; Study links lacked a balanced narrow layout; chat height/composer, transcript actions and mastery filters needed better stacking. Fixed navigation needed a short-height fallback for landscape/keyboard-sized viewports.

- Compact Home spacing, natural-height cards and prominent full-width primary action.
- Two-column Study navigation, improved Japanese passage wrapping/line spacing and answer alignment.
- Dynamic mobile conversation height, full-width Send, larger transcript editor and wrapping recording/pagination actions.
- Stacked mastery filters and fixed-layout tables with wrapping cells.
- Safe-area-aware header/navigation/access spacing and visible pressed states.
- Short-height mobile navigation enters normal page flow, avoiding a fixed overlay on essential controls.
- Both viewport tags allow safe-area coverage and request content resizing for supporting virtual keyboards, without disabling zoom.

Files: `frontend/styles.css`, `frontend/index.html`, `frontend/access.html`, this report. All added CSS is limited to widths below 960px; desktop tokens/rules and JavaScript controllers are unchanged. No dependencies, backend, data, authentication, provider or learning changes.

## Verification

- Frontend baseline and final run: **110 tests passed**.
- Focused API, staging, JLPT, conversation, speech and audio-progress regression: **187 passed, 12 skipped** (separate PostgreSQL-service cases); two existing dependency deprecation warnings.
- Windows Edge browser checks: nine existing application views across **320, 360, 375, 390, 430, 768, 1024, 1280, 1440, 1920px**. All 90 checks had no horizontal document overflow and visible buttons at least 44×44 CSS pixels.
- Access form checked at all ten widths: no overflow, 16px input text, submit height above 44px.
- Supplemental active Listening/transcript at 320px and landscape 844×390: no overflow; landscape navigation in page flow. Tutor at 390×420: Send reachable and navigation static.
- Disposable local learner: completed a Study answer, JLPT practice/results/review, speaking recording/preview/transcription/edit/confirmation and voice conversation turn. Audio capture and providers were mocked; native browser preview/decoding used. No real recordings transmitted.
- Long Japanese Tutor draft survived navigation; Settings save succeeded. Existing frontend tests cover restoration and recording cleanup.
- Desktop sidebar, Home grid and spacing visually checked at 1440px; all existing views included in the larger-width matrix. Desktop CSS unchanged.

Deployment and CI: pending checkpoint below.

## Physical devices and limitations

The user agreed to test after deployment. **Actual Android/iPhone, on-screen keyboard, browser bars and physical microphone verification remain pending.** Desktop Edge viewport resizing is not a device test. Browsers may differ in support for `interactive-widget`; native phone confirmation remains necessary. Guidance: [MDN viewport documentation](https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Elements/meta/name/viewport).

## Handover

Phase 11B only. Preserve the current desktop baseline and existing discovery work. A shared-component cleanup belongs to Phase 11C and requires explicit authorization. No Phase 11C work begun.
