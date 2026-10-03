import asyncio
import io
import struct
import wave
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.errors import TutorError
from app.main import create_app
from app.safeguards import COOKIE, sign_session
from app.speech.audio import MAX_AUDIO_BYTES, validate_audio
from app.speech.provider import GroqSpeechProvider
from app.speech.service import SpeechService


def wav(seconds=.1, silent=False, rate=16000, channels=1):
    output = io.BytesIO()
    with wave.open(output, 'wb') as stream:
        stream.setnchannels(channels)
        stream.setsampwidth(2)
        stream.setframerate(rate)
        stream.writeframes((b'\0\0' if silent else struct.pack('<h', 1000)) * int(seconds * rate) * channels)
    return output.getvalue()


class FakeSpeech:
    def __init__(self):
        self.calls, self.error = [], None
        self.text = 'こんにちは。私の名前はミゲルです。'

    async def transcribe(self, audio):
        self.calls.append(audio)
        if self.error:
            raise self.error
        return self.text


@pytest.fixture
def speech_client(settings, provider):
    settings.stt_enabled = True
    settings.groq_api_key = SecretStr('offline-test-placeholder')
    fake = FakeSpeech()
    with TestClient(create_app(settings, provider, fake), raise_server_exceptions=False) as client:
        learner = client.post('/api/learners').json()['learner_id']
        yield client, fake, learner


def upload(client, learner, audio=None, mime='audio/wav', request_id=None, **headers):
    return client.post(f'/api/learners/{learner}/speech/transcribe', content=wav() if audio is None else audio,
        headers={'content-type': mime, 'x-transcription-id': str(request_id or uuid4()), **headers})


def test_transcript_is_ephemeral_and_does_not_send_tutor_or_create_evidence(speech_client, provider, tmp_path):
    client, fake, learner = speech_client
    before = client.get(f'/api/learners/{learner}/activity').json()
    response = upload(client, learner)
    assert response.status_code == 200, response.text
    assert response.json()['original_text'] == fake.text
    assert response.json()['language'] == 'ja'
    assert response.json()['provider'] == 'groq'
    assert response.json()['duration_seconds'] == .1
    assert client.get(f'/api/learners/{learner}/activity').json() == before
    assert not provider.calls
    assert list(tmp_path.rglob('*.wav')) == []
    assert not hasattr(client.app.state.speech, 'audio')
    assert list(client.app.state.speech.completed.values())[0] > 0  # Only expiry.


@pytest.mark.parametrize('mime', ['audio/wav', 'audio/x-wav', 'audio/wav; codecs=1'])
def test_supported_wav_mime(speech_client, mime):
    client, _, learner = speech_client
    assert upload(client, learner, mime=mime).status_code == 200


@pytest.mark.parametrize('audio,mime,code', [
    (b'', 'audio/wav', 'empty_audio'), (b'not audio', 'audio/wav', 'invalid_audio'),
    (wav()[:-1], 'audio/wav', 'invalid_audio'), (wav() + b'hidden', 'audio/wav', 'invalid_audio'),
    (wav(), 'audio/webm', 'unsupported_audio'), (wav(), 'audio/mp4', 'unsupported_audio'),
    (wav(), 'application/json', 'unsupported_audio'), (wav(61), 'audio/wav', 'audio_too_long'),
    (wav(silent=True), 'audio/wav', 'no_speech'), (wav(rate=8000), 'audio/wav', 'invalid_audio'),
    (wav(channels=2), 'audio/wav', 'invalid_audio'), (wav(0), 'audio/wav', 'empty_audio'),
], ids=['empty','false-wav','truncated','trailing','webm-needs-normalization','mp4-needs-normalization',
        'wrong-mime','long','silent','wrong-rate','stereo','zero-frames'])
def test_invalid_audio_rejected_before_quota_or_provider(speech_client, audio, mime, code):
    client, fake, learner = speech_client
    response = upload(client, learner, audio, mime)
    assert response.json()['error']['code'] == code
    assert not fake.calls
    assert not client.app.state.speech.user_limit.windows


def test_sixty_seconds_allowed_and_wave_sample_header_cannot_hide_length():
    assert validate_audio(wav(60), 'audio/wav') == 60
    data = bytearray(wav()); struct.pack_into('<I', data, 40, 1)
    with pytest.raises(TutorError):
        validate_audio(bytes(data), 'audio/wav')


def test_actual_received_body_bounded_even_with_false_content_length(speech_client):
    client, fake, learner = speech_client
    response = upload(client, learner, b'x' * (MAX_AUDIO_BYTES + 1), **{'content-length': '1'})
    assert response.status_code == 413
    assert not fake.calls
    assert client.post('/api/chat', content=b'x' * 32769).status_code == 413
    assert upload(client, learner).status_code == 200


