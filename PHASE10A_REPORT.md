# GoiGrow — Phase 10A

## Audit

Started from clean `main` at `a3c3ebd` (GoiGrow branding and passing CI).
Phase 9 is accepted complete by the user. Inspected existing classic deferred-script
frontend, hash router, Study/JLPT subsections, Tutor reply/history rendering and Node
test harness. No existing TTS/audio module was found. Reused cards, buttons, forms,
Study navigation and saved Tutor replies. No repeat of the Phase 1–9 audit.

## Implementation and architecture

`audio.js` owns one browser-native speech queue. It discovers only Japanese voices
(`ja`, `ja-JP`, compatible Japanese language metadata), prefers local voices, handles
asynchronous `voiceschanged`, and shows loading/missing/unsupported/error states.
Explicit Play/replay gestures create utterances at 0.75, 1.0 or 1.25 rate. Stop,
route changes, page exit, hidden tabs, learner changes and replaced content cancel
playback. Generation guards ignore stale events; startup and playback watchdogs
recover stalled engines. Short chunks prefer sentence boundaries.

Reusable accessible controls expose voice selection, speed, Play/replay and Stop.
Pause/resume is deliberately omitted: reliable behavior across devices is not yet
validated. Stop/replay is the initial fallback. Nothing auto-speaks.

Tutor controls use only displayed reply text, corrected Japanese and examples,
including saved replies and scenario openings. A conservative Japanese-character
extractor omits English scaffolding. It does not inspect hidden DOM, RAG metadata,
internal instructions, explanations, exercise hints or learner messages. Dynamic
content uses textContent/createElement. No extra Gemini/Groq call is made.

`listening.js` contains eight original, reviewed passages: four N5 and four basic N4.
Review checked Japanese wording, level suitability, answer consistency and distractor
ambiguity; no independent teacher review is claimed. Multiple-choice correctness is
validated locally with bounds checks and one submission per question. Transcript is
empty/hidden until explicit assisted reveal or feedback. A completed summary separates
unassisted and assisted results. Practice survives route navigation in the same tab,
but reload resets it. It creates no saved evidence, mastery change or official score.

No backend/API/schema/migration/authentication/security-header changes; no microphone,
recording, uploads, paid provider, audio storage, worker or new database.

## Files changed

- Added `frontend/audio.js`, `frontend/listening.js`, this report.
- Updated `frontend/index.html`, `shell.js`, `app.js`, `learner.js`, `study.js`,
  `styles.css`, `tests/frontend.test.cjs`, `README.md`.

## Compatibility and limitations

Uses [Web Speech API](https://webaudio.github.io/web-speech-api/#tts-section) and
[SpeechSynthesis](https://developer.mozilla.org/en-US/docs/Web/API/SpeechSynthesis).
Availability of an API does not guarantee an installed Japanese voice. Missing voices
produce a helpful message and an assisted-transcript path; English voices are never
used as a fallback. OS/browser voices may process text online; localService voices
are preferred, but offline-only operation is not promised. Voice/rate selection is
tab-local. Actual sound quality, reading of names/kanji and perceived speed vary.
Mixed Latin/Japanese text is read as Japanese fragments; Latin terms are omitted.
Extremely long passages (over 12,000 characters) are rejected rather than queued.

## Verification

- 44 frontend tests passed (30 existing + 14 new): Japanese discovery/late loading,
  missing/unsupported voices, explicit playback, replay/stop, selected rates/voices,
  stale callbacks, failures/timeouts, chunk cancellation, navigation/visibility/profile
  cleanup, safe public-text extraction, zero extra requests, all bank answers,
  transcript reveal, single scoring, assisted summaries and route retention.
- JavaScript syntax and whitespace checks passed.
- Source/history deployment audit passed; no secret candidates or private files found.
- Targeted existing API/JLPT regression: 67 passed, 5 PostgreSQL-dependent checks
  skipped locally. Existing CI runs the full suite with PostgreSQL.
- Local Windows in-app browser discovered four Microsoft Japanese voices. Native
  start/end events, all three selected speeds, keyboard Play, Stop/replay and voice
  switching exercised. Completed playback permitted unassisted answer feedback.
  This validates browser events/rate settings, not an independent listening-quality
  or perceived-speed comparison.
- Desktop and emulated 390×844 / 320×740 layouts checked. Observed content/scroll
  widths matched (368/368 and 299/299), controls wrapped, mobile navigation remained
  available, assisted feedback rendered and saved Tutor text gained controls.
- User confirmed on their actual phone: “Playback and all three speeds work.” The
  phone model/browser were not supplied. This is user-reported verification, not an
  agent-operated physical-device test; a broader Safari/iOS, Android, Firefox and
  screen-reader matrix remains unverified.

## Deployment

Implementation checkpoint `be0967b` was pushed normally to existing `main`; repository
and Render service names are unchanged. The existing
[Tests workflow](https://github.com/NekomeKozo/japanese-ai-tutor/actions/runs/37113860120)
passed, including the full backend suite with PostgreSQL and all 44 frontend tests.
The existing [Render site](https://japanese-ai-tutor.onrender.com/#study/listening)
served the new Listening tab and controls after its normal cold start; `/health`
returned 200 and unauthenticated protected paths still returned 401.

Live N5 playback produced native start/end events. A four-question run completed with
two correct unassisted and two correct assisted answers, displayed separately in the
summary. Transcript timing, feedback and navigation were checked. The live desktop
screenshot is saved in the task workspace at `outputs/phase10a-live-listening.png`.
No tutor generation was requested for this listening verification.
Saved Tutor conversation/recap restored and its displayed Japanese examples played
at normal speed without requesting a new reply. JLPT history remained unchanged
(completed N5 quick 80%, completed N4 mock 5%).

## Phase 10B

Browser recording remains a separate, unimplemented phase requiring user approval.
Microphone consent, local recording lifecycle and upload/privacy choices need their
own design and tests. No Phase 10B implementation is included here.
