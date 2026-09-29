"""An inverted index, separate from learner schema versions and learner writes."""
import json
import math
import re
from pathlib import Path

from app.assessment.repository import AssessmentRepository
from app.knowledge.schemas import KnowledgeChunk, SearchResult
from app.knowledge.terms import terms

DDL = [
    'CREATE TABLE IF NOT EXISTS knowledge_meta (id INTEGER PRIMARY KEY, version INTEGER NOT NULL)',
    '''CREATE TABLE IF NOT EXISTS knowledge_sources (source_id TEXT PRIMARY KEY,
       version TEXT NOT NULL, title TEXT, category TEXT, format TEXT NOT NULL)''',
    '''CREATE TABLE IF NOT EXISTS knowledge_chunks (chunk_id TEXT PRIMARY KEY,
       source_id TEXT NOT NULL REFERENCES knowledge_sources(source_id), content_hash TEXT NOT NULL,
       payload TEXT NOT NULL)''',
    'CREATE INDEX IF NOT EXISTS ix_knowledge_source ON knowledge_chunks(source_id)',
    '''CREATE TABLE IF NOT EXISTS knowledge_postings (term TEXT NOT NULL,
       chunk_id TEXT NOT NULL REFERENCES knowledge_chunks(chunk_id), weight REAL NOT NULL,
       PRIMARY KEY(term,chunk_id))''',
    'CREATE INDEX IF NOT EXISTS ix_knowledge_posting_chunk ON knowledge_postings(chunk_id)',
]


