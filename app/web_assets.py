"""Deployment-versioned public UI assets, never learner/API response caching."""
import hashlib
from pathlib import Path
import re


class WebAssets:
    def __init__(self, directory: Path):
        digest = hashlib.sha256()
        for path in sorted(directory.iterdir()):
            if path.is_file() and path.suffix in ('.html', '.js', '.css', '.json'):
                digest.update(path.name.encode())
                digest.update(path.read_bytes())
        self.version = digest.hexdigest()[:20]
        html = (directory / 'index.html').read_text(encoding='utf-8')
        html = html.replace('<html lang="en">', f'<html lang="en" data-asset-version="{self.version}">')
        self.index = re.sub(r'(/static/[\w.-]+\.(?:js|css))(?=["\'])',
                            lambda match: match[0] + '?v=' + self.version, html)

    def cache_control(self, request, status):
        if status in (200, 304) and request.url.path.startswith('/static/') and Path(request.url.path).suffix in ('.js', '.css', '.json'):
            if request.query_params.get('v') == self.version:
                return 'private, max-age=31536000, immutable'
            return 'private, max-age=0, must-revalidate'
        return 'no-store'
