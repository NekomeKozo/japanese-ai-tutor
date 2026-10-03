# GoiGrow — Phase 10F

## Implementation

Started from clean `main` at `d342507`. Read 10A–10E reports and inspected the actual
listening/speaking lifecycle, voice confirmation, saved chat transactions, learning
events, Progress and schema (version 7). No Phase 10G work.

Progress → Overview now includes listening, speaking, voice conversations and the
latest 20 completed audio activities. Empty and independently retryable error states
preserve other Progress sections. One learner-scoped GET is made when Progress loads;
Home, playback and Progress aggregation make no additional LLM/STT calls.

Listening uses the existing eight original passages and matching server catalog.
The server validates exercise/choice and computes correctness. Unassisted and
transcript-assisted correct/total/accuracy remain separate; an empty denominator
shows no percentage. Temporary listening without a learner retains tab-only feedback
and is explicitly labelled. Catalog parity is tested to prevent frontend/backend drift.

Speaking retains the existing 18 prompts and text feedback. Attempts are exercises
opened (including explicit retry); completions require explicit learner confirmation
and a successful learner-owned STT receipt. Failed STT, preview, playback and opening
Progress cannot complete an exercise. Completion is activity, never pronunciation,
accent, fluency, placement, JLPT or mastery evidence.

Confirmed voice drafts add a transcription identifier to the SAME saved chat request.
Only successful transactional commits create spoken-turn activity. Ordinary typed
turns remain text; mixed scenarios reuse existing transcripts. Finish records one
voice conversation only if a saved spoken turn exists. Old unmarked turns are not
retroactively classified. Existing Phase 8 observations still run exactly once.

## Persistence, integrity and privacy

Schema **8** adds only `ix_audio_events` over existing `learning_events`; no new table,
transcript store, raw audio column or destructive migration. Earlier migration guards
accept v8; SQLite/PostgreSQL share the existing transactional compatibility layer.

Events: `audio_attempted`; `listening_unassisted` / `listening_assisted` (score 0/1);
`speaking_completed`; `voice_turn_completed`; `voice_conversation_completed`.
Metadata contains authored exercise/scenario ID, level/mode, assistance and selected
choice as applicable. Minimal `speech_transcribed` / `speech_used` receipts retain
only identifiers, ownership, timestamps and a consumption target; they are omitted
from ordinary activity and audio history. No original STT/edited speaking transcript,
raw audio, provider credentials or numerical pronunciation score is stored for analytics.
Confirmed conversation text remains in its existing private saved-turn storage.

Client UUIDs identify attempts; namespaced deterministic completion/voice IDs enforce
one record per attempt/turn/session. Conflicting identifier reuse returns 409. A
successful transcription can complete only one speaking attempt or voice turn,
including across matching client UUIDs. Provider/chat failures do not consume it.
Completion retries keep the first submitted answer and identity. Legacy text-request
fingerprints remain compatible; existing replay does not call a provider or reapply
mastery. SQL totals are computed server-side, never submitted percentages/counters.
History is bounded to 20 metadata records; indexed aggregation avoids transcript scans.

Existing staging auth/origin/resource ownership, Groq Free/ZDR settings, quotas,
audio size/duration limits and backend-only credentials remain unchanged. No paid
provider, external analytics, automatic upload or extra audio integration.

## Files and validation

New: `app/audio_progress/{service,migrations,catalog,__init__}`, API audio-progress
router, `frontend/audio-progress.js`, `tests/test_audio_progress.py`, this report.
Updated: main/repository migration wiring and version guards; speech receipt hook;
saved-chat fingerprint/commit and conversation finish; frontend listening/speaking/
voice/confirmation, Progress rendering, HTML/CSS; focused regression expectations,
frontend tests and README.

- Full offline backend regression before final integrity refinements: **560 passed,
  17 PostgreSQL-dependent skipped**, two existing dependency warnings. Final affected
  speech/conversation/JLPT/audio suite: **120 passed, 12 skipped**.
- **106 frontend tests passed**, including all 98 prior regressions. New checks cover
  catalog parity, server correctness, playback boundaries, uncertain save retries,
  metadata-only confirmation, errors/empty states and voice/text classification.
- New SQLite/PostgreSQL-parametrized checks cover accuracy, reload/restart, mixed
  voice, receipt reuse, ownership and additive/atomic migration preservation.
  PostgreSQL runs through the existing CI service; local skips are not claimed as passes.
- Disposable local browser check used a new database/learner and workspace-only
  mock microphone/STT/LLM, real WAV decoding and application HTTP/database paths.
  Two listening answers produced 1/2 (50%) unassisted; Read Aloud and Spoken Answer
  each saved once; a restaurant spoken reply and Finish yielded one spoken turn and
  one completed voice conversation. Refresh preserved all totals without duplicates.
- Desktop and emulated 390×844 / 320×740 Progress layouts checked; document and scroll
  widths matched (368/368 and 299/299). Metrics stack and history wraps; navigation
  remains reachable. No real learner profiles were changed or reset for this check.

## Deployment and remaining limits

Deployment/CI/live verification pending at this implementation checkpoint.

Actual physical microphone/codec behavior and real Groq Japanese recognition remain
deferred from 10B–10E; mocked integration is not physical speech acceptance. Assistance
reflects the UI reveal flag, not proof of what a learner heard. Exercise completion
does not establish linguistic proficiency. Current exercise sets and unsent audio
remain tab-local; only confirmed activity survives reload. Existing process-local
STT quotas retain their single-worker limitation. Keep authored IDs stable when
changing catalogs; do not invent historical audio results.

Phase 10G handover: verify actual-device microphone, preview/codec, keyboard and
navigation cleanup with these existing singleton controllers and activity IDs.
No browser compatibility overhaul has begun. **Stop after Phase 10F.**
