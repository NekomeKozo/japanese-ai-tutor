# JLPT practice bank and operations

The shipped `jlpt-v1` bank has 40 N5 and 40 N4 questions: 10 vocabulary, 10 kanji,
10 grammar and 10 reading at each level. All are original application-authored
content reviewed during implementation. This is an initial practice bank, not an
official exam specification, a calibrated proficiency test, or an independently
teacher-reviewed curriculum. Expand coverage after editorial review, especially
vocabulary, grammar, contextual readings and longer reading material.

## Authoring lifecycle

Only `approved` items in `app/jlpt/data/n5.json` and `n4.json` are served. Keep IDs
stable. Candidate and reviewed states are not playable. Retire unsuitable items;
do not reuse their IDs for unrelated questions. Increment the item version and bank
version for published content changes. Existing sessions retain full snapshots,
so changes cannot rewrite their questions, answers or explanations.

Before approval, review Japanese naturalness, level suitability, a single clear
correct answer, plausible but unambiguously incorrect distractors, explanation
accuracy, canonical topic and mastery-dimension mapping, contextual on/kun readings,
passage completeness, and originality. Check duplicates against both levels. Never
copy official questions, commercial exercises or private reference passages.

Validate with `python -m pytest -q tests/test_jlpt.py` and the complete regression
suite before publishing. Startup also validates the bank. Deploy normal reviewed
Git changes to the existing service; no new environment setting is required.

## Optional private RAG-assisted candidates

In an existing development environment with private knowledge retrieval configured:

```sh
python scripts/author_jlpt_candidate.py --level N5 --section grammar --topic particle_ni_destination
```

Use an actual canonical topic ID from `app/learner/catalog.py`. This is an explicit
operator action that calls the configured provider. It is disabled outside
development, requires usable retrieved context, treats retrieved text as untrusted,
checks copying and duplicates, and saves only a private candidate under ignored
`knowledge_base/jlpt_candidates/`. Nothing is automatically approved or published.
The saved provenance describes retrieved chunks and the configured provider/model;
it does not prove which provider handled a fallback request. Editorial review and
a separate bank edit are required before publication. Keep candidate files private.

## Persistence, timing and recovery

Schema 7 adds three JLPT tables and the required new topic identities without replacing
existing learner data. Startup also fills missing authored JLPT topics in an already-upgraded
schema-7 database, without overwriting existing topic metadata. A learner
has at most one active JLPT session. Request identifiers make retried starts and
answers idempotent. Questions, selected order and deadlines are stored on the server.
Unsubmitted text survives section navigation, but reload restores submitted answers
only. Finishing early counts unanswered questions as incorrect. Abandonment retains
history and does not produce a score; already submitted practice evidence remains.

The optional timer allocates 60 seconds per non-reading question and 120 per reading
question. These are app study budgets, not official exam timings. Expired sessions
finish on the next server interaction; a background worker is not required.
Mock feedback and learning evidence remain withheld until completion. Abandoned
mock answers never become performance evidence.

Retain additive tables during rollback. Verify that the selected application
release accepts the current schema and topic definitions; do not deploy an older
incompatible authorizer or destructively downgrade the database. Preserve sessions,
answer snapshots and learner history. Use normal reviewed release operations without
rewriting Git history. See [deployment](deployment.md).
