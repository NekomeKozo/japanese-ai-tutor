# Phase 10G — Desktop, Mobile & Browser Compatibility

## Inspection and targeted changes

Started on clean `main` at `1869b65`. Read Phase 10A–10F reports and inspected the existing shell, styles, playback, recording, transcription, speaking, voice conversation and progress code. Baseline: 106 frontend tests passed.

Desktop Edge confirmed a fixed left margin left excess space on the right of wide screens. Content now centers inside the space beside the existing 230px sidebar, with a 1480px maximum. Dashboard cards keep their natural height rather than stretching to match neighboring cards. Brand descriptor, tagline and chat labels have modest readability adjustments. The green theme, sidebar and brand hierarchy remain intact.

Mobile keeps the existing header and bottom navigation. Added safe-area side padding and focused-control scroll margins, smaller chat minimum height with a `vh` fallback, and wrapping for long content. Input text remains 16px. Recording's timer already has `aria-live="off"`; no ticking announcements were added.

Audio capability checks now require callable speech methods. Explicit Play can resume an engine left paused by the browser; there is no new Pause UI or automatic playback. Transcript confirmation now prevents overlapping callbacks, handles rejected callbacks without losing text, and ignores completion after context cancellation. Successful transcription configuration is cached within the page; failed/disabled checks remain retryable. The opening status explains a possible server cold start.

Files: `frontend/styles.css`, `frontend/audio.js`, `frontend/speech.js`, `frontend/voice.js`, `frontend/index.html`, `tests/frontend.test.cjs`, this report. No backend, database, provider, authentication, learning or route changes.

## Verification

- Frontend: **110 passed**. Four added tests cover incomplete speech engines/paused recovery, duplicate/failed/stale confirmation, configuration caching/retry and prefixed Web Audio decoding.
- Focused backend: **187 passed, 12 skipped** across speech, audio progress, conversation, JLPT, API and staging tests. Skips require the separate PostgreSQL test service. Existing CI runs its PostgreSQL suite automatically.
- Existing tests retain coverage for permission denial, late microphone grants, initialization failure, MIME/default-format fallback, recording deadlines, size limits, track/timer/URL cleanup, upload cancellation, rate limits and stale replies.
- Disposable local browser workflow: beginner setup; saved Home; Daily Study plan and correct answer; assisted Listening answer; Speaking Record → Stop → Preview → Transcribe → edit → Confirm; Tutor scenario Confirm and Send; reload restores the saved voice turn; Progress shows separate listening/speaking/voice metadata. Local microphone, transcription and tutor are deterministic fixtures, **not real capture or Groq**. Native Web Audio decoding is used.
- Navigation during local recording discards the clip and clears its preview. Recording blocks reference playback. Keyboard navigation, long Japanese draft wrapping and reduced-height 390×420 layout were checked. No real learner profile was reset.

## Browser matrix and limits

| Environment | Verification |
|---|---|
| Windows Edge, actual browser | Home widths 1024/1280/1440/1600/1920 and 320/360/390/430/768; responsive route smoke checks for Home, Daily Study, JLPT, Listening, Speaking, Tutor, Progress and Settings; no observed horizontal overflow. Scrollbars reduce actual content width slightly. |
| Edge desktop layout | At 1920, main spans x335–1815: equal 105px outer gutters within the sidebar's remaining space. Short/tall Home cards measured 157/233px independently. |
| Edge Japanese TTS | Six Japanese voices detected; explicit Play and speed selections exercised, with preparation/finished UI states. Audible output and reliable start events cannot be certified by automation; Listening retained assisted fallback when playback did not establish a start. |
| Codex in-app browser | Separate responsive Home checks at all ten requested viewport sizes; no overflow. This is not a Chrome, Android or Safari certification. |
| Chrome / Firefox | Not available through the connected browser tools; unverified. |
| Android Chrome / iPhone Safari | No physical device available; viewport checks are not microphone/keyboard/voice certification. |
| 125% browser zoom | Browser chrome zoom was not exposed through the connected controls; unverified. Reduced viewport checks do not substitute for zoom. |

Owner check on each available browser/device: Play → Stop → replay at all three speeds; Record → Stop → preview → Transcribe → edit → Confirm; navigate or background during recording and verify microphone turns off; retry after denial; check controls with the phone keyboard open. Use a short Japanese test sentence and confirm the transcript before sending. Also check desktop 100%/125% zoom. Existing Groq Free/ZDR configuration and explicit upload consent remain unchanged; no real recordings were transmitted during these checks.

## Deployment

Implementation commit `4e88516` was pushed using the existing main-branch Render auto-deploy workflow. [GitHub Actions Tests](https://github.com/NekomeKozo/japanese-ai-tutor/actions/runs/37140744379) passed, including the existing PostgreSQL regression workflow.

Verified the live frontend at `https://japanese-ai-tutor.onrender.com/`: new 1480px centered layout and cold-start copy are served; authenticated saved Home renders without overflow at all ten requested widths; mobile Tutor exposes recording and enabled Groq transcription controls; Japanese TTS discovers voices and reaches its finished UI state; Progress restores its audio summary. Live playback was exercised without submitting an answer or recording. Health returns 200; unauthenticated API/static requests remain protected (401). No service recreation, Supabase changes, billing changes or real audio uploads. Proof screenshots are saved in the task's outputs folder as `phase10g-live-desktop.png` and `phase10g-live-mobile.png`.

## Deferred work

Phase 11A backlog only: stronger page hierarchy, dashboard density and card grouping, sidebar information organization, clearer Tutor composer/voice control hierarchy, and JLPT setup/result organization. No redesign implemented.

Phase 10H remains the final security/privacy audit and release review, including owner-operated physical device evidence and any resulting fixes. Do not infer completed phone capture or production Groq transcription from mocked tests. **Stop after 10G; 10H and 11 have not begun.**
