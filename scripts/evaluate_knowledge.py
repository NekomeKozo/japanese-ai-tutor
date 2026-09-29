"""Relevance checks separate from answer quality; no private previews printed."""
import argparse
import json
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.knowledge.repository import KnowledgeRepository


def evaluate(repo, cases):
    timings, rows = [], []
    for case in cases:
        for query in case['queries']:
            started = time.perf_counter()
            results = repo.retrieve(query)
            timings.append((time.perf_counter()-started)*1000)
            hit = any(r.chunk.category == case['topic'] for r in results)
            rows.append({'topic':case['topic'], 'query':query, 'results':len(results),
                'expected_category_hit': hit if case['text'] else None,
                'no_match_correct': not results if case['text'] is None else None,
                'duplicate_count':len(results)-len({r.chunk.content_hash for r in results})})
    return {'queries':len(rows), 'category_hits':sum(r['expected_category_hit'] is True for r in rows),
        'category_cases':sum(r['expected_category_hit'] is not None for r in rows),
        'no_match_correct':sum(r['no_match_correct'] is True for r in rows),
        'no_match_cases':sum(r['no_match_correct'] is not None for r in rows),
        'duplicate_results':sum(r['duplicate_count'] for r in rows),
        'median_ms':round(statistics.median(timings),2), 'max_ms':round(max(timings),2), 'cases':rows}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database',default='knowledge_base/index.sqlite3')
    parser.add_argument('--cases',type=Path,default=Path('tests/fixtures/knowledge/cases.json'))
    args=parser.parse_args()
    results=evaluate(KnowledgeRepository(args.database),json.loads(args.cases.read_text(encoding='utf8')))
    # On owner material, categories are usually unknown: do not report synthetic
    # category hits as a corpus relevance score. Inspect actual result provenance.
    print(json.dumps(results,ensure_ascii=True))


if __name__=='__main__': main()
