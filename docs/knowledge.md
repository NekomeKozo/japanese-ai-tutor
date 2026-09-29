# Private Japanese knowledge build

Knowledge retrieval is optional and disabled by default. It adds evidence to existing
tutor chat; it does not select lessons, change learner scores, schedule reviews, or
generate placement questions. The Phase 7 UI is unchanged. No new HTTP API is added.

## Local build

Run from the canonical repository using its Python environment:

```powershell
python -m pip install -r requirements-dev.txt
python scripts/inventory_references.py
python scripts/build_knowledge_base.py
python scripts/search_knowledge.py "たい grammar"
```

The source folder is `reference/`. `knowledge_base/` holds private inventory,
manifest and SQLite index files. Both directories are ignored by Git and excluded
from the Docker context. Never force-add them. Do not place them under `frontend/`.
Search prints opaque source IDs, physical PDF page numbers and scores. The optional
`--preview` flag prints at most 100 characters per result for local developer review;
do not paste these previews into public issues or logs.

Supported inputs: text-based PDF using pypdf 6.18.1, UTF-8 TXT and Markdown.
Encrypted PDFs are skipped, even if an empty password might unlock them. Image-only
pages are recorded as skipped/OCR-needed; OCR is deliberately absent. Files over
150 MiB, documents over 3,000 pages and oversized individual pages are bounded/skipped.
A parser exception does not expose its message or discard other successfully built sources.
Text detection does not guarantee correct reading order or Japanese OCR quality.

Normalization uses NFC, removes zero-width/control artifacts, and normalizes whitespace.
It does not translate, romanize, replace kanji, or aggressively repair PDF line breaks.
Chunks remain within one physical page, preserve explicit Markdown headings and group
paragraphs. Oversized groups use sentence/newline boundaries, then a hard fallback.
Default maximum is 1,000 characters; `--chunk-chars` accepts 200–2,400. No blanket overlap.
Titles, editions and JLPT levels are not invented. Explicit metadata and filename-based
`inferred_category` are separate. Source paths stay in the local inventory, not the index.

## Safe rebuild

Run the same build command. The source ID derives from the relative path, not the
absolute machine path. Content hash plus build version and chunk size identifies an
unchanged source. Renaming a file creates a new identity; avoid unnecessary renames.
Each successfully extracted source replaces only its own chunks/postings in one
transaction. Failures and empty extraction preserve its previous successful index.
Removed source files are not silently deleted from the index. There is no automatic
prune operation. Duplicate chunk bodies are suppressed in each source and search results.
No learner database is opened by the local build command.

Do not regard a partial build as a complete representation of a book. Consult the
private manifest for skipped sources/pages. Unchanged entries refer to an existing
successful index version rather than a fresh extraction assessment.

## Retrieval and grounding

The inverted index stores English words and Japanese bigrams/trigrams, plus separated
single characters for particles/kanji. It uses indexed candidate lookup, query coverage,
phrase/boundary boosts, bounded term-density ranking, optional category/source filters
and duplicate suppression. A small documented alias set supports terms such as te-form.
Known vocabulary lists are excluded from grammar-form searches. This is lexical matching,
not semantic understanding; some related wording will correctly or incorrectly produce
no match. Unknown-category material and multi-topic PDF pages need careful evaluation.

At most 48 query terms and 120 candidates are considered. Default top K is 3 and minimum
score is 0.35; scores are ranking heuristics, not calibrated probabilities. The context
budget is 6,000 UTF-8 bytes. Whole records fit within it; oversized records are omitted.
Database retrieval runs in a worker thread with a two-second response deadline. One
outstanding retrieval per service is permitted; while a timed-out operation finishes,
later requests continue without grounding. Database timeouts also remain bounded.

Greetings and correction mode do not retrieve. Empty/unavailable retrieval gracefully
uses the ordinary tutor without a grounding badge. Relevant records are placed in a
separate untrusted-data message, never concatenated into system instructions. The same
selected data reaches the existing primary/fallback wrapper. Reference messages are
not persisted in learner conversation history. Responses are validated before any
conversation or learner-evidence writes; idempotent replay skips retrieval/generation.

System rules require original synthesis and deny authority to embedded source commands.
Suspicious instruction-like chunks are excluded. Requests to reproduce pages/chapters
are rejected. An output check blocks at least 60 normalized copied characters supported
by matching 24-character spans across the selected references. It checks all response
fields before persistence. These defenses reduce risk; they are not a proof against
all prompt injection, paraphrase reconstruction, or every copyright misuse.

## Existing PostgreSQL deployment

Do not upload PDFs or the local inventory to Render. After local acceptance, import only
validated derived source/chunk/posting records using the existing server connection:

```powershell
python scripts/import_knowledge.py
# After confirming the intended existing PostgreSQL connection privately:
python scripts/import_knowledge.py --apply
```

The first command is a local dry run. The second reads `DATABASE_URL` from the existing
private environment or project `.env`; never put it in command arguments, Git or chat.
It must point to the intended existing Supabase database. It uses TLS for remote
connections and does not create a database/service or modify learner tables.
An interrupted import can be rerun; unchanged source versions are skipped.
Bulk inserts avoid a network round trip per posting. Per-source transactions may briefly
contend with application transactions; perform imports during a quiet period.

Tables: `knowledge_meta`, `knowledge_sources`, `knowledge_chunks`, `knowledge_postings`.
The knowledge schema version is independent of learner v1–v5. Tables live in the existing
private `tutor_private` PostgreSQL schema, with PUBLIC privileges revoked; no browser
database access or Supabase client is added. Do not expose that schema through Supabase's
Data API or grant it to anon/authenticated roles. No pgvector extension is required.

Owner-controlled activation after successful import:

1. Open https://dashboard.render.com/ and select `japanese-ai-tutor`.
2. Open **Environment**, add `KNOWLEDGE_ENABLED` with value `true` (not secret).
3. Save/redeploy, then test the existing tutor with a reference-covered grammar question.
4. Look for the safe log `Knowledge retrieval status=available results=... latency_ms=...`.
   It must accompany a successful tutor response; no-match questions should still work.

Do not make this setting change automatically. No new secret or provider account is
needed. If `DATABASE_URL` is unavailable locally, the owner must configure that existing
connection privately before the import; never request its value in chat.

The server neither extracts documents nor migrates/builds the index at startup.
Missing optional knowledge storage does not fail `/health`, `/ready` or ordinary chat.
`/health` remains zero-inference. The regular provider still charges for any additional
context tokens; lexical search, ingestion and tests make no AI calls.

## Tests and rollback

```powershell
python -m pytest -q
node --test tests/frontend.test.cjs
python scripts/audit_deployment.py
```

Use the existing disposable-loopback `TEST_POSTGRES_URL` to include PostgreSQL tests.
Normal tests block external HTTP and use original synthetic references. The 36-query
synthetic benchmark checks expected topics and no-match behavior. Running
`scripts/evaluate_knowledge.py` on the owner corpus measures latency/results, but its
synthetic expected categories are not a valid corpus relevance score. Keep real-source
evaluation metadata under ignored `knowledge_base/` and inspect bounded examples locally.

Rollback: set `KNOWLEDGE_ENABLED=false` through the owner-controlled Render settings,
or revert the Phase 7.5 code commits normally to checkpoint `974d3ca`. Leave private
knowledge tables in place; prior application code ignores them. Never reset the database
or delete learner data. Semantic embeddings, OCR and optional candidate-question authoring
are deferred. Phase 8 has not begun.
