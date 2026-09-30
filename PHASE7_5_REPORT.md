# Phase 7.5 — Private knowledge and lexical RAG

Status: Phase 7.5 lexical RAG implemented, deployed and verified on live staging.
Actual-phone acceptance remains deferred by the owner; browser mobile-width checks passed.

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
Published implementation checkpoint: `e24569b`. GitHub Actions also passed:
https://github.com/NekomeKozo/japanese-ai-tutor/actions/runs/36554475987.
After publication, live `/health` returned 200 and unauthenticated `/api/health`
and protected static resources returned 401. This verifies service/access availability,
not live grounded tutoring or the exact Render deployment revision.

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
Live answer spot checks are recorded below; these are not a calibrated quality score.

On 2026-09-29, after the owner configured the existing database connection privately,
the explicit importer populated **29 sources, 943 chunks and 143,665 postings** in
the existing PostgreSQL database. Raw PDFs and the local inventory were not uploaded.
Three positive sample queries and one no-match query returned the same chunk/page
provenance as the local index. Remote lookup times from this machine were **1.31–1.97 s**;
the bounded knowledge service returned `available` with a 1,743-byte context. These
include connection latency and do not measure latency from Render itself.

Learner schema version remained 5 and the learner count remained three. Database
permission checks showed both `anon` and `authenticated` had neither schema USAGE
nor SELECT on knowledge_chunks. No learner tables were modified by the importer.

The owner enabled retrieval and redeployed. Live verification on 2026-09-29/30 found
that knowledge INFO diagnostics did not inherit Uvicorn's deployment handler. Commit
`b618765` fixes that using the same logger hierarchy as provider diagnostics, without
enabling source bodies or request logging. Its regression test verifies visible safe
metadata under the deployment logging levels. All 29 focused knowledge tests passed.
GitHub Actions then passed **449 backend tests and 15 frontend tests**, including
PostgreSQL integration and the privacy audit (three CI dependency warnings):
https://github.com/NekomeKozo/japanese-ai-tutor/actions/runs/36584623395.
Render Events confirmed `b618765` live on 2026-09-29.

Signed-in N5 placement confidence (49%), the existing 30-minute/five-activity study
plan and prior conversation survived deployment. The conversation also restored on
the following day after the free instance woke up. Grammar, vocabulary and school
kanji-reading answers succeeded. A fresh grammar request logged `available`, one
result and 1,582 ms retrieval latency. Vocabulary and kanji-reading requests each
retrieved three records in 1,101 ms and 1,099 ms respectively. Safe provider logs
confirmed Gemini handled the live requests. Answers were brief explanations/examples,
not source-page reproductions.

An English question about rendaku logged `no_match`, zero records and 935 ms lookup
time; tutoring still returned an explanation without claiming reference support.
Its main bookcase example was useful, but an additional clock example was misleading.
This is a concrete limitation of ungrounded generation; successful fallback is not
proof of answer accuracy. The tutor acknowledged and corrected the example when asked
in the same conversation. Generation quality remains a documented limitation.

The live tutor rejected a textbook-page request and an unrelated coding request.
Live `/health` returned 200; unauthenticated API, private-reference and index paths
returned 401. Render logs also confirmed the signed-in index-file request returned
404. Automated checks cover absence of all four reference/index/book/chunk routes.
No Render/Supabase dashboard settings were changed by the agent. The connection
value was neither printed nor requested in chat.
No pgvector or additional service is needed. Follow docs/knowledge.md for the explicit
import, owner activation, safe rebuild and rollback steps.

At a 390 x 844 browser viewport, the tutor composer, send button and bottom navigation
remained reachable with no horizontal overflow. Home navigation also worked at this
width. This is desktop browser emulation, not an actual-phone/soft-keyboard test.
No Phase 7 frontend or learning algorithm changes were needed. Groq compatibility and
single-retrieval failover were verified with fake providers; live quota exhaustion was
not induced. Phase 7.5 stops here, with semantic retrieval, OCR and phone verification
explicitly deferred as described above.

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
