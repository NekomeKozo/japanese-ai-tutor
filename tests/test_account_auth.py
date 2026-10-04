"""Provider verification is mocked; no real Auth users, emails or token exchanges."""
import asyncio
import base64
from dataclasses import FrozenInstanceError
import hashlib
import hmac
import json
import time
from uuid import UUID, uuid4

import httpx
import pytest
from pydantic import SecretStr, ValidationError

from app.auth import AuthenticationError, SupabaseAccountVerifier
from app.config import Settings
from app.safeguards import COOKIE
from tests.test_staging import gated, login

ORIGIN = 'https://test-project.supabase.co'
KEY = 'sb_publishable_test-not-a-real-key'
FAKE_SIGNING = b'offline-provider-mock-only'


def part(value):
    raw = value if isinstance(value, str) else json.dumps(value)
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip('=')


def claims():
    now = int(time.time())
    return dict(iss=ORIGIN+'/auth/v1', aud='authenticated', role='authenticated',
                sub=str(uuid4()), session_id=str(uuid4()), is_anonymous=False,
                iat=now-60, exp=now+3600)


def token(payload=None, header=None):
    unsigned = part(header or {'typ':'JWT','alg':'HS256'})+'.'+part(payload or claims())
    signature = base64.urlsafe_b64encode(hmac.new(FAKE_SIGNING,unsigned.encode(),hashlib.sha256).digest()).decode().rstrip('=')
    return unsigned+'.'+signature


def auth_settings(**changes):
    return Settings(_env_file=None, supabase_auth_url=ORIGIN,
                    supabase_auth_publishable_key=SecretStr(KEY), **changes)


def user_for(payload):
    return {'id':payload['sub'],'email':'test@example.test','is_anonymous':False,
            'email_confirmed_at':'2026-01-01T00:00:00Z'}


def verify(value, handler, settings=None):
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=True) as client:
            return await SupabaseAccountVerifier(settings or auth_settings(),client).verify(value)
    return asyncio.run(run())


def test_disabled_defaults_and_configuration():
    config = Settings(_env_file=None)
    assert config.account_auth_enabled is False
    assert not config.supabase_auth_url
    assert not config.supabase_auth_publishable_key.get_secret_value()
    with pytest.raises(AuthenticationError) as caught:
        SupabaseAccountVerifier(config, object())
    assert caught.value.status == 503
    for value in [True, 'true']:
        with pytest.raises(ValidationError,match='activation is unavailable'):
            auth_settings(account_auth_enabled=value)
    assert auth_settings(account_auth_enabled='false').account_auth_enabled is False
    assert KEY not in repr(auth_settings())


@pytest.mark.parametrize('url',[
    'https://attacker.example','http://test-project.supabase.co',
    'https://test-project.supabase.co.attacker.example','https://user:password@test-project.supabase.co',
    ORIGIN+'/auth/v1',ORIGIN+'?token=secret',ORIGIN+'#fragment',ORIGIN+':bad',
    'https://[broken',ORIGIN+':444','https://test-project.\tsupabase.co',
])
def test_bad_or_redirectable_config_origins(url):
    with pytest.raises(ValidationError):
        Settings(_env_file=None,supabase_auth_url=url,supabase_auth_publishable_key=KEY)


@pytest.mark.parametrize('key',['','sb_secret_test-not-a-real-key',token({'role':'service_role'}),'x\r\napikey:evil'])
def test_missing_and_privileged_config_keys(key):
    with pytest.raises(ValidationError):
        Settings(_env_file=None,supabase_auth_url=ORIGIN,supabase_auth_publishable_key=key)


def test_partial_local_and_staging_configuration():
    with pytest.raises(ValidationError):
        Settings(_env_file=None,supabase_auth_publishable_key=KEY)
    local = Settings(_env_file=None,supabase_auth_url='http://127.0.0.1:54321/',supabase_auth_publishable_key=KEY)
    assert local.supabase_auth_url == 'http://127.0.0.1:54321'
    with pytest.raises(ValidationError):
        Settings(_env_file=None, environment='staging',supabase_auth_url=local.supabase_auth_url,
                 supabase_auth_publishable_key=KEY)


