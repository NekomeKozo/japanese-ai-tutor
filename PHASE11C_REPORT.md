# Phase 11C — Shared component consistency

## Audit and inventory

Starting checkpoint: `main` / `20d1d90`; tracked working tree clean, Phase 11B implementation/report present. Existing `design/` references were untracked and preserved. Inspected discovery, concept mockup and all ten owner-supplied iPhone 13 Safari captures. The mockup remains inspiration; the deployed green/cream layout is the functional baseline.

| Component family | Existing shared pattern / treatment |
|---|---|
| Shell, headers, navigation | Existing sidebar/bottom bar, page header, aria-current and focus ring retained; shared tab hover/pressed states |
| Buttons and actions | Primary/secondary buttons and button links share sizing, padding, weight, hover and pressed treatment; outline secondary emphasis retained |
| Cards and Tutor messages | Existing placement/activity cards keep shared border/radius/padding; hero border aligned; distinct message surfaces tokenized |
| Forms and choices | Existing native inputs/selects/textareas retain validation; shared control border/disabled state; JLPT and other choice rows share styling |
| Progress and badges | Existing native progress, tables and statistic layout retained; pill radius reused |
| Feedback and recovery | Existing alert presentation retained; audio errors use its colour; nonempty Study/Listening/Settings/recovery feedback shares notice styling |
| Audio and transcripts | Existing reusable player/recorder/editor retained; audio buttons inherit common minimum height; recording indicator remains distinct |
| Loading and empty states | Existing announcements, muted loading and honest empty guidance retained; no fabricated data or extra requests |

## Changes

Only functional source changed: `frontend/styles.css`. Added semantic control-border, on-accent, pill/message radius and conversation/learner/correction surface tokens using existing values. Removed separate JLPT palette/border/choice definitions and the audio button height override. Shared buttons now distinguish secondary pressed states; disabled forms match disabled actions. Card geometry, Phase 11B breakpoints/safe areas/short-height navigation, DOM IDs and controllers remain intact. No dependencies, JavaScript, backend, routes, provider, authentication or learning changes.

## iPhone references and visual comparison

Originals in `design/screenshots/Iphone 13/` are preserved and excluded from this commit. Names below abbreviate `ChatGPT Image Oct 4, 2026, … AM.png`. New captures are in [phase11c](design/screenshots/phase11c/), with **mobile-emulated** in their names. They use disposable local learner data and mocked microphone/STT; no owner profile, credentials or real recordings are included.

| Original suffix / state | Updated capture / finding |
|---|---|
| `02_51_19` — Progress History | `progress-history-mobile-emulated-after.jpg`: same card hierarchy, active History and Resume; shared tab control sizing |
| `02_51_36` — Knowledge filters/list | `progress-knowledge-mobile-emulated-after.jpg`: same stacked filters, unknown evidence and topic controls |
| `02_51_44` — Skills | `progress-skills-mobile-emulated-after.jpg`: same explanatory card and wrapping table |
| `02_51_51` — Overview loading audio | `progress-overview-mobile-emulated-after.jpg`: loaded empty audio state rather than reproducing a transient loading capture |
| `02_51_58` — expanded recorder | `tutor-recording-mobile-emulated-after.jpg`: disclosure and prominent Record preserved; controls share common styling |
| `02_52_07` — Tutor TTS/voice picker | `tutor-audio-mobile-emulated-after.jpg` and transcript captures retain the player/editor family; native Safari Kyoko picker differs from desktop browsers and is not recreated |
| `02_52_11`, `02_52_18` — conversation setup/Tutor header | `tutor-mobile-emulated-after.jpg`: same scenario/corrections controls, header action and active Tutor navigation |
| `02_52_22`, `02_52_27` — Study setup/reviews/tabs | `study-mobile-emulated-after.jpg`: same two-column Study links and review hierarchy; active links now use the common accent |

Additional captures: Home, JLPT feedback, editable transcript, and representative 1440px desktop Home/Tutor. Mobile captures are 390×844 browser viewports, not new physical-device tests. Compared with originals, density/hierarchy remain familiar. Remaining differences are browser fonts/native controls, scrollbar/browser chrome, capture scroll position and disposable learner state. These are qualitative comparisons, not pixel-identical Safari baselines. Original screenshots show no Home state; Home also compared against the existing desktop discovery/Phase 11B baseline.

## Verification

- Frontend baseline and final: **110 passed**; navigation, drafts, recovery/loading, Tutor, JLPT and audio lifecycle coverage retained.
- Browser measurements: **108 checks** across 12 existing views at **320, 360, 390, 430, 768, 1024, 1280, 1440, 1920px**; no horizontal document overflow or visible buttons below 44×44 CSS pixels. Measurements saved in `responsive-emulated.json`.
- Local UI: Study plan/activity interaction; correct JLPT answer saved; mock recording → Stop → Transcribe → edit → Confirm copied Japanese to the composer without sending. Tutor draft retained across navigation. JLPT selected choice uses shared soft/accent colours and 10px radius, with height above 52px.
- Desktop Home/Tutor visually checked at 1440px: sidebar, centering, card hierarchy and spacing preserved. Existing responsive matrix includes large-monitor views.
- Backend tests not rerun locally: no functional code changed. No live AI/STT calls required.
- Deployment/CI verification pending final checkpoint.

## Limitations and handover

Reviewed real iPhone 13 screenshots supplied by the owner; conducted no new physical phone, microphone or on-screen-keyboard test. Browser emulation cannot certify Safari keyboard or native voice-picker behaviour. Existing accessibility semantics/focus announcements are preserved. Captures show representative states, not every possible content length or transient network failure.

Phase 11C only. Phase 11D may reuse these lightweight tokens and existing cards/forms, but flashcards, scoring and new features require explicit authorization. No Phase 11D work started.
