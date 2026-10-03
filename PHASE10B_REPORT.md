# GoiGrow — Phase 10B

## Inspection and implementation

Started from clean `main` at `6bcd19f`. Read Phase 10A report and inspected the native
speech controller, classic deferred-script architecture, Tutor panel, frontend tests
and security headers. Reused existing cards/buttons and kept recording separate from
the chat composer. No repeat of the Phase 1–9 audit.

`frontend/recorder.js` provides a reusable controller and a collapsed **Record spoken
Japanese** Tutor panel. Record is the only action that requests microphone access;
there is no permission request on page load or panel opening. Stop releases tracks
immediately and builds a local Blob preview. Native audio controls and Play preview
provide playback. Record again, Discard and Cancel dispose of prior resources.

Lifecycle: idle → requesting → recording → processing → preview; failures enter error
and permit explicit retry. Cancel returns to idle. A generation token rejects stale
events and releases late permission grants. While a cancelled permission prompt is
still unresolved, another recording request is disabled (no repeated prompts); TTS
is restored. The browser prompt itself cannot be dismissed programmatically.

## Formats, limits and cleanup

Checks `MediaRecorder.isTypeSupported` in order: WebM/Opus, WebM, MP4/AAC, MP4, Ogg/Opus.
If no candidate is advertised, or an advertised option throws NotSupportedError,
uses the browser’s default. Actual recorder/chunk MIME is retained in Blob.type and
the controller’s recording metadata; no guessed extension or transcoding.

Requests 250 ms chunks, bounds retained bytes to 8 MB, and stops at 60 seconds using
a deadline plus elapsed-time checks. Oversized recordings, including final chunks,
are discarded with an explanation. Empty clips, initialization/permission/device
errors, interruption and missing finalization events recover without active capture.
The processing watchdog is five seconds. Limits are client-side; browser suspension
can delay timers/events, and future backend limits must be independent.

All exits stop stream tracks, detach recorder/track handlers, clear capture timers
and discard chunks. Discard, retry, navigation, page exit, panel close and learner
changes revoke object URLs and clear the audio source. Hiding a tab cancels active
capture and pauses preview. Starting capture stops TTS and preview; TTS stays blocked
while requesting/recording. Preview and TTS stop each other rather than playing together.

## Privacy and security

Audio stays in browser memory, never localStorage/IndexedDB or the backend. No audio
uploads, logging of recordings, new API/provider/key, database/migration, worker,
transcription or scoring. User notice states this explicitly. The only security-header
change is `media-src blob:` for the local audio source. Existing script/connect source,
frame and authentication restrictions remain unchanged. Dynamic messages use textContent.

## Files changed

- Added `frontend/recorder.js` and this report.
- Updated `frontend/audio.js` (small recording lock), `index.html`, `styles.css`,
  `app/main.py` (Blob media policy), `tests/frontend.test.cjs`, `tests/test_api.py`, README.

## Verification and limitations

- 62 frontend tests passed: all 44 existing tests plus 18 focused recording tests
  covering support/security context, permissions, lifecycle, late grants, cleanup,
  duration/size limits, empty clips, errors, MIME/default fallback, navigation,
  preview/retry/discard, playback failures, zero uploads and TTS interaction.
- 67 targeted API/staging regression tests passed, including the narrow media policy
  and unchanged script/connect/frame restrictions. CI runs the full PostgreSQL suite.
- Desktop and emulated 390×844 / 320×740 layouts checked; content and scroll widths
  matched (368/368 and 299/299). Native permission-wait/cancel states checked locally.
- The Windows in-app browser did not provide a usable microphone-permission grant
  interface through the available automation controls. Physical speech capture and
  audible preview were therefore not completed by the agent. Successful recording
  lifecycle/preview was tested with mocks, not a physical microphone.
- The user chose to test on their actual device later. Chrome/Edge/Safari physical
  recording, denied permission UI and mobile microphone-indicator checks remain
  unverified. API/MIME support does not guarantee a working device or playable codec.
- Live Tutor and Study → Listening both reached the native Playing Japanese audio
  state after deployment. The new panel and enabled Record button were visible
  below Send message. No physical microphone capture was claimed.

References: [getUserMedia](https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getUserMedia),
[MediaRecorder](https://developer.mozilla.org/en-US/docs/Web/API/MediaRecorder),
[MIME support checks](https://developer.mozilla.org/en-US/docs/Web/API/MediaRecorder/isTypeSupported_static).

## Deployment

Published implementation commit `d0aeba0` as `Phase 10B - add browser microphone recording`
through the existing main/Render workflow. GitHub Tests passed (run 37115758651).
Verified the live HTTPS Tutor recording panel, microphone-off notice and Record
button, plus existing Tutor and Listening playback. Source/history privacy audit
passed. Actual-device microphone testing remains deferred at the user's request.
No Phase 10C work began.

## Handover for Phase 10C

Controller metadata exposes the in-memory Blob, actual MIME and elapsed duration.
No upload or speech-to-text integration is implemented. Phase 10C needs explicit
user approval, an upload/privacy design and independent backend MIME/size/duration
validation. This phase does not authorize or begin Phase 10C.
