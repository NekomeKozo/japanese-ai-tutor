# Tutoring provider boundary

Learning services use `LLMProvider.generate(instructions, messages, schema=None)`.
The application factory constructs the selected adapter on a shared HTTPX client
and injects it into tutor, assessment evaluation and generated activity services.
Provider envelopes remain inside `app/llm`; learning logic receives text/JSON and
validates its own Pydantic schemas before saving evidence or replies.

## Adapters and selection

Gemini uses the generateContent REST API with backend-only header credentials,
system instructions and structured JSON output settings. Thought parts are discarded;
incomplete, blocked and malformed responses become safe application failures.
OpenAI uses Responses with structured output and `store=false`. Groq implements
the same transport-independent interface. Provider/model availability depends on the
operator's account; defaults are defined in `app/llm/common.py`, and explicit settings
are preserved rather than overwritten by deployment documentation.

`LLM_PROVIDER` selects Gemini, Groq or OpenAI. Only the configured provider's key
is required unless fallback is deliberately enabled. Unknown providers, missing keys
and unsafe model names produce safe configuration errors; deterministic study can
remain available without working live inference. Changes to settings require restart
or deployment of the actual configured process, not a separate frontend setting.

## Bounded fallback

`FailoverProvider` supports Gemini primary and Groq fallback when configured by
`LLM_FAILOVER_ENABLED` and `LLM_FALLBACK_PROVIDER`. It makes one primary attempt and
at most one fallback within the caller's deadline. Timeout, unavailability, rate-limit
or explicitly classified retryable provider failures can trigger fallback; schema,
refusal and other nonretryable failures must not produce an uncontrolled retry loop.
The request-scoped guard also bounds caller-driven schema repair. A failed fallback
returns a generic unavailable error. No learning service implements its own provider router.

## Validation, context and diagnostics

Adapters check transport envelopes and JSON syntax; application schemas still validate
teaching fields, lengths, observations, scores, topic identities and activity contracts.
Untrusted retrieved reference data is separate from system instructions. Profile/history
and lesson context remain bounded. No model can choose persistence or authorization.

Logs use fixed provider names, route templates, latency and allowlisted error categories;
they do not include keys, headers, request/response bodies, prompt text or vendor error
messages. `/api/health` describes loaded configuration and key presence, not live model
access, quota or output quality. `/health` is the minimal zero-inference liveness endpoint.

To add an adapter, implement the same protocol, register its setting/key field in
`PROVIDERS`, and add mocked transport contract tests. Do not expose SDK-specific types
to learning modules or introduce another token store. Tests use HTTPX MockTransport
and synthetic teaching responses; real-provider checks require intentional authorization
and private configuration. Speech transcription is a separate explicit Groq audio call,
not the tutoring provider fallback mechanism.
