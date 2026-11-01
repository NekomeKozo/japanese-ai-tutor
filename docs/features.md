# Features

GoiGrow combines a daily learning loop with optional AI-supported tutoring.
Its estimates guide study; they are not official JLPT results or calibrated guarantees.

## Placement and daily learning

Adaptive placement covers kana, vocabulary, grammar/particles/conjugation, kanji,
reading and written sentence construction. It adjusts item difficulty, supports
partial credit and unknown answers, and reports uncertainty. Listening/speaking
are not measured by placement. See [placement design](assessment-design.md).

Persistent learner memory records preferences, controlled topics, mistakes and
validated learning evidence without letting a model set scores or identity.
Daily Study plans use goals, strengths/gaps, prerequisites, recent activity and due
reviews. Planning and fixed content are deterministic; selected grammar/writing
activities can use validated generation. Saved activity state supports resume,
retry and recap. [Memory](learning-memory.md), [curriculum](curriculum-design.md).

## Mastery, reviews and flashcards

Vocabulary, grammar and kanji estimates distinguish tested dimensions and confidence.
Unknown dimensions stay unknown. FSRS is wrapped with conservative interval, lapse,
confidence and backlog policies. Reviews reuse the existing learner history and
activity contracts. [Mastery](mastery-design.md), [scheduling](review-design.md).

Flashcards offer authored vocabulary, grammar and kanji decks with reveal, navigation,
shuffle and Japanese playback. Free Practice does not invent scored mastery evidence.
Due Reviews uses the existing queue and Again/Hard/Good/Easy recall ratings; self-ratings
remain distinguishable from graded evidence. It does not create a second SRS system.

## Tutor and conversations

Ask questions, request explanations or submit Japanese for correction. Saved exchanges
and compact profile context personalize future teaching. Scenario conversations cover
everyday situations with starting guidance, correction preferences and bounded turns.
Scenario openings do not need a model call. Text entry remains available during optional
turn-based voice replies. [Provider boundary](provider-design.md).

Optional private lexical reference retrieval can ground explanations. It neither
publishes source documents nor chooses curriculum or scores. [Knowledge](knowledge.md).

## JLPT practice

The authored N5/N4 bank supports vocabulary, kanji, grammar and reading practice and
mock sessions. The server owns selection, answer snapshots, timing and scoring.
Feedback and learning evidence are withheld until mock completion; abandoned mock
answers are not fabricated performance. [Bank and operations](jlpt.md).

## Audio practice

- Browser Japanese TTS supports explicit Play/replay, Stop, voice selection and
  0.75×/1.0×/1.25× speeds. Available voices depend on device/browser installation.
- Listening exercises separate transcript-assisted and unassisted results.
- Speaking offers read-aloud, spoken-answer and repeat activities using a small
  authored beginner/N5/basic-N4 catalog.
- Record/Stop/preview is local. Transcribe explicitly uploads validated Japanese
  audio to Groq through the backend. Edit and confirm the transcript before use.
- In an active conversation, Confirm and Send creates a normal tutor turn; other
  transcript confirmation paths do not automatically send a chat message.
- Navigation, cancellation and replaced sessions release capture/playback resources.

Speaking feedback measures recognized/edited text against the task. It is not acoustic
pronunciation scoring. Listening/speaking/voice progress reflects completed learning
events, not playback clicks or claimed study time. Recognition errors and edited
transcripts limit what performance conclusions can be drawn.

## Progress, preferences and installation

Home and Progress summarize saved activity, skill evidence, mastery, review load and
audio practice. Preferences guide explanations, readings, correction style and study
goals. Empty/error states distinguish unavailable data from a new learner.

Supported browsers can install GoiGrow as a PWA. The offline screen helps reconnect;
it does not cache authenticated study or profile history. A new hostname or installed
iOS context can need separate sign-in and explicit profile restoration. Account sign-in
and learner ownership remain distinct. [Security and storage](security.md).

## Current limits

Content coverage is bounded, especially at advanced levels. AI explanations and
semantic grading can be wrong; heuristic confidence is not a pass probability.
Device speech support varies, transcription requires connectivity and explicit consent,
and browser text edits cannot establish pronunciation quality. Public signup is closed;
learner linking is separately controlled and currently disabled. General email onboarding
and cross-device restoration must not be advertised as complete merely because the
account-ready screen works.
