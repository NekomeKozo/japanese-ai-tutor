# Phase 11D — Japanese Flashcards Foundation

## Inspection

Started on `main` at `b426938`, with a clean tracked working tree and Phase 11C present. Existing untracked design references were preserved. Read Phase 11C report and design discovery; inspected the mockup, real iPhone 13 Study spacing/navigation reference, Study shell, Phase 6 review/content infrastructure, learner/mastery catalogs and Phase 10A audio module. Mockups remain inspiration, not completed implementation. Frontend baseline: **110 passed**.

## Implementation and files

- `frontend/flashcard-catalog.js`: validated, immutable, application-owned catalog.
- `frontend/flashcards.js`: independent transient session model and safe DOM rendering; no requests or persistence.
- `frontend/index.html`, `shell.js`: Study → Flashcards at `#study/flashcards`, with existing hash/navigation conventions.
- `frontend/styles.css`: green/cream central card, readable Japanese, wrapping controls, shared tokens and mobile navigation clearance. No animations added; existing reduced-motion rules retained.
- `tests/frontend.test.cjs`: 14 focused flashcard tests alongside existing regressions.
- `design/screenshots/phase11d/`: desktop and mobile-emulated captures plus responsive measurements.

No backend, schema, database, migration, dependency, provider, authentication or scheduling changes.

## Schema, decks and content

Each card has `id`, `category`, `level`, `front`, `back`, `meaning`, `tags`; optional `reading`, `explanation`, paired `example_japanese`/`example_translation`, and nullable `topic_id`. Validation rejects malformed fields, invalid categories/topic IDs, missing vocabulary readings, unmatched examples and duplicate stable IDs. Records and tags are frozen; the catalog is parsed once.

| Deck | Count | Direction / content |
|---|---:|---|
| Vocabulary | 12 | Japanese ↔ English; kana, meaning and original sentence |
| Kanji | 10 | Character → meaning, selected readings and example vocabulary |
| Grammar | 8 | Pattern → usage, explanation and original sentence |

Reused existing item identities/meanings where appropriate; curated display content and examples were checked for Japanese/translation consistency during implementation. Beginner is a practice label, not an official JLPT vocabulary claim. Kanji readings are explicitly selective and context-dependent. No textbook, private reference, RAG or generated-provider content used. Ten vocabulary cards and all kanji/grammar cards link to existing exact topics. 猫 and 約束 keep stable flashcard IDs with null topic links until an approved later mapping; broad topic groups are not substituted as mastery evidence.

## Session and audio

Start applies the chosen deck/direction. Reveal creates the answer DOM only after explicit action; no answer, reading or example is accessibly exposed beforehand. Previous/Next clear reveal and stop audio. Shuffle restarts a duplicate-free deck, Restart retains its current order, and Finish shows an honest transient practice summary. Card position is announced and displayed. Native buttons, focus management, language attributes and existing focus rings support keyboard/touch/mouse use.

Reuses `attachJapaneseAudio` and the global Japanese speech queue. Vocabulary speaks the Japanese word; kanji and grammar speak their Japanese example. No activity callback or listening/mastery event is attached. Player subscriptions are destroyed on card/session changes or navigation; existing pagehide/visibility cleanup remains. Missing voice/unsupported browser guidance comes from the shared player. Learners see the browser speech-service notice. No Gemini, Groq, STT or paid TTS calls.

## Verification

- Final frontend: **124 passed**, zero failures; JavaScript syntax and diff whitespace checks passed.
- Focused coverage: valid/invalid catalog, stable IDs/decks, both vocabulary directions, specialized kanji/grammar, inaccessible unrevealed answer, next/previous bounds, shuffle uniqueness, restart/completion, empty deck, TTS text/cleanup, missing voice, progress labels, no requests/storage/review events, retained ordinary Study draft.
- Browser automation: **24 checks**, all three revealed decks at CSS viewport widths **320, 360, 390, 430, 768, 1024, 1440, 1920**. No horizontal overflow or visible flashcard buttons below 44×44px. Browser zoom was accounted for using measured CSS viewport widths; measurements are recorded.
- Local manual workflow: keyboard Reveal, both directions, full 12-card navigation → completion → shuffled restart, deck switches, Japanese audio reached Playing and Playback finished, ordinary Study/Daily Review restored, JLPT/Listening/Speaking/Tutor interfaces accessible. Local learner is disposable; providers/microphone are mocked. No live recordings or learner mutations required.
- Representative desktop and mobile captures visually inspected. Mobile captures are browser emulation; original iPhone screenshots were not changed. No new physical-phone or Safari audio test claimed.
- Deployment/live verification: pending the existing Render workflow after this commit.

## Limitations and Phase 11E handover

Sessions reset on reload and do not track recalled correctness, ratings, mastery, review completion or scheduling. Card position is browsing progress only. Browser voices and audible output vary by device. No custom decks, AI generation, swipe dependency or new account features.

Phase 11E may consume the stable card ID/topic links and pure session interface, but must reuse Phase 6 ownership, review attempt and scheduling rules. Null topic links need deliberate mapping before evidence integration. This phase submits no evidence. **Stop after Phase 11D; Phase 11E is not begun.**
