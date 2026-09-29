"""Local developer search with bounded previews; never an HTTP route."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.knowledge.repository import KnowledgeRepository


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('query')
    parser.add_argument('--database', default='knowledge_base/index.sqlite3')
    parser.add_argument('--limit', type=int, default=3)
    parser.add_argument('--preview', action='store_true', help='Show at most 100 source characters per result locally')
    args = parser.parse_args()
    for rank, result in enumerate(KnowledgeRepository(args.database).retrieve(args.query, args.limit), 1):
        row = {'rank': rank, 'source': result.chunk.source_id, 'page': result.chunk.page, 'score': result.score}
        if args.preview:
            row['preview'] = result.chunk.text[:100]
        print(json.dumps(row, ensure_ascii=True))


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print('Search unavailable:', type(exc).__name__)
        raise SystemExit(1)
