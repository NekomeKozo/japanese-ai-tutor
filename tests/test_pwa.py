import base64
import hashlib
import json
import re
import struct

from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.main import create_app
from app.web_assets import PWA_PUBLIC_PATHS


def test_manifest_icons_and_apple_metadata(client):
    response = client.get('/manifest.webmanifest')
    assert response.status_code == 200
    assert response.headers['content-type'].startswith('application/manifest+json')
    assert response.headers['cache-control'] == 'no-store'
    manifest = response.json()
    assert manifest['name'] == 'GoiGrow — Japanese Tutor'
    assert manifest['short_name'] == 'GoiGrow'
    assert manifest['description'] == 'A little, every day. Your Japanese learning companion.'
    assert (manifest['id'],manifest['start_url'],manifest['scope']) == ('/','/#home','/')
    assert (manifest['display'],manifest['orientation'],manifest['lang']) == ('standalone','any','en')
    assert manifest['theme_color'] == '#285d4e'
    assert manifest['background_color'] == '#f5f6f1'
    assert {icon['purpose'] for icon in manifest['icons']} == {'any','maskable'}
    for icon in manifest['icons']:
        image = client.get(icon['src'])
        size = tuple(map(int,icon['sizes'].split('x')))
        assert image.content[:8] == b'\x89PNG\r\n\x1a\n'
        assert struct.unpack('>II',image.content[16:24]) == size
        assert image.headers['content-type'] == 'image/png'
        assert 'immutable' in image.headers['cache-control']
    apple = client.get('/static/pwa/apple-touch-icon.png')
    assert struct.unpack('>II',apple.content[16:24]) == (180,180)
    assert client.get('/favicon.ico').headers['content-type'] == 'image/x-icon'
    for url in ['/','/access']:
        html = client.get(url).text
        assert 'rel="manifest" href="/manifest.webmanifest"' in html
        assert 'rel="apple-touch-icon"' in html
        assert 'name="apple-mobile-web-app-capable" content="yes"' in html
        assert 'viewport-fit=cover' in html


def test_worker_scope_integrity_and_exact_public_paths(settings, provider):
    settings.staging_access_enabled = True
    settings.staging_access_code = SecretStr('pwa-test-access-code')
    settings.staging_session_secret = SecretStr('pwa-test-signing-secret-at-least-32')
    with TestClient(create_app(settings, provider)) as client:
        for path in PWA_PUBLIC_PATHS:
            result = client.get(path)
            assert result.status_code == 200, path
            assert 'set-cookie' not in result.headers
            assert 'frame-ancestors' in result.headers['content-security-policy']
        worker = client.get('/service-worker.js')
        assert worker.headers['content-type'].startswith('application/javascript')
        assert worker.headers['service-worker-allowed'] == '/'
        assert worker.headers['cache-control'] == 'no-store'
        config = json.loads(re.search(r'const CONFIG = (.+);',worker.text)[1])
        assert len(config['assets']) == 3
        assert {asset['url'].split('?')[0] for asset in config['assets']} == {
            '/offline','/static/pwa/offline.css','/static/pwa/icon-192.png'}
        for asset in config['assets']:
            assert asset['url'] in config['offline'] or asset['url'].startswith('/static/pwa/')
            response = client.get(asset['url'])
            integrity = 'sha256-' + base64.b64encode(hashlib.sha256(response.content).digest()).decode()
            assert integrity == asset['integrity']
            assert 'set-cookie' not in response.headers
        offline = client.get(config['offline']).text
        assert 'You’re offline' in offline and 'cannot be saved' in offline
        assert '/api/' not in offline and '<script' not in offline
        assert '<form action="/" method="get">' in offline
        assert '<input' not in offline and 'type="submit">Try again' in offline
        assert client.get('/',follow_redirects=False).status_code == 303
        for path in ['/api/health','/api/learners/example/profile','/static/app.js',
                     '/static/flashcard-catalog.json','/static/pwa/private.json','/reference/book.pdf']:
            result = client.get(path)
            assert result.status_code == 401, path
            assert result.headers['cache-control'] == 'no-store'
        assert client.post('/offline').status_code == 401
        assert not provider.calls
