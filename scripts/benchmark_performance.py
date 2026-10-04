"""Reproducible local-only Phase 11F measurements; never uses live learner/provider data.

Run: python scripts/benchmark_performance.py --output /path/to/results.json
Uses a disposable SQLite database, mocked providers and sequential warm requests.
The concurrency check simulates one 150ms DB read; it is not a Render load test.
"""
import argparse
import asyncio
import json
from pathlib import Path
import re
import sqlite3
import statistics
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import httpx
from fastapi.testclient import TestClient
from app.config import Settings
from app.main import create_app


class OfflineProvider:
    async def generate(self, **kwargs):
        raise AssertionError('This benchmark must never call an AI provider')


def benchmark(output):
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = tempfile.TemporaryDirectory(prefix='goigrow-perf-', dir=output.parent)
    folder = Path(temporary.name).resolve()
    assert folder.is_relative_to(output.parent.resolve())
    try:
        statements = []
        original_connect = sqlite3.connect
        def traced(*args, **kwargs):
            db = original_connect(*args, **kwargs)
            db.set_trace_callback(statements.append)
            return db
        settings = Settings(_env_file=None, environment='development', database_url='',
            staging_access_enabled=False, knowledge_enabled=False, stt_enabled=False,
            openai_api_key='', gemini_api_key='', groq_api_key='', llm_failover_enabled=False,
            assessment_db_path=str(folder / 'learner.sqlite3'))
        app = create_app(settings, OfflineProvider())
        sqlite3.connect = traced
        started = time.perf_counter()
        with TestClient(app) as client:
            startup_ms = (time.perf_counter()-started)*1000
            startup_bank_writes = sum(s.startswith('INSERT') and 'INTO assessment_questions' in s for s in statements)
            html = client.get('/').text
            assets = re.findall(r'(?:src|href)="(/static/[^" ]+\.(?:js|css)(?:\?[^" ]*)?)"', html)
            transferred = raw = repeat = 0
            for path in assets:
                response = client.get(path, headers={'Accept-Encoding':'gzip'})
                raw += len(response.content)
                transferred += int(response.headers['content-length'])
                repeat_headers={'Accept-Encoding':'gzip'}
                if 'no-store' not in response.headers['cache-control']: repeat_headers['If-None-Match']=response.headers['etag']
                reloaded = client.get(path, headers=repeat_headers)
                # A browser uses a fresh immutable private entry without this request.
                repeat += 0 if 'immutable' in response.headers['cache-control'] else int(reloaded.headers.get('content-length',0))
            learner = client.post('/api/learners').json()['learner_id']
            latencies=[]
            for _ in range(10):
                started=time.perf_counter(); result=client.get(f'/api/learners/{learner}/profile')
                assert result.status_code==200
                latencies.append((time.perf_counter()-started)*1000)
            original_profile=app.state.learners.profile
            def delayed(*args):
                time.sleep(.150)
                return original_profile(*args)
            app.state.learners.profile=delayed
            async def contention():
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://local.test') as requests:
                    started=time.perf_counter()
                    async def health():
                        result=await requests.get('/health')
                        assert result.status_code==200
                        return (time.perf_counter()-started)*1000
                    _, completed=await asyncio.gather(requests.get(f'/api/learners/{learner}/profile'),health())
                    return completed
            health_ms=asyncio.run(contention())
        sqlite3.connect=original_connect
        data=dict(environment='local TestClient/ASGI, disposable SQLite, no providers',
            initial_js_css_resources=len(assets),initial_js_css_raw_bytes=raw,
            initial_js_css_gzip_transfer_bytes=transferred,
            repeat_static_body_bytes=repeat, startup_question_bank_write_statements=startup_bank_writes,
            local_startup_ms=round(startup_ms,2),warm_profile_median_ms=round(statistics.median(latencies),2),
            health_completion_with_150ms_profile_ms=round(health_ms,2),
            lcp=None,cls=None,inp=None)
        output.write_text(json.dumps(data,indent=2)+'\n',encoding='utf-8')
        print(json.dumps(data))
    finally:
        sqlite3.connect=original_connect
        assert folder.is_relative_to(output.parent.resolve())
        temporary.cleanup()


if __name__ == '__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--output',type=Path,required=True)
    benchmark(parser.parse_args().output.resolve())