def test_disabled_and_missing_config_are_safe(speech_client, settings):
    client, fake, learner = speech_client
    settings.stt_enabled = False
    assert not client.get('/api/speech/config').json()['enabled']
    assert upload(client, learner).status_code == 503
    settings.stt_enabled = True; settings.groq_api_key = SecretStr('')
    response = upload(client, learner)
    assert response.json()['error']['code'] == 'stt_not_configured'
    assert not fake.calls


def test_duplicate_and_rate_limits(speech_client, settings):
    client, fake, learner = speech_client
    identifier = uuid4()
    assert upload(client, learner, request_id=identifier).status_code == 200
    assert upload(client, learner, request_id=identifier).status_code == 409
    settings.stt_rate_limit_per_hour = 1
    assert upload(client, learner).status_code == 429
    assert len(fake.calls) == 1


def test_provider_failure_keeps_retry_possible_without_cache(speech_client):
    client, fake, learner = speech_client; identifier = uuid4()
    fake.error = TutorError('stt_failure', 'Please retry.', 502)
    assert upload(client, learner, request_id=identifier).status_code == 502
    assert not client.app.state.speech.pending and not client.app.state.speech.completed
    fake.error = None
    assert upload(client, learner, request_id=identifier).status_code == 200


def test_identifier_validation_and_unknown_learner(speech_client):
    client, fake, learner = speech_client
    assert upload(client, learner, request_id='bad').status_code == 422
    assert upload(client, uuid4()).status_code == 404
    assert not fake.calls


def test_auth_origin_and_ownership_before_upload(settings, provider):
    settings.staging_access_enabled = True
    settings.staging_access_code = SecretStr('offline-access-placeholder')
    settings.staging_session_secret = SecretStr('offline-signing-placeholder-123456789')
    settings.groq_api_key = SecretStr('offline-test-placeholder')
    settings.frontend_url = 'https://tutor.example'
    fake = FakeSpeech()
    with TestClient(create_app(settings, provider, fake)) as client:
        assert upload(client, uuid4()).status_code == 401
        assert client.get('/api/speech/config').status_code == 401
        client.cookies.set(COOKIE, sign_session(str(uuid4()), settings))
        learner = client.post('/api/learners').json()['learner_id']
        assert upload(client, learner, origin='https://evil.example').status_code == 403
        assert upload(client, learner, **{'sec-fetch-site':'cross-site'}).status_code == 403
        assert upload(client, learner, origin='https://tutor.example').status_code == 200
        client.cookies.set(COOKIE, sign_session(str(uuid4()), settings))
        assert upload(client, learner).status_code == 404
        assert len(fake.calls) == 1


def test_total_timeout_and_concurrency_release(settings):
    async def check():
        settings.groq_api_key = SecretStr('offline-test-placeholder')
        class Waiting:
            async def transcribe(self, audio):
                await asyncio.sleep(100)
        service = SpeechService(settings, Waiting())
        first = asyncio.create_task(service.transcribe(identity='one', request_id=uuid4(), audio=wav(), content_type='audio/wav'))
        await asyncio.sleep(0)
        with pytest.raises(TutorError) as duplicate:
            await service.transcribe(identity='one', request_id=uuid4(), audio=wav(), content_type='audio/wav')
        assert duplicate.value.status == 409
        second = asyncio.create_task(service.transcribe(identity='two', request_id=uuid4(), audio=wav(), content_type='audio/wav'))
        await asyncio.sleep(0)
        with pytest.raises(TutorError) as busy:
            await service.transcribe(identity='three', request_id=uuid4(), audio=wav(), content_type='audio/wav')
        assert busy.value.status == 429
        first.cancel(); second.cancel()
        await asyncio.gather(first, second, return_exceptions=True)
        assert not service.pending
        settings.stt_timeout_seconds = .001
        with pytest.raises(TutorError) as timeout:
            await service.transcribe(identity='one', request_id=uuid4(), audio=wav(), content_type='audio/wav')
        assert timeout.value.code == 'stt_timeout'
        assert not service.pending
    asyncio.run(check())


