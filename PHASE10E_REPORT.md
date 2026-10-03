# GoiGrow — Phase 10E

## Inspection and implementation

Started on clean main `939ad03`; read Phase 8 and 10A–10D reports and inspected the
actual conversation.js, saved-session utilities, chat request/replay, ownership,
recorder, speech and TTS interfaces. Phase 10C real microphone/Groq acceptance was
still deferred and remains explicitly unresolved below. No full historical audit.

Optional voice replies extend active Phase 8 Tutor scenarios. The single recorder
panel becomes Record spoken reply / Record Reply; the text composer remains visible.
One small frontend/voice.js binds each recording to the current learner/session and
provides Confirm and Send, Cancel, busy controls and lifecycle cleanup. Speech's
existing confirmation adapter supports context-specific labels/help. Ordinary Tutor
still uses Confirm text to copy an unsent draft; Study speaking uses Confirm answer.

app.js exposes its existing form-submission path as submitChatMessage(), shared by
text and confirmed voice. Successful turns discard voice resources; failures retain
edited text, clip and request ID for explicit retry. A late response cannot populate
a replacement learner/session. Opening/restoring/changing sessions and finishing
clear transient recording/transcription; finish stops capture immediately.

Files changed: frontend/voice.js (new), app.js, conversation.js, learner.js,
recorder.js (start guard only), speech.js (labels/help), speaking.js (shared-panel
visibility), shell.js, index.html, tests/frontend.test.cjs, tests/test_speech.py,
README.md and this report. No production backend, schema, migration or API changes.

## Data flow, persistence and providers

User Play → browser japaneseAudio TTS; Record/Stop/preview → existing browserRecorder;
explicit Transcribe → existing speechTranscriber / learner-scoped Groq Japanese STT;
original STT + editable tab-local transcript → explicit Confirm and Send → SAME
/api/chat payload, saved learner/session and request_id → existing TutorService →
Phase 8 saved history/adaptation/observations → user-initiated reply TTS.

Only edited confirmed text is saved as a learner turn; original STT is not separately
saved or evaluated. Recognition errors are not pronunciation evidence. Chat replay
and transactional commit deduplicate both turns and observations. After refresh,
existing restoration shows one authored opening and saved confirmed turns, correction
policy and derived difficulty. Raw clips/unconfirmed transcripts do not survive reload.

One explicit STT call plus one normal Tutor call per successful spoken turn; browser
TTS makes no new LLM call. Catalog/start/restore/preview/replay/finish do not generate.
Gemini primary, Groq text fallback, RAG boundaries/scope enforcement, preferences,
mastery pipeline and adaptive rules are unchanged. STT remains a separate existing
Groq Whisper responsibility. No extra provider, environment variable, paid billing,
streaming, background listening or pronunciation/placement analytics introduced.

## Security, privacy and errors

Existing Free/ZDR owner confirmation, backend-only key, access/origin/learner/session
ownership, scope/injection/copy controls and independent STT/chat quotas remain.
Microphone and upload each require explicit action; learners see Groq transmission
and retention notices. No permanent raw audio/public URLs/transcript logging added.
Original and edited text stay separate until successful confirmation and sending.

Existing recorder handles permission/unsupported/empty/size/duration/preview errors;
STT handles timeout/quota/network/provider errors and keeps clips for explicit retry.
A failed Tutor request retains the confirmed editor and pending request_id; it does
not retranscribe. Busy locks prevent simultaneous typed/voice sends. Conflicting
text drafts are protected. Cancel, panel close, navigation, learner/session change
and finish release capture/URLs and invalidate late STT results. Completed scenarios
cannot accept a voice reply; separate Study speaking remains usable afterward.

## Automated and manual verification

- 98 frontend tests passed: all 86 Phase 10A–10D/earlier tests plus 12 voice cases
  covering explicit edited-text submission, double sends, safe chat retry, text/voice
  switching, draft protection, stale STT/chat, cleanup/completion, permission/STT
  failure, one-opening restoration/playback and independent Study speaking.
