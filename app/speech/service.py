import asyncio
import time

from app.errors import TutorError
from app.safeguards import WindowLimiter
from app.speech.audio import validate_audio
from app.speech.provider import checked_text, configuration_issue
from app.speech.schemas import Transcript


class SpeechService:
    def __init__(self, settings, provider):
        self.settings, self.provider = settings, provider
        self.user_limit, self.hour_limit, self.day_limit = WindowLimiter(), WindowLimiter(), WindowLimiter()
        self.minute_limit = WindowLimiter()
        self.pending = set()
        self.completed = {}

    async def transcribe(self, *, identity, request_id, audio, content_type):
        issue = configuration_issue(self.settings)
        if issue:
            raise TutorError('stt_not_configured', issue, 503)
        now = time.monotonic()
        self.completed = {key:expiry for key, expiry in self.completed.items() if expiry > now}
        key = (identity, str(request_id))
        if identity in self.pending or key in self.completed:
            raise TutorError('duplicate_transcription', 'This transcription was already requested. Review the text or retry explicitly.', 409)
        if len(self.pending) >= 2 or len(self.completed) >= 2000:
            raise TutorError('stt_busy', 'Transcription is busy. Your recording is still here; try shortly.', 429)
        self.pending.add(identity)
        try:
            duration = validate_audio(audio, content_type)
            self.user_limit.take(identity, self.settings.stt_rate_limit_per_hour)
            self.minute_limit.take('all', 10, 60)
            self.hour_limit.take('all', self.settings.stt_global_rate_limit_per_hour)
            self.day_limit.take('all', self.settings.stt_global_rate_limit_per_day, 86400)
            # Total deadline covers slow streaming, not just time between packets.
            try:
                text = await asyncio.wait_for(self.provider.transcribe(audio), self.settings.stt_timeout_seconds)
            except TimeoutError:
                raise TutorError('stt_timeout', 'Transcription took too long. Please retry.', 504) from None
            result = Transcript(request_id=request_id, original_text=checked_text(text), duration_seconds=duration)
            self.completed[key] = now + 600  # IDs only, no transcript/audio cache.
            return result
        finally:
            self.pending.discard(identity)
