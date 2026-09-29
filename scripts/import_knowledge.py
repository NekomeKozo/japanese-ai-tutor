"""Explicit private derived-index import to the existing server database.

Dry run by default. Reads DATABASE_URL privately from the existing environment/.env.
Never copies reference PDFs, filenames, inventory metadata, or learner records.
"""
import argparse
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.config import Settings
from app.knowledge.repository import KnowledgeRepository
from app.knowledge.schemas import KnowledgeChunk, KnowledgeSource


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database',type=Path,default=Path('knowledge_base/index.sqlite3'))
    parser.add_argument('--apply',action='store_true',help='Import derived chunks to the configured PostgreSQL database')
    args=parser.parse_args()
    path=args.database.resolve(strict=True)
    with sqlite3.connect(path.as_uri()+'?mode=ro',uri=True) as local:
        sources=local.execute('SELECT source_id,version,title,category,format FROM knowledge_sources').fetchall()
        print(json.dumps({'sources':len(sources),'mode':'apply' if args.apply else 'dry_run'}))
        if not args.apply: return
        settings=Settings()
        url=settings.database_url.get_secret_value()
        if not url.startswith(('postgres://','postgresql://')):
            raise ValueError('PostgreSQL DATABASE_URL must be configured privately')
        remote=KnowledgeRepository(database_url=url)
        remote.initialize()
        updated=0
        for sid,version,title,category,fmt in sources:
            if remote.source_version(sid)==version: continue
            source=KnowledgeSource(source_id=sid,relative_path='',title=title,category=category,format=fmt,size_bytes=0)
            chunks=[KnowledgeChunk.model_validate_json(row[0]) for row in local.execute(
                'SELECT payload FROM knowledge_chunks WHERE source_id=?',(sid,)).fetchall()]
            remote.replace_source(source,chunks,version)
            updated+=1
        print(json.dumps({'updated_sources':updated,**remote.counts()}))


if __name__=='__main__':
    try: main()
    except Exception as exc:
        print('Import stopped safely:',type(exc).__name__)
        raise SystemExit(1)
