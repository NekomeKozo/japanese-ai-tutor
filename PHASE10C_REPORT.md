# GoiGrow — Phase 10C

## Audit and scope

Started from clean main `a01ec6b`; read 10A/10B reports and inspected recorder/TTS,
provider, ownership/origin, rate limits and request buffering. Baseline: 62 frontend
and 67 API/staging tests passed. Phase 1–9 functionality was preserved. No schema,
migration, database, auth-code, chat-provider or learning-algorithm changes.

## Provider evaluation and cost (official docs checked 2026-10-03)

Selected **Groq whisper-large-v3-turbo** using the existing server key, separate from
text generation. Dedicated `/audio/transcriptions`, `language=ja`, never English
translation; [Whisper language definitions](https://github.com/openai/whisper/blob/main/whisper/tokenizer.py)
include Japanese. No STT failover or new account/key/provider subscription.

[Groq speech documentation](https://console.groq.com/docs/speech-to-text) lists WebM,
MP4/M4A, Ogg, WAV and other formats; Free uploads are capped at 25 MB, minimum audio
0.01 s, minimum billable duration 10 s. It does not publish a separate numerical
maximum duration there; GoiGrow independently caps decoded audio at 60 s. Published
Turbo pricing beyond Free is $0.04/audio hour (~$0.00067 per 60-second clip). No paid
billing was enabled. Reliability is handled with deadlines, response bounds and
explicit retry; no SLA or real-world accuracy guarantee is claimed.

[Groq Free limits](https://console.groq.com/docs/rate-limits) currently list 20 RPM,
2,000 requests/day, 7,200 audio seconds/hour and 28,800/day for this model, shared by
the organization; account-specific limits can differ. App defaults: 6/user/hour,
10/global/minute, 30/global/hour, 300/global/day. Maximum clips imply 1,800 s/hour and
18,000 s/day at defaults, leaving nominal headroom. Other apps, restarts or multiple
workers can consume/reset that headroom. With paid billing disabled, quota errors
fail safely rather than introducing paid fallback. Hypothetical maximum default
paid-volume cost would be $0.20/day; this is not an enabled billing arrangement.

Also evaluated [Gemini transcription](https://ai.google.dev/gemini-api/docs/transcribe),
[audio formats/limits](https://ai.google.dev/gemini-api/docs/audio),
[pricing](https://ai.google.dev/gemini-api/docs/pricing) and
[quotas](https://ai.google.dev/gemini-api/docs/rate-limits). Dedicated Gemini 3.5
Transcribe has a Free tier and estimated paid $0.005/minute; Free data may improve
Google products and quotas depend on the project. General audio docs list WAV,
WebM/M4A and 20 MB inline requests, up to 9.5 hours per prompt; these are not assumed
to apply unchanged to the dedicated model or existing chat model. Groq was selected
for explicit Japanese Whisper configuration, existing Free key, documented quotas
and owner-confirmed ZDR. No Gemini audio adapter or paid route was introduced.

## Implementation, compatibility and API

Reuse the 10B recorder. Preview does not upload; **Transcribe audio** is explicit.
`frontend/speech.js` decodes the actual recording using native Web Audio, validates
decoded duration and normalizes to 16 kHz mono PCM16 WAV. Native WebM/Opus, MP4/AAC,
Ogg/default recordings remain supported when that browser can decode its own output.
If decoding is unavailable, retain preview and explain how to retry elsewhere.
No conversion dependency/FFmpeg, second recorder or multipart parsing dependency.
See [decodeAudioData](https://developer.mozilla.org/en-US/docs/Web/API/BaseAudioContext/decodeAudioData)
and [OfflineAudioContext](https://developer.mozilla.org/en-US/docs/Web/API/OfflineAudioContext).

`GET /api/speech/config` gives safe availability, not keys. Learner-owned
`POST /api/learners/{learner_id}/speech/transcribe` accepts raw WAV and UUID
`X-Transcription-ID`. The server ignores filenames and client duration: checks RIFF
length, chunks, exact PCM format, complete sample bytes, actual duration and digital
silence. Unsupported native containers are rejected directly; the frontend supplies
verified WAV. Response separates original text, Japanese language, duration, provider
and request ID. Learner edits stay tab-local; Confirm only fills an empty/same-text
composer and never submits to Tutor or creates learning evidence.

Limits: 60 s/8 MB local recording; decoded WAV <=60 s and received body <=2 MiB;
two process-wide uploads/provider requests, one transcription per identity; 15 s
upload, 30 s total provider deadline, 128 KiB upstream response, 4,000 text chars.
Only the exact speech route gets a larger body cap; other requests keep 32 KiB.
Auth, origin and learner ownership are checked before buffering audio in staging.
Ten upload attempts/minute/user also bound malformed/retry traffic. STT usage caps
apply independently from chat in all environments. Duplicate in-flight identities
and successful UUIDs are rejected; only IDs/expiry retained for 10 minutes, no audio
or transcript result cache. Failed calls allow explicit retry; no automatic retry.

## Privacy and security

Owner confirmed Groq Free billing and ZDR and authorized live tests on 2026-10-03.
Default `STT_ENABLED=true` reuses configured server Groq key; absent key or explicit
false returns unavailable while recording/preview continue. No billing/dashboard
changes were made. [Groq data policy](https://console.groq.com/docs/your-data) says
inference is not normally retained, but reliability/abuse data may be held up to
30 days (longer if legally required); ZDR opts out of this customer-data retention.
Usage metadata remains. Account settings/ZDR are user-reported, not independently
verified by the agent. Learners see transmission/retention notices before upload.

No raw audio/transcript logs, permanent files, PostgreSQL audio, public storage or
new credentials in frontend. In-memory raw request/response data is released after
handling. Cancel/navigation/discard abort local waiting, invalidate late callbacks
and clear transcript; upload cancellation cannot recall already transmitted audio.
Failures retain the original clip for explicit retry. Existing CSP/auth protections
remain. Silence heuristics can miss noise/hallucinations or reject very quiet speech;
transcription accuracy is never treated as proficiency evidence.

## Files changed

- New `app/speech/{__init__,audio,schemas,provider,service}.py`, `app/api/speech.py`,
  `frontend/speech.js`, `tests/test_speech.py`, this report.
- Updated config, main wiring, safeguards body handling, index/styles, frontend
  tests, `.env.example`, README. Existing recorder/audio modules remain unchanged.

## Verification and live status

- 74 frontend tests passed (62 existing +12 STT), including editable/original text,
  explicit actions, no Tutor submission, bounded WAV generation, native format
  normalization, duplicate clicks, abort/deadline/stale callbacks, preview retention
  and missing config. Native decode mock tests are not physical codec proof.
- 103 targeted backend/security tests passed (36 STT +67 existing); full local
  regression: 550 passed, 14 PostgreSQL-dependent skipped. CI supplies PostgreSQL.
- Local browser exercised mock microphone + fake STT through real Web Audio WAV
  decoding, native preview playback controls, HTTP validation, edit and Confirm.
  Confirm populated the composer without a message. Emulated 390×844 and 320×740
  widths matched scroll widths (368/368 and 299/299); controls remained reachable.
  The fixture is workspace-only and is not shipped or enabled on Render.
- Live Groq transcription smoke test **not passed/claimed**: in-app browser lacks a
  usable microphone-grant interface; local credentials do not include the staging
  Groq key. The user chose actual-device testing later. Live provider availability
  alone will not be reported as successful transcription. Physical microphone,
  Chrome/Edge/Safari compressed-codec recording and Japanese accuracy still need
  that device test; automated silent/failure cases passed.
- Deployment/CI/live availability checks pending; update below after publication.

## Phase 10D handover — not begun

Original vs edited text is separate and tab-local. No pronunciation scoring,
speaking mastery, streaming, automatic submission, persistent audio or voice-chat
integration. A later phase needs explicit approval and must not treat STT errors as
learner errors. Process-local quotas/dedup are suitable for current single-worker
Alpha; shared durable limits would be needed before multiple workers/instances.