- Full local backend suite: 552 passed, 14 PostgreSQL-dependent skipped, two existing
  dependency deprecation warnings. Two added integration cases chain mocked STT to
  existing restaurant chat, verify corrected text saved once, one evidence event,
  request replay, failure recovery, restoration and completed-session rejection.
  Existing ownership, scope, RAG/fallback and adaptation tests remain unchanged.
- Browser restaurant check used workspace-only fake microphone and STT/LLM with real
  WAV decoding, HTTP validation and SQLite persistence. Opening TTS, Record/Stop/
  preview, original 一人です。 edited to 二人です。, explicit send, continuation,
  typed 水をください。, second voice お茶をお願いします。 and reload passed.
  Reload showed exactly three exchanges and one opening. STT failure retained preview
  and retried; stopping the local server caused a chat connection failure, then
  Confirm and Send retried after restart without retranscription or duplicate turn.
  Finish during recording released capture and showed the existing three-turn recap;
  subsequent general Tutor send passed. Fixture replies are mocked, not evidence
  of Japanese correction quality. No fixture ships to Render or contacts Groq.
- Emulated 390×844 and 320×740 layouts matched document/scroll widths (368/368 and
  299/299). Japanese text, existing composer and recording controls remained reachable.
  This is browser emulation, not actual-phone microphone/keyboard acceptance.
- Source and available Git history privacy audit and whitespace checks passed.
  Implementation `4a9f97f` (`Phase 10E - integrate voice with adaptive conversations`)
  pushed normally through the existing GitHub/Render workflow. [Tests run 37131572914](https://github.com/NekomeKozo/japanese-ai-tutor/actions/runs/37131572914)
  passed, including the full PostgreSQL suite and all 98 frontend tests.
- Live HTTPS release shows the optional Record spoken reply panel, Record Reply,
  text composer and configured Groq disclosure. A new restaurant scenario played
  its authored Japanese opening. The typed test reply 二人です。 used the SAME chat
  submission path and received かしこまりました。こちらへどうぞ。メニューをどうぞ。
  Reply TTS reached Playing Japanese audio. Reload restored one opening and exactly
  one saved exchange with balanced policy/beginner difficulty. This is a live text
  generation/persistence check, not a real spoken/transcription claim. The new
  test restaurant is left active for the deferred device test; no pre-existing
  active scenario was finished or replaced. No browser errors/warnings observed.
  Proof: task workspace outputs/phase10e-live-voice.png. Temporary local preview
  and tab stopped/closed, viewport reset. No service/Supabase/domain changes.

Implementation, automated regressions, mocked audio integration and live availability
are verified. Physical-device/Groq speech acceptance remains pending below.

## Known limits and Phase 10F handover

Actual physical Japanese speech capture, device codecs and successful real Groq STT
remain pending from 10B–10D. The in-app browser has no usable microphone permission
interface, and local credentials do not include the staging key. The user deferred
physical testing; live availability or mocked success will not be claimed as a
passed real-provider transcription test. A device test should record 二人です。 in
Restaurant, preview/transcribe/edit/Confirm and Send, switch to typing, reload, finish
and check the microphone indicator. Account Free/ZDR settings remain owner-reported.

Existing request_id retry is tab-local until success; reloading after an uncertain
submission restores saved turns but discards unsent drafts/audio. Learners should
inspect restored history before sending another reply. Process-local STT quotas are
appropriate for the current single-worker deployment; multi-worker scaling would
need shared durable limits. No broader device/screen-reader matrix is claimed.

Phase 10F has NOT begun. Future explicitly approved speaking analytics must respect
recognition uncertainty and confirmed-text boundaries; never infer accent/phonetic
accuracy from transcripts. Existing session engine and singleton audio interfaces
are the handover points. Stop after Phase 10E.
