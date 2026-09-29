"""Explicit local build. No network, provider calls, or learner DB access."""
import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.knowledge.chunker import BUILD_VERSION, chunk_document
from app.knowledge.extractors import SUPPORTED, MAX_FILE_BYTES, extract, inventory
from app.knowledge.repository import KnowledgeRepository
from scripts.inventory_references import private_output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference', type=Path, default=Path('reference'))
    parser.add_argument('--database', type=Path, default=Path('knowledge_base/index.sqlite3'))
    parser.add_argument('--chunk-chars', type=int, default=1000)
    args = parser.parse_args()
    sources = inventory(args.reference)
    repo = KnowledgeRepository(str(private_output(args.database)))
    repo.initialize()
    statuses, manifest = Counter(), []
    for number, source in enumerate(sources, 1):
        path = args.reference / source.relative_path
        try:
            if source.format not in SUPPORTED:
                source.status = 'unsupported'
            elif source.size_bytes > MAX_FILE_BYTES:
                source.status = 'size_limit'
            else:
                with path.open('rb') as stream:
                    digest = hashlib.file_digest(stream, 'sha256').hexdigest()
                version = f'{BUILD_VERSION}:{args.chunk_chars}:{digest}'
                if repo.source_version(source.source_id) == version:
                    source.status = 'unchanged'
                else:
                    document = extract(source, args.reference)
                    source = document.source
                    chunks = chunk_document(document, args.chunk_chars)
                    if chunks:
                        repo.replace_source(source, chunks, version)
        except Exception:
            source.status = 'build_failed_previous_preserved'
        manifest.append(source.model_dump())
        statuses[source.status] += 1
        print(f'Source {number}/{len(sources)}: {source.status}', flush=True)
    private_output(Path('knowledge_base/build_manifest.json')).write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'status_counts': dict(statuses), **repo.counts()}))


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print('Build stopped safely:', type(exc).__name__)
        raise SystemExit(1)
