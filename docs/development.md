# Development

Work from the repository root. Python 3.12 is selected by `.python-version`;
Node.js runs the frontend tests and syntax checks. The browser client needs no
Node build step or JavaScript package installation for normal development.

## Setup and run

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt -r requirements-knowledge.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

On macOS/Linux substitute `.venv/bin/python` and `cp .env.example .env`. Do not
overwrite an existing private `.env`; inspect your local configuration first.
The lock file supplies the tested Python stack. Administrative reference ingestion
also needs `requirements-knowledge.txt`; `requirements-dev.txt` groups development
and ingestion requirements when updating a development environment.

Open http://127.0.0.1:8000. Local API documentation is at `/docs`. Use a single
worker and keep unauthenticated development on loopback. Optional `--reload`
restarts process-local caches; persisted SQLite history survives normal restart.
Launch from the repository root to keep relative local data paths stable.

`.env.example` contains safe defaults. Leave the local database connection unset
for isolated SQLite development. Set provider credentials only in private settings
when deliberately testing live generation. Without them, placement's deterministic
grading and fixed study content remain usable; provider-dependent work reports
unavailable evaluation rather than inventing a failure score.

## Tests and source checks

Activate the virtual environment, or substitute its full Python path:

```sh
python -m pytest -q
node --test tests/*.test.cjs
python scripts/audit_deployment.py
git diff --check
```

In PowerShell, check frontend syntax with:

```powershell
Get-ChildItem frontend\*.js | ForEach-Object { node --check $_.FullName }
```

CI runs Python tests, Node tests, JavaScript syntax checks and a secret/source/history
audit. Its PostgreSQL service is disposable and loopback-only. To run PostgreSQL tests
locally, configure `TEST_POSTGRES_URL` privately for a disposable local instance.
Never substitute a deployed database: integration tests create and remove fixtures.
External HTTP transports are blocked in ordinary tests; mocked provider/Auth/speech
results do not demonstrate live account access, model quality or device permissions.

Use focused tests while changing a subsystem, followed by the checks appropriate
to its impact. Documentation-only work needs link, privacy, preservation and diff
checks; it does not justify production queries or real email/audio/model traffic.

## Structure and extension points

| Location | Purpose |
|---|---|
| `app/main.py`, `app/config.py` | Application construction and validated settings |
| `app/api/`, `app/web_assets.py` | Same-origin APIs, protected pages and static delivery |
| `app/learner/`, `app/curriculum/`, `app/mastery/`, `app/review/` | Learning state and deterministic policies |
| `app/assessment/`, `app/jlpt/`, `app/audio_progress/` | Authored assessment/practice and audio evidence |
| `app/accounts.py`, `app/auth.py`, `app/account_links.py`, `app/learner_access.py` | Account/session and ownership boundaries |
| `app/llm/`, `app/speech/`, `app/knowledge/` | External-provider and optional reference adapters |
| `frontend/` | Native browser UI, assets, authored flashcards and PWA worker |
| `scripts/`, `tests/` | Explicit administration/development tools and isolated tests |

New learning signals should enter the validated event boundary, with canonical
topics and provenance. Do not make models write state directly. Keep generated
content separate from authored banks and require editorial validation before
publication. [JLPT authoring](jlpt.md), [provider adapters](provider-design.md),
[knowledge ingestion](knowledge.md).

## Local data and maintenance

Local SQLite data, private references and knowledge indexes are ignored. Back them
up before upgrade, reset or replay. Review the maintenance tool's `--help` and target
an explicitly chosen disposable/local database and learner. Never paste real IDs or
connection strings into public examples or command transcripts.

| Tool | Scope |
|---|---|
| `python -m app.learner.reset --help` | Deliberate local learner-derived-data reset |
| `python -m app.mastery.maintenance --help` | Mastery evidence replay |
| `python -m app.review.maintenance --help` | Review rebuild, suspension and resume |
| `python scripts/migrate_account_links.py --help` | Reviewed additive association-table administration |
| `python scripts/build_knowledge_base.py --help` | Private local reference extraction/indexing |
| `python scripts/import_knowledge.py --help` | Explicit derived-index import; inspect dry run first |

Some legacy reset/mastery/review CLIs currently reject learning schema 8 in their
version guards. Do not bypass that check, manually lower the schema marker or run
those tools against current production data. Updating their guards is a separate
implementation task.

Reset/replay tools are not normal startup or recovery steps and do not establish
ownership. Production changes require their own authorization, private backups,
schema compatibility review and an unchanged-history comparison where applicable.

## Documentation and contribution policy

Follow [AGENTS.md](../AGENTS.md). Keep public documentation about current behavior;
update [architecture](architecture.md) when permanent boundaries change. Put task
journals, phase reports, approvals and rollout checkpoints in ignored `work/phases/`.
Put generated execution logs, measurements and screenshots in ignored `work/evidence/`.
Reviewed design-reference assets can remain intentionally tracked; do not blanket-ignore
the design directory. Private reference documents are never public design assets.

Before committing, inspect Git status and the explicit diff, run applicable checks,
and stage only intended files. Preserve unrelated edits. Do not commit a generated
report simply because it is Markdown. Public commits contain code, tests and durable
documentation, without private account data or execution narratives.
