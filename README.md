# GoiGrow — Japanese Tutor

*A little, every day.*

GoiGrow helps learners build Japanese knowledge through adaptive placement,
personalized study, spaced review and guided practice. AI supports tutoring,
explanations and selected evaluations; the application owns learning state,
curriculum selection, scoring rules and review scheduling.

Production: **https://goigrow.onrender.com**. The deployment is a private beta
with a staging gate and approved-account sign-in at `/auth/sign-in`.
Account sign-in alone does not claim or restore an existing learner profile.
Account-to-learner linking is separately controlled and is currently disabled.

## What you can do

- Take adaptive Japanese placement and view provisional skill estimates.
- Follow a personalized daily study plan and resume saved activities.
- Review vocabulary, grammar and kanji with mastery tracking and FSRS scheduling.
- Use flashcards for free practice or the existing due-review queue.
- Ask the tutor questions, receive corrections and practice scenario conversations.
- Practice N5/N4 vocabulary, kanji, grammar and reading in JLPT-style sessions.
- Listen to Japanese with browser speech playback and adjustable speed.
- Record, preview and explicitly submit Japanese audio for transcription; edit
  recognized text before confirming a speaking answer or sending a voice reply.
- View learning history and listening/speaking activity, and save study preferences.
- Install the PWA on supported browsers; its offline screen explains reconnection.

Practice banks and estimates are provisional, not official JLPT exams or certification.
Speech feedback evaluates recognized/edited text, not pronunciation. Browser voice,
microphone and PWA support vary. See [features and limitations](docs/features.md).

## Technology

Python 3.12, FastAPI, Pydantic and HTTPX serve a vanilla HTML/CSS/JavaScript client.
SQLite supports isolated local development; the deployed app uses private Supabase
PostgreSQL storage and Supabase Auth through a server-side account layer.
Gemini, Groq and OpenAI adapters share one tutoring interface; optional private
lexical knowledge retrieval adds bounded reference context. FSRS supplies scheduling.
Provider credentials and account tokens stay on the backend.

## Run locally

From the repository root, using Python 3.12 and Node.js for frontend tests:
For an existing checkout, preserve its private `.env` instead of repeating the copy step.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt -r requirements-knowledge.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

On macOS/Linux, use `.venv/bin/python` and `cp .env.example .env`.
Open http://127.0.0.1:8000; do not open the HTML files directly.
Enter only your intended provider's credentials privately in `.env` if you want
live tutoring. Missing credentials do not prevent deterministic study features.
Keep development on loopback with the local SQLite defaults; never copy production
database credentials into a test environment.

## Check changes

With the virtual environment active:

```sh
python -m pytest -q
node --test tests/*.test.cjs
python scripts/audit_deployment.py
git diff --check
```

The test suite uses mocked AI/Auth/speech transports. PostgreSQL integration tests
need a disposable loopback database; never use production. CI also checks each
`frontend/*.js` file with `node --check`.
See [development](docs/development.md) for platform commands and test prerequisites.

## Deployment and documentation

One Render web service serves the frontend and API. It connects to the existing
Supabase database; browser requests use relative same-origin API paths. Secrets
are configured privately in Render. `/health` is a public, zero-inference liveness
check; protected readiness and account checks are distinct.

- [Architecture](docs/architecture.md): current components, data and identity model.
- [Development](docs/development.md): setup, tests, maintenance and contribution rules.
- [Deployment](docs/deployment.md): Render, required settings, Auth URLs and rollback.
- [Security](docs/security.md): authorization, sessions, privacy and operational limits.
- [Features](docs/features.md): learner workflows and links to detailed design documents.

Keep private development journals and execution evidence outside public documentation.
See [repository working rules](AGENTS.md). Permanent design changes belong in the
current documentation, with architecture maintained in `docs/architecture.md`.
