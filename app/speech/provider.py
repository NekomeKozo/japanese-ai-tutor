"""One STT adapter, separate from text generation. Never log payloads."""
import re
from typing import Protocol

import httpx

from app.errors import TutorError

MODEL = 'whisper-large-v3-turbo'


class SpeechProvider(Protocol):
    async def transcribe(self, audio: bytes) -> str: ...


def configuration_issue(settings):
    if not settings.stt_enabled:
        return 'Transcription is disabled on the server. Local recording and preview still work.'
    if not settings.groq_api_key.get_secret_value().strip():
        return 'Transcription is not configured on the server. Local recording and preview still work.'
    return None


def checked_text(text):
    if not isinstance(text, str) or len(text) > 4000 or any(ord(c) < 32 and c not in '\n\t\r' for c in text):
        raise TutorError('invalid_transcript', 'The transcription response could not be read. Please retry.', 502)
    text = text.strip()
    if not text or not re.search(r'[\u3040-\u30ff\u3400-\u9fff]', text):
        raise TutorError('no_speech', 'No recognizable Japanese speech was found. Try recording again.', 422)
    return text


class GroqSpeechProvider:
    def __init__(self, settings, client):
        self.settings, self.client = settings, client

    async def transcribe(self, audio):
        issue = configuration_issue(self.settings)
        if issue:
            raise TutorError('stt_not_configured', issue, 503)
        try:
            # Bound upstream response too; a provider error body is never exposed.
            async with self.client.stream('POST', 'https://api.groq.com/openai/v1/audio/transcriptions',
                    headers={'Authorization': 'Bearer ' + self.settings.groq_api_key.get_secret_value().strip(), 'Accept-Encoding': 'identity'},
                    files={'file': ('recording.wav', audio, 'audio/wav')},
                    data={'model': MODEL, 'language': 'ja', 'response_format': 'verbose_json', 'temperature': '0'},
                    timeout=self.settings.stt_timeout_seconds) as response:
                if response.status_code in (401, 403):
                    raise TutorError('stt_not_configured', 'Check transcription configuration on the server.', 503)
                if response.status_code == 429:
                    raise TutorError('stt_rate_limit', 'The transcription allowance is busy. Please try later.', 429)
                if response.is_error:
                    raise TutorError('stt_failure', 'Transcription could not finish. Your recording is still available; retry later.', 502)
                if response.headers.get('content-encoding', 'identity').lower() != 'identity':
                    raise TutorError('invalid_transcript', 'The transcription response could not be read. Please retry.', 502)
                body = bytearray()
                async for chunk in response.aiter_bytes(chunk_size=8192):
                    if len(body) + len(chunk) > 131072:
                        raise TutorError('invalid_transcript', 'The transcription response could not be read. Please retry.', 502)
                    body.extend(chunk)
        except httpx.TimeoutException:
            raise TutorError('stt_timeout', 'Transcription took too long. Your recording is still here; please retry.', 504) from None
        except httpx.RequestError:
            raise TutorError('stt_unavailable', 'Transcription could not connect. Please try later.', 503) from None
        try:
            import json
            result = json.loads(body)
            segments = result.get('segments', [])
            if not isinstance(segments, list):
                raise ValueError()
            if segments and all(isinstance(s, dict) and isinstance(s.get('no_speech_prob'), (int, float)) and s['no_speech_prob'] >= .9 for s in segments):
                raise TutorError('no_speech', 'No recognizable Japanese speech was found. Try recording again.', 422)
            return checked_text(result['text'])
        except (ValueError, KeyError, TypeError, AttributeError):
            raise TutorError('invalid_transcript', 'The transcription response could not be read. Please retry.', 502) from None