class KnowledgeRepository:
    def __init__(self, path='knowledge_base/index.sqlite3', database_url=''):
        self.storage = AssessmentRepository(path, database_url)

    def initialize(self):
        # Explicit administrative operation; never called by the web process.
        if not self.storage.database_url:
            self.storage.path.parent.mkdir(parents=True, exist_ok=True)
        with self.storage.connection(initialize=True) as db:
            db.execute('BEGIN IMMEDIATE')
            for statement in DDL:
                db.execute(statement)
            row = db.execute('SELECT version FROM knowledge_meta WHERE id=1').fetchone()
            if row and row[0] != 1:
                raise ValueError('Unsupported knowledge schema')
            db.execute('INSERT OR IGNORE INTO knowledge_meta VALUES (1,1)')
            if self.storage.database_url:
                db.execute('REVOKE ALL ON knowledge_meta, knowledge_sources, knowledge_chunks, knowledge_postings FROM PUBLIC')

    def source_version(self, source_id):
        with self.storage.connection() as db:
            row = db.execute('SELECT version FROM knowledge_sources WHERE source_id=?', (source_id,)).fetchone()
            return row[0] if row else None

    def replace_source(self, source, chunks, version):
        if not chunks or any(c.source_id != source.source_id for c in chunks):
            raise ValueError('A successful nonempty source build is required')
        with self.storage.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            # Atomic per-source replacement; no learner tables or unrelated sources touched.
            db.execute('DELETE FROM knowledge_postings WHERE chunk_id IN (SELECT chunk_id FROM knowledge_chunks WHERE source_id=?)', (source.source_id,))
            db.execute('DELETE FROM knowledge_chunks WHERE source_id=?', (source.source_id,))
            db.execute('INSERT OR IGNORE INTO knowledge_sources VALUES (?,?,?,?,?)',
                (source.source_id, version, source.title, source.category, source.format))
            db.execute('UPDATE knowledge_sources SET version=?,title=?,category=?,format=? WHERE source_id=?',
                (version, source.title, source.category, source.format, source.source_id))
            def bulk(statement, rows):
                if self.storage.database_url:
                    with db.raw.cursor() as cursor:
                        cursor.executemany(statement.replace('?', '%s'), rows)
                else:
                    db.executemany(statement, rows)
            bulk('INSERT INTO knowledge_chunks VALUES (?,?,?,?)',
                [(c.chunk_id,c.source_id,c.content_hash,c.model_dump_json()) for c in chunks])
            bulk('INSERT INTO knowledge_postings VALUES (?,?,?)',
                [(term,c.chunk_id,1+math.log(frequency)) for c in chunks
                 for term,frequency in terms(c.text+' '+(c.section or '')).items()])

    def counts(self):
        with self.storage.connection() as db:
            return {name: db.execute(f'SELECT COUNT(*) FROM knowledge_{name}').fetchone()[0]
                for name in ('sources', 'chunks', 'postings')}

    def retrieve(self, query, limit=3, filters=None, min_score=.35):
        query_terms = list(terms(query[:4000], expand=True))[:48]
        if not query_terms:
            return []
        limit = max(1, min(int(limit), 8))
        filters = filters or {}
        if set(filters) - {'source_id', 'category'}:
            raise ValueError('Unsupported knowledge filter')
        placeholders = ','.join('?' for _ in query_terms)
        with self.storage.connection() as db:
            # Bound candidates before loading bodies. The posting primary key indexes term.
            where, params = '', list(query_terms)
            for key, value in filters.items():
                where += f' AND s.{key}=?'
                params.append(value)
            candidates = db.execute(f'''SELECT p.chunk_id, COUNT(*), SUM(p.weight)
                FROM knowledge_postings p JOIN knowledge_chunks c ON c.chunk_id=p.chunk_id
                JOIN knowledge_sources s ON s.source_id=c.source_id
                WHERE p.term IN ({placeholders}){where}
                GROUP BY p.chunk_id ORDER BY COUNT(*) DESC, SUM(p.weight) DESC, p.chunk_id LIMIT 120''', params).fetchall()
            if not candidates:
                return []
            ids = [c[0] for c in candidates]
            rows = db.execute('SELECT chunk_id,payload FROM knowledge_chunks WHERE chunk_id IN (' + ','.join('?' for _ in ids) + ')', ids).fetchall()
        from app.knowledge.normalize import match_text
        payloads = dict(rows)
        results, seen = [], set()
        needles = re.findall(r'[\u3040-\u30ff\u3400-\u9fff]+', match_text(query))
        grammar_forms = {'たい', 'ながら', 'たり', 'ので', 'のに', 'は', 'が', 'に', 'で'}
        grammar_query = bool(grammar_forms.intersection(needles)) or bool(re.search(r'grammar|particle|form|conjugat',query,re.I))
        for cid, count, weight in candidates:
            chunk = KnowledgeChunk.model_validate_json(payloads[cid])
            coverage = count / len(query_terms)
            # Phrase match supports short grammar forms; broad single English words
            # still require a full term match. Scores describe relevance, not confidence.
            phrase = match_text(query.strip())
            phrase_bonus = .15 if 2 <= len(phrase) <= 80 and phrase in match_text(chunk.text) else 0
            body=match_text(chunk.text)
            exact = sum(bool(re.search(r'(?<![\u3040-\u30ff\u3400-\u9fff])'+re.escape(n)+r'(?![\u3040-\u30ff\u3400-\u9fff])',body)) for n in needles)
            category=chunk.category or chunk.inferred_category
            # A grammar suffix buried inside an unrelated vocabulary word is not evidence.
            if grammar_query and category=='vocabulary':
                continue
            if grammar_forms.intersection(needles) and not exact:
                continue
            if set(needles).intersection({'は','が','に','で'}) and len(needles)>1:
                if exact < len(needles) or not re.search(r'particle|subject|topic|contrast|destination|location|助詞|主語|主題|場所',body):
                    continue
            boundary_bonus=.12*exact/max(1,len(needles))
            density_bonus=min(.08,float(weight)/max(1,len(query_terms))*.02*min(1,400/max(1,len(chunk.text))))
            reading_bonus=.1 if re.search(r'reading|kanji|読み',query,re.I) and category in {'kanji','vocabulary'} else 0
            comparison_bonus=.12 if re.search(r'difference|instead|versus|違い|使い分け',query,re.I) and re.search(
                r'contrast|whereas|while|however|identical|difference|違い|使い分け',body) else 0
            score = min(1., coverage * .75 + phrase_bonus + boundary_bonus + density_bonus + reading_bonus + comparison_bonus)
            if score < min_score or chunk.content_hash in seen:
                continue
            seen.add(chunk.content_hash)
            results.append(SearchResult(chunk=chunk, score=round(score, 4)))
        return sorted(results, key=lambda r: (-r.score, r.chunk.chunk_id))[:limit]
