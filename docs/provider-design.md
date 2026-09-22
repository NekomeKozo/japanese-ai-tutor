# Provider integration (Phase 4.5)

Learning services → existing `LLMProvider.generate` protocol → selected REST adapter.
`create_app` creates one shared provider and injects it into tutor, assessment evaluation,
and curriculum content/evaluation. Learner memory only consumes validated application data.
There is no second LLM service, per-prompt method family, fallback router or UI change.

`generate(instructions, messages, schema=None)` accepts application-owned messages and
returns a string. With a schema, adapters request JSON and check JSON syntax. The caller
still validates its own Pydantic schema, length limits and learning-specific rules before
saving data. Without a schema the same method returns plain text. Business logic never
sees provider envelopes, SDK objects, thought parts or provider-specific role names.

Gemini maps assistant turns to `model`, instructions to `systemInstruction`, and JSON
schema to `generationConfig.responseJsonSchema` with the JSON MIME type. It uses the
official `v1beta/models/{model}:generateContent` REST endpoint, sends its key only in the
`x-goog-api-key` header, and discards thought parts. Completed text requires `STOP`;
truncation and safety blocks are errors. The default is Gemini 3.1 Flash-Lite, verified
live through the running tutor. Explicit Gemini 2.5 Flash configurations retain their
legacy thinking-budget setting, but it is no longer the default or example model.
Other explicitly chosen models receive no thinking override and may need a larger
configured output budget.

OpenAI retains Responses, strict JSON schema, unchanged role/instruction mapping and
`store=false`; plain text uses the same endpoint. Its default remains `gpt-4.1-mini`.
No API key, database, dependency, or curriculum change is needed to switch adapters.

The factory selects only the configured provider, normalizing case/outer whitespace.
Unknown providers, unsafe model IDs and missing selected keys produce safe setup messages.
The server and deterministic learning features still start without a configured provider.
Health checks configuration presence only, not live connectivity, quota or model access.
Provider failures use existing `TutorError` categories: configuration, missing key, auth,
rate limit, timeout, unavailable, failure, incomplete, refusal, or invalid model response.
Gemini may report invalid keys as HTTP 400; this uses the safe generic failure category.
Logs include adapter/model names, HTTP status, allowlisted provider error categories/reasons
and API route templates, never raw vendor messages, exception text, credentials,
headers, request bodies, generated text or prompt contents. Startup logs show the working
directory and application-relative environment-file path. Health reports the loaded
provider/model and key-presence boolean. Do not enable HTTP wire-debug
logging when using real learner data.

Transport calls do not retry or switch provider. Existing caller-controlled lesson
schema repair remains as before. Tutor history and learner/lesson context limits are
unchanged; switching adapters only changes the wire envelope. No new learner data is sent.

To add a provider, implement the same protocol in `app/llm`, add a secret setting, register
the adapter/key field in `PROVIDERS`, update the setup message/examples, and add mocked
transport contract tests. Keep SDK/API formats entirely inside that adapter. Future fallback
could implement the existing protocol without changing learning services; none is enabled.

Offline tests reuse `tests.conftest.MockProvider` and HTTPX `MockTransport`; the test fixture
blocks HTTPX's real sync/async transports. No real-provider quality or account-access claim
is made by those tests. Separate live verification with the locally configured key is
documented in `PHASE4_5_RUNTIME_REPORT.md`; it is not part of the automated test suite.

Official references checked for this implementation:

- [Gemini generateContent REST reference](https://ai.google.dev/api/generate-content)
- [Gemini structured outputs](https://ai.google.dev/gemini-api/docs/generate-content/structured-output)
- [Gemini thinking controls](https://ai.google.dev/gemini-api/docs/generate-content/thinking)
- [Gemini 2.5 Flash capabilities](https://ai.google.dev/gemini-api/docs/models/gemini-2.5-flash)
- [OpenAI structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs)