def test_valid_online_verification_returns_immutable_minimal_identity():
    payload = claims()
    value = token(payload)
    calls=[]
    def authority(request):
        calls.append(request)
        assert str(request.url) == ORIGIN+'/auth/v1/user'
        assert request.method == 'GET'
        assert request.headers['apikey'] == KEY
        assert request.headers['authorization'] == 'Bearer '+value
        assert not request.content
        return httpx.Response(200,json=user_for(payload))
    account = verify(value,authority)
    assert account.account_id == UUID(payload['sub'])
    assert account.provider_session_id == UUID(payload['session_id'])
    assert account.expires_at == payload['exp']
    assert len(calls)==1
    assert not hasattr(account,'email') and not hasattr(account,'learner_id')
    assert value not in repr(account) and KEY not in repr(account)
    with pytest.raises(FrozenInstanceError): account.account_id=uuid4()


@pytest.mark.parametrize('change',[
    {'iss':'https://other-project.supabase.co/auth/v1'},{'aud':'service_role'},
    {'aud':['authenticated','other']},{'role':'service_role'},{'is_anonymous':True},
    {'is_anonymous':None},{'sub':'browser-provided-id'},{'sub':str(uuid4()).upper()},
    {'session_id':'not-a-session'},{'exp':0},{'exp':True},{'exp':'99999999999'},
    {'iat':None},{'iat':99999999999},{'nbf':99999999999},{'nbf':False},
])
def test_ineligible_claims_never_reach_provider(change):
    payload=claims();payload.update(change)
    def forbidden(request): raise AssertionError('Should reject before any network request')
    with pytest.raises(AuthenticationError) as caught: verify(token(payload),forbidden)
    assert caught.value.status==401


@pytest.mark.parametrize('value',[
    '',None,'garbage','Bearer '+token(),'a.b.c','x'*16385,
    part({'typ':'JWT','alg':'none'})+'.'+part(claims())+'.sig',
    part({'typ':'JWT','alg':'HS512'})+'.'+part(claims())+'.sig',
    part({'typ':'JWT','alg':'HS256'})+'.'+part('{"iss":"one","iss":"two"}')+'.sig',
    part({'typ':'JWT','alg':'HS256'})+'.'+part([])+'.sig',
], ids=['empty','missing','garbage','bearer-prefix','bad-json','oversized','unsigned','wrong-alg','duplicate-claims','array-claims'])
def test_malformed_and_unsigned_tokens_are_rejected(value):
    with pytest.raises(AuthenticationError):
        verify(value,lambda request: pytest.fail('No network for malformed token'))


def test_signature_tampering_is_rejected_by_provider_not_decoding():
    payload=claims(); original=token(payload)
    # All local eligibility checks still pass; only the signature authority detects this.
    changed=dict(payload,sub=str(uuid4()))
    tampered=original.split('.')[0]+'.'+part(changed)+'.'+original.split('.')[2]
    calls=[]
    def authority(request):
        calls.append(request)
        supplied=request.headers['authorization'].removeprefix('Bearer ')
        unsigned,signature=supplied.rsplit('.',1)
        expected=base64.urlsafe_b64encode(hmac.new(FAKE_SIGNING,unsigned.encode(),hashlib.sha256).digest()).decode().rstrip('=')
        return httpx.Response(401) if not hmac.compare_digest(signature,expected) else httpx.Response(200,json=user_for(payload))
    with pytest.raises(AuthenticationError) as caught: verify(tampered,authority)
    assert caught.value.status==401 and len(calls)==1


@pytest.mark.parametrize('status,expected',[(401,401),(403,401),(429,503),(500,503),(302,503)])
def test_provider_errors_are_generic_and_redirects_never_followed(status,expected,caplog):
    value=token();calls=[]
    def handler(request):
        calls.append(request)
        return httpx.Response(status,text='PRIVATE_PROVIDER_BODY',headers={'Location':'https://attacker.example'})
    with pytest.raises(AuthenticationError) as caught: verify(value,handler)
    assert caught.value.status==expected and len(calls)==1
    assert all(secret not in str(caught.value)+caplog.text for secret in [value,KEY,'PRIVATE_PROVIDER_BODY'])