@pytest.mark.parametrize('status,result,expected', [
    (200, {'text':'こんにちは。','segments':[]}, None),
    (200, {'text':'hello'}, 'no_speech'), (200, {'text':''}, 'no_speech'),
    (200, {'text':123}, 'invalid_transcript'), (200, {}, 'invalid_transcript'),
    (200, {'text':'こんにちは。','segments':[{'no_speech_prob':.99}]}, 'no_speech'),
    (401, {'private':'not logged'}, 'stt_not_configured'),
    (429, {'private':'not logged'}, 'stt_rate_limit'), (500, {}, 'stt_failure'),
])
def test_groq_adapter_japanese_multipart_and_sanitized_responses(settings, status, result, expected):
    settings.groq_api_key = SecretStr('offline-test-placeholder')
    def handler(request):
        assert request.url.path == '/openai/v1/audio/transcriptions'
        body = request.read()
        assert b'name="language"\r\n\r\nja' in body
        assert b'whisper-large-v3-turbo' in body
        assert b'filename="recording.wav"' in body
        return httpx.Response(status, json=result)
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            adapter = GroqSpeechProvider(settings, client)
            if expected:
                with pytest.raises(TutorError) as error:
                    await adapter.transcribe(wav())
                assert error.value.code == expected
                assert 'not logged' not in error.value.message
            else:
                assert await adapter.transcribe(wav()) == 'こんにちは。'
    asyncio.run(run())


@pytest.mark.parametrize('failure,code', [(httpx.ReadTimeout('private'), 'stt_timeout'), (httpx.ConnectError('private'), 'stt_unavailable')])
def test_groq_network_failures(settings, failure, code):
    settings.groq_api_key = SecretStr('offline-test-placeholder')
    def handler(request):
        raise failure
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with pytest.raises(TutorError) as error:
                await GroqSpeechProvider(settings, client).transcribe(wav())
            assert error.value.code == code and 'private' not in error.value.message
    asyncio.run(run())


def test_groq_response_is_bounded(settings):
    settings.groq_api_key = SecretStr('offline-test-placeholder')
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r:httpx.Response(200, content=b'x'*131073))) as client:
            with pytest.raises(TutorError, match='could not be read'):
                await GroqSpeechProvider(settings, client).transcribe(wav())
    asyncio.run(run())

def test_confirmed_voice_uses_existing_conversation_replay_without_duplicate_evidence(speech_client, provider):
    from tests.test_conversation import start, body, reply
    client, fake, learner = speech_client
    provider.raw = reply(1)
    state = start(client, learner).json()
    fake.text = '一人です。'
    transcript = upload(client, learner).json()
    assert transcript['original_text'] == '一人です。'
    assert not provider.calls
    saved_url = f'/api/learners/{learner}/sessions/{state["session_id"]}'
    assert client.get(saved_url).json()['interaction_count'] == 0
    # The learner corrects recognition before the existing chat request is sent.
    request = body(learner, state, '二人です。')
    first = client.post('/api/chat', json=request)
    assert first.status_code == 200
    assert client.post('/api/chat', json=request).json() == first.json()
    saved = client.get(saved_url).json()
    assert len(saved['turns']) == saved['interaction_count'] == 1
    assert saved['turns'][0]['message'] == '二人です。'
    assert len(fake.calls) == len(provider.calls) == 1
    with client.app.state.repository.connection() as db:
        assert db.execute("SELECT COUNT(*) FROM learning_events WHERE session_id=? AND event_type='performance'", (state['session_id'],)).fetchone()[0] == 1
    assert client.get(f'/api/learners/{learner}/conversations/active').json()['session_id'] == state['session_id']
    result = client.post(f'/api/learners/{learner}/conversations/{state["session_id"]}/finish').json()
    assert result['recap']['turn_count'] == 1
    assert client.post('/api/chat', json=body(learner, state)).status_code == 409
    assert len(provider.calls) == 1


def test_transcription_failure_and_chat_failure_leave_persistent_scenario_retryable(speech_client, provider):
    from tests.test_conversation import start, body, reply
    client, fake, learner = speech_client
    state = start(client, learner).json()
    fake.error = TutorError('speech_provider_unavailable', 'Try transcription again.', 503)
    assert upload(client, learner).status_code == 503
    assert not provider.calls
    fake.error = None
    assert upload(client, learner).status_code == 200
    request = body(learner, state)
    provider.error = TutorError('provider_unavailable', 'Try the Tutor again.', 503)
    assert client.post('/api/chat', json=request).status_code == 503
    assert client.get(f'/api/learners/{learner}/sessions/{state["session_id"]}').json()['interaction_count'] == 0
    provider.error = None
    provider.raw = reply(1)
    assert client.post('/api/chat', json=request).status_code == 200
    assert client.post('/api/chat', json=request).status_code == 200
    assert client.get(f'/api/learners/{learner}/sessions/{state["session_id"]}').json()['interaction_count'] == 1
    assert len(fake.calls) == 2 and len(provider.calls) == 2
