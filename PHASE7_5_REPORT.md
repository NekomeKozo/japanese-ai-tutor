# Phase 7.5 — Private knowledge and lexical RAG

Status: local implementation complete. Live knowledge import and activation
requires the owner-controlled configuration step; Phase 7.5 is not yet fully accepted.

## Initial audit

Canonical checkout: `C:\Users\MIGUEL PC\Github\japanese-ai-tutor`, clean `main` at
`974d3ca`, remote `NekomeKozo/japanese-ai-tutor`. This is the rollback checkpoint.
Phase 7 is deployed; its actual-phone acceptance remains deferred by the owner.
The initially missing reference folder was subsequently supplied with 33 PDFs.

FastAPI protects `/api/chat` before TutorService restores history, constructs teaching
instructions and learner context, calls LLMProvider, validates structured output and
saves evidence. Teaching rules live in tutor/prompts.py; bounded learner context lives
in learner/context.py. Gemini and Groq share one interface; eligible failover is limited
to one fallback, with no refusal/configuration bypass. The knowledge service fits before
this wrapper and does not change provider adapters.

SQLite and psycopg already support transactional storage; PostgreSQL uses the private
tutor_private schema. Learner migrations v1–v5 remain unchanged. Knowledge has independent
additive versioning. Existing Pydantic, asyncio and database dependencies are reused.
No embedding integration or pgvector setup exists in the project; live extension
availability is unverified. A lexical baseline avoids a new account, extension, embedding
cost or deployment dependency. PDF parsing is an explicit administrative dependency.

## Inventory and extraction

33 PDFs, approximately 390 MiB. Preliminary five-page sampling detected text in 29,
little/no text in three and encryption in one. The complete bounded build indexed 29
sources: 28 extracted, one partial. Two sources had no usable text, one was encrypted
and one exceeded the 150 MiB safety limit. The local manifest contains private details;
no filenames or source text are included in this report.

Supported: text PDF, UTF-8 TXT and Markdown. Unsupported scans are marked for OCR;
no OCR or encryption bypass is implemented. pypdf 6.18.1 is installed separately for
administrative ingestion/testing, not needed by the web process. Extraction failures
are isolated. Source metadata, stable IDs, conservative NFC normalization, page provenance,
paragraph/sentence chunking, hard bounds and deduplication are implemented with typed
schemas. Inferred categories are explicitly separate from supplied metadata. Default
chunk size is 1,000 characters. Titles, chapters, editions and levels are not fabricated.

## Storage, retrieval and tutor integration

Separate source, chunk and term-posting tables provide indexed candidate retrieval.
Local builds use ignored SQLite; the explicit import utility can populate the existing
private PostgreSQL schema with derived records only. Atomic per-source replacement
preserves unrelated sources and all learner records; empty/failed extraction preserves
the previous successful version. Obsolete chunks of a rebuilt source are removed inside
that transaction. Missing source files are not automatically pruned.

English words, Japanese bigrams/trigrams and separated single characters support the
lexical baseline. Phrase/boundary and density ranking, filters, minimum relevance,
bounded candidates and duplicate suppression constrain context. Semantic retrieval is
explicitly deferred pending evidence of benefit. Initial real-corpus sampling exposed
grammar suffix matches in vocabulary lists; ranking was tightened rather than treating
the synthetic benchmark as proof of real-source quality.

The knowledge service runs database work off the async request loop, retrieves once,
and bounds context to 6,000 UTF-8 bytes/top three results by default. It skips greetings
and correction mode. Retrieval failure/no-match falls back to ordinary tutoring.
Sources remain untrusted data in a separate message. Explicit synthesis rules,
instruction-like-chunk filtering, source-dump request rejection and an output copying
check run before saved conversation/evidence commits. This is layered mitigation, not
a formal guarantee against all prompt injection or reconstruction attacks.

No raw-reference API, learner-visible chunk browser, frontend redesign, live question
generation, learner scoring/scheduling changes, or provider-specific RAG path was added.
No reference messages are stored in chat history. The UI receives the existing response
schema and does not claim grounding when retrieval fails. Internal typed context retains
source/page provenance; compact learner-facing citations are deferred.

## Files and dependencies

Added: app/knowledge/{schemas,extractors,normalize,chunker,terms,repository,service}.py,
administrative inventory/build/search/evaluate/import scripts, original synthetic fixtures,
knowledge tests, requirements-knowledge.txt and docs/knowledge.md.
Modified: config.py, main.py, tutor/service.py, .env.example, test_postgres.py,
requirements-dev.txt, CI workflow and README. Existing learner migrations, provider
adapters and Phase 7 frontend remain unchanged. Runtime parsing is not added.

## Verification

First full regression: **444 passed**, including disposable PostgreSQL integration;
two existing dependency deprecation warnings. Additional corpus-ranking and extraction
tests were then added. Tests use authored fixtures and fake providers,
with external HTTP blocked. No live provider quota was consumed by these checks.

Final full regression: **448 passed** (29 additional cases over Phase 7), including
real disposable PostgreSQL migration, rollback and learner-schema preservation.
All **15 frontend tests** passed; JavaScript/Python syntax checks, Git whitespace check
and source/available-history privacy audit passed. The two dependency warnings remain.

Synthetic benchmark: 36 queries spanning grammar, particles, conjugation, adjectives,
vocabulary, kanji/readings, kana and no-match cases. All 33 expected topics appeared
in the top three; all three no-match cases returned empty and no duplicates appeared.
These synthetic results do not establish real-reference answer quality.

The private index contains **29 sources, 943 chunks and 143,665 postings** (about
25.7 MiB locally). A repeat build skipped all 29 unchanged sources and kept identical
counts. Import dry-run found the expected 29 sources and made no network/database writes.
The 36-query real-corpus run had 32 nonempty results, three correct no-match cases,
no duplicate results, about **5.9 ms median / 26.4 ms maximum** local retrieval time.
These are retrieval observations, not an accuracy score. Bounded manual spot checks
found relevant evidence within the top three for desire, particle contrast, ながら,
て-form, 時間, たり and 学校 readings; some first results remained broad or partial.
Neither model answer quality nor remote PostgreSQL retrieval latency is yet verified.

Live activation/import, grounded Gemini answers and persisted-state checks after that
deployment remain pending. No Render/Supabase dashboard settings or secrets have changed.
The local environment has no configured PostgreSQL connection. Import requires the
owner to supply the existing connection privately; its value was not requested in chat.
No pgvector or additional service is needed. Follow docs/knowledge.md for the explicit
import, owner activation, safe rebuild and rollback steps.

## Limits and costs

PDF reading order, furigana and multi-topic pages remain imperfect; text extraction is
not OCR-quality validation. Four sources are not indexed. Lexical search misses some
paraphrases and may retrieve incidental topic mentions. No claim of calibrated relevance
or complete coverage is made. The web path uses a bounded retrieval deadline and ordinary
tutoring fallback. Bulk import can briefly contend with the existing database lock.
Ingestion/retrieval consume no LLM quota; added provider context consumes normal input
tokens. Embeddings, OCR and candidate question authoring are deferred.

Rollback checkpoint: `974d3ca`. Disable optional knowledge through the owner-controlled
setting or normally revert Phase 7.5 commits; retain additive tables and all learner data.
Never force-push or reset the database. **Phase 8 has not begun.**
