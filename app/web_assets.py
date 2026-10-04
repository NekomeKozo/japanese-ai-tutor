"""Deployment-versioned public UI assets, never learner/API response caching."""
import hashlib
import base64
import json
from pathlib import Path
import re

PWA_PUBLIC_PATHS = frozenset(('/manifest.webmanifest', '/service-worker.js', '/offline', '/favicon.ico',
    '/static/pwa/offline.css', '/static/pwa/icon-192.png', '/static/pwa/icon-512.png',
    '/static/pwa/icon-maskable-512.png', '/static/pwa/apple-touch-icon.png', '/static/pwa/favicon-32.png'))


class WebAssets:
    def __init__(self, directory: Path):
        digest = hashlib.sha256()
        for path in sorted(directory.rglob('*')):
            if path.is_file() and path.suffix in ('.html', '.js', '.css', '.json', '.png', '.ico'):
                digest.update(path.relative_to(directory).as_posix().encode())
                digest.update(path.read_bytes())
        self.version = digest.hexdigest()[:20]
        self.index = self.version_html((directory / 'index.html').read_text(encoding='utf-8'))
        if (directory / 'service-worker.js').exists():
            self.access = self.version_html((directory / 'access.html').read_text(encoding='utf-8'))
            self.offline = self.version_html((directory / 'pwa/offline.html').read_text(encoding='utf-8'))
            offline_url = '/offline?v=' + self.version
            sources = [(offline_url, self.offline.encode()),
                ('/static/pwa/offline.css?v=' + self.version, (directory / 'pwa/offline.css').read_bytes()),
                ('/static/pwa/icon-192.png?v=' + self.version, (directory / 'pwa/icon-192.png').read_bytes())]
            config = dict(version=self.version, offline=offline_url, assets=[dict(url=url,
                integrity='sha256-' + base64.b64encode(hashlib.sha256(body).digest()).decode()) for url, body in sources])
            self.worker = (directory / 'service-worker.js').read_text(encoding='utf-8').replace('__PWA_CONFIG__', json.dumps(config))

    def version_html(self, html):
        html = html.replace('<html lang="en">', f'<html lang="en" data-asset-version="{self.version}">')
        return re.sub(r'(/static/(?:[\w.-]+/)*[\w.-]+\.(?:js|css|png|ico))(?=["\'])',
                      lambda match: match[0] + '?v=' + self.version, html)

    def manifest(self):
        def icon(name, size, purpose='any'):
            return dict(src='/static/pwa/' + name + '?v=' + self.version, sizes=size, type='image/png', purpose=purpose)
        return dict(id='/', name='GoiGrow — Japanese Tutor', short_name='GoiGrow',
            description='A little, every day. Your Japanese learning companion.', start_url='/#home',
            scope='/', display='standalone', orientation='any', lang='en', theme_color='#285d4e',
            background_color='#f5f6f1', icons=[icon('icon-192.png','192x192'),icon('icon-512.png','512x512'),
                icon('icon-maskable-512.png','512x512','maskable')])

    def cache_control(self, request, status):
        public_pwa = request.url.path in PWA_PUBLIC_PATHS and request.url.path not in ('/manifest.webmanifest', '/service-worker.js')
        if status in (200, 304) and (public_pwa or (request.url.path.startswith('/static/') and Path(request.url.path).suffix in ('.js', '.css', '.json'))):
            if request.query_params.get('v') == self.version:
                return 'private, max-age=31536000, immutable'
            return 'private, max-age=0, must-revalidate'
        return 'no-store'
