"""Explicit development-only candidate generation; never edits the served bank."""
import argparse
import asyncio
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.config import Settings
from app.jlpt.authoring import candidate
from app.jlpt.bank import Bank
from app.knowledge.repository import KnowledgeRepository
from app.knowledge.service import KnowledgeService
from app.llm.factory import create_provider


async def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--level', required=True, choices=['N5','N4'])
    parser.add_argument('--section', required=True, choices=['vocabulary','kanji','grammar','reading'])
    parser.add_argument('--topic', required=True)
    args=parser.parse_args()
    settings=Settings()
    if settings.environment != 'development': raise ValueError('Development only')
    repository=KnowledgeRepository(settings.knowledge_db_path, settings.database_url.get_secret_value())
    async with httpx.AsyncClient() as client:
        path=await candidate(settings,create_provider(settings,client),KnowledgeService(repository,settings),Bank.load(),
            level=args.level,section=args.section,topic_id=args.topic,root=ROOT)
    print('Candidate saved privately:', path.name, 'Manual editorial review is required; nothing was published.')


if __name__ == '__main__':
    try: asyncio.run(main())
    except Exception as exc:
        print('Candidate authoring failed:', type(exc).__name__)
        raise SystemExit(1)
