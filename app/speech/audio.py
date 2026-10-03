"""Bounded PCM WAV validation. No decoder, filesystem or client duration trust."""
import struct

from app.errors import TutorError

MAX_AUDIO_BYTES = 2 * 1024 * 1024
MAX_SECONDS = 60


def validate_audio(audio: bytes, content_type: str) -> float:
    if not audio:
        raise TutorError('empty_audio', 'No audio was received. Record a short Japanese sentence.', 422)
    if len(audio) > MAX_AUDIO_BYTES:
        raise TutorError('audio_too_large', 'The audio upload is too large. Record a shorter sentence.', 413)
    if content_type.split(';')[0].strip().lower() not in ('audio/wav', 'audio/x-wav'):
        raise TutorError('unsupported_audio', 'Transcription needs a WAV recording prepared by GoiGrow. Try recording again.', 415)
    invalid = TutorError('invalid_audio', 'This recording could not be read. Record again or try another browser.', 422)
    if len(audio) < 44 or audio[:4] != b'RIFF' or audio[8:12] != b'WAVE':
        raise invalid
    if struct.unpack_from('<I', audio, 4)[0] != len(audio) - 8:
        raise invalid
    offset, fmt, samples, count = 12, None, None, 0
    while offset < len(audio):
        count += 1
        if offset + 8 > len(audio) or count > 32:
            raise invalid
        kind = audio[offset:offset + 4]
        size = struct.unpack_from('<I', audio, offset + 4)[0]
        start, end = offset + 8, offset + 8 + size
        if end + (size % 2) > len(audio):
            raise invalid
        if kind == b'fmt ':
            if fmt is not None or size != 16:
                raise invalid
            fmt = struct.unpack_from('<HHIIHH', audio, start)
        elif kind == b'data':
            if samples is not None or fmt is None or size % 2:
                raise invalid
            samples = memoryview(audio)[start:end]
        else:
            # The frontend emits just fmt/data; reject metadata or hidden tracks.
            raise invalid
        offset = end + size % 2
    if fmt != (1, 1, 16000, 32000, 2, 16) or samples is None:
        raise invalid
    duration = len(samples) / 32000
    if duration < .01:
        raise TutorError('empty_audio', 'No audio was recorded. Try a little longer.', 422)
    if duration > MAX_SECONDS:
        raise TutorError('audio_too_long', 'Record no more than 60 seconds.', 422)
    # Reject digital silence before spending provider quota. This is not a score.
    if not any(abs(value[0]) > 16 for value in struct.iter_unpack('<h', samples)):
        raise TutorError('no_speech', 'No audible speech was found. Try a short Japanese sentence.', 422)
    return duration
