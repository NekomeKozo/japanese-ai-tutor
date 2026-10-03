# GoiGrow — Phase 10D

## Implementation

Study → Speaking Practice offers Read Aloud, Spoken Answer and Repeat a Phrase
for Beginner, N5 and Basic N4. The fixed catalog has 18 original prompts (two per
mode/level). Wording, level and answer variants were reviewed during implementation;
this is a small authored practice collection, not an official JLPT or independently
teacher-validated bank. No exercise generation or optional Tutor feedback calls.

Flow: choose level/activity, start, listen/replay, Record/Stop/preview, explicit
Transcribe, review/edit, Confirm answer, feedback, retry/next/finish. Repeat hides
its reference until confirmation or explicit assisted reveal. Starting a new set,
retrying and moving next discard the old clip and transcript. Navigation releases
capture/playback and restores the shared recorder to Tutor.

Files: frontend/speaking.js (catalog/state/feedback); index.html (Study panel and
recorder slots); shell.js (Study route); speech.js (confirmation callback adapter);
styles.css (Japanese/feedback readability); tests/frontend.test.cjs; README.md;
this report. Backend, database, API routes, authentication and algorithms unchanged.

## Reuse, evaluation and privacy

One existing japaneseAudio controller, browserRecorder and speechTranscriber;
one physical recording panel moved between Study and Tutor, not duplicated.
Phase 10C learner-scoped STT endpoint, backend-only Groq key, Japanese transcription,
Free/ZDR configuration, duration/size checks, ownership/origin/access restrictions,
rate limits and cancellation remain unchanged. No paid provider/billing changes.
Microphone activation and upload each require explicit action. Transmission to Groq
is disclosed; no permanent raw audio, public audio URLs or transcript logging added.

Original STT is separately viewable; only confirmed edited text receives feedback.
Read/repeat use descriptive normalized text comparison with kana/kanji/STT caveats,
never a pronunciation percentage, accent or fluency score. Spoken Answer recognizes
reviewed variants and a few conservative grammar patterns. Unrecognized expressions
receive a neutral limitation/sample, not an incorrect mark. Pattern recognition does
not validate every word or meaning. Edits invalidate confirmation; duplicate Confirm
reuses the existing result. No Tutor auto-send, saved speaking analytics, placement,
mastery or JLPT evidence. Current set/feedback are tab-local and do not survive reload.

## Verification

- 86 frontend tests passed: all 74 Phase 10A–10C regressions plus 12 focused speaking
  tests (three modes, explicit confirmation, editable/original separation, valid
  alternatives, neutral unknown answers, progression/retry, permission failure,
  STT failure, TTS/record coordination, cleanup, no auto-send/duplicate calls/scores).
- 103 targeted speech/API/staging backend tests passed. Backend unchanged; existing
  full CI includes PostgreSQL. Diff whitespace checks passed.
- Local browser completed all three modes using a workspace-only mock microphone
  and fake STT through real browser WAV decoding/HTTP validation. Native reference
  TTS, preview controls, edit/Confirm feedback, retry/next, assisted reveal and return
  to Tutor were exercised. Mock fixture is not shipped and did not transmit to Groq.
- Emulated 390×844 and 320×740 layouts had matching document/scroll widths
  (368/368 and 299/299). Japanese text and controls wrap without horizontal overflow.
- Deployment/CI/live verification pending checkpoint below.

## Remaining acceptance limits and Phase 10E handover

Actual physical microphone/codec behavior and successful real Groq Japanese
transcription remain unverified from Phase 10B/10C. The in-app browser cannot grant
native microphone access, local credentials do not contain the staging Groq key,
and the user deferred the device test. Provider-ready configuration and mocked
success are not reported as real-provider transcription success. On a device, test
all three modes, preview, edit/Confirm/retry and leaving during capture; recognition
accuracy depends on recording conditions and provider behavior.

Phase 10E has not begun. A future explicitly approved voice-conversation integration
can reuse the confirmation adapter and singleton controls, but must retain learner
review, existing quotas/privacy and avoid turning recognition uncertainty into
learning evidence. Multi-worker scaling still needs shared durable STT limits.