@pytest.mark.parametrize('override',[
    {'id':str(uuid4())},{'is_anonymous':True},{'email_confirmed_at':None},
    {'email_confirmed_at':'2099-01-01T00:00:00Z'},{'email_confirmed_at':'2026-01-01'},
    {'email':None},
])
def test_unverified_or_mismatched_provider_identity(override):
    payload=claims();user=user_for(payload);user.update(override)
    with pytest.raises(AuthenticationError): verify(token(payload),lambda request:httpx.Response(200,json=user))


@pytest.mark.parametrize('body',['not json','[]','{}','x'*65537],ids=['not-json','array','empty-object','oversized'])
def test_malformed_and_oversized_provider_response(body):
    with pytest.raises(AuthenticationError): verify(token(),lambda request:httpx.Response(200,text=body))


def test_timeout_and_expiry_while_verifying(monkeypatch):
    def timeout(request): raise httpx.ReadTimeout('PRIVATE_DETAIL',request=request)
    with pytest.raises(AuthenticationError) as caught: verify(token(),timeout)
    assert caught.value.status==503 and 'PRIVATE' not in str(caught.value)
    payload=claims()
    def handler(request):
        monkeypatch.setattr('app.auth.time.time',lambda:payload['exp']+1)
        return httpx.Response(200,json=user_for(payload))
    with pytest.raises(AuthenticationError) as caught: verify(token(payload),handler)
    assert caught.value.status==401


def test_concurrent_account_contexts_do_not_leak():
    first,second=claims(),claims();values=[token(first),token(second)]
    users={value:user_for(payload) for value,payload in zip(values,[first,second])}
    async def run():
        async def authority(request):
            await asyncio.sleep(0)
            return httpx.Response(200,json=users[request.headers['authorization'].removeprefix('Bearer ')])
        async with httpx.AsyncClient(transport=httpx.MockTransport(authority)) as client:
            verifier=SupabaseAccountVerifier(auth_settings(),client)
            return await asyncio.gather(*(verifier.verify(value) for value in values))
    results=asyncio.run(run())
    assert [str(result.account_id) for result in results]==[first['sub'],second['sub']]


def test_preparation_cannot_bypass_gate_or_assign_legacy_ownership(gated,settings,provider):
    settings.supabase_auth_url=ORIGIN
    settings.supabase_auth_publishable_key=SecretStr(KEY)
    legacy_cookie=login(gated)
    learner=gated.post('/api/learners').json()['learner_id']
    before=gated.get(f'/api/learners/{learner}/profile').json()
    with gated.app.state.repository.connection() as db:
        owner_before=db.execute('SELECT * FROM staging_resources ORDER BY kind,resource_id').fetchall()
        tables_before=db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
    for route in ['/api/auth/login','/api/auth/register','/api/auth/me']:
        assert gated.get(route).status_code==404
    assert gated.post('/api/auth/register',json={'email':'test@example.test'}).status_code==404
    # A verified provider identity alone still has NO current application privileges.
    payload=claims();value=token(payload)
    assert str(verify(value,lambda request:httpx.Response(200,json=user_for(payload))).account_id)==payload['sub']
    gated.cookies.clear()
    assert gated.get(f'/api/learners/{learner}/profile',headers={'Authorization':'Bearer '+value}).status_code==401
    for route in ['/api/auth/login','/api/auth/register','/api/auth/me']:
        assert gated.get(route).status_code==401
    login(gated)
    assert gated.get(f'/api/learners/{learner}/profile').status_code==404
    gated.cookies.clear();gated.cookies.set(COOKIE,legacy_cookie)
    assert gated.get(f'/api/learners/{learner}/profile').json()==before
    with gated.app.state.repository.connection() as db:
        assert db.execute('SELECT * FROM staging_resources ORDER BY kind,resource_id').fetchall()==owner_before
        assert db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()==tables_before
    assert not provider.calls
