import hashlib
import re

from app.knowledge.schemas import ExtractedDocument, KnowledgeChunk

BUILD_VERSION = 'lexical-v2'


def bounded_parts(text, limit):
    """Prefer paragraph then sentence boundaries; hard splitting is a last resort."""
    if len(text) <= limit:
        yield text
        return
    parts = re.split(r'(?<=[。！？.!?])\s*|\n', text)
    current = ''
    for part in filter(None, parts):
        if current and len(current) + len(part) + 1 > limit:
            yield current
            current = ''
        while len(part) > limit:
            split = part.rfind(' ', 0, limit + 1)
            split = split if split >= limit // 2 else limit
            yield part[:split].strip()
            part = part[split:].lstrip()
        current = (current + '\n' + part).strip()
    if current:
        yield current


def chunk_document(document: ExtractedDocument, max_chars=1000) -> list[KnowledgeChunk]:
    if not 200 <= max_chars <= 2400:
        raise ValueError('Chunk size must be between 200 and 2400 characters')
    source = document.source
    output, seen = [], set()
    for page in document.pages:
        section, group = None, ''
        def emit(text, heading):
            digest = hashlib.sha256(text.encode()).hexdigest()
            if digest in seen:
                return
            seen.add(digest)
            identity = f'{BUILD_VERSION}:{source.source_id}:{page.page}:{heading}:{digest}'
            output.append(KnowledgeChunk(chunk_id='chk_' + hashlib.sha256(identity.encode()).hexdigest()[:32],
                source_id=source.source_id, title=source.title, page=page.page, section=heading,
                category=source.category, inferred_category=source.inferred_category, text=text, content_hash=digest))
        for block in re.split(r'\n\s*\n', page.text):
            # Markdown headings are explicit, not inferred bibliographic metadata.
            lines = block.splitlines()
            if lines and re.match(r'^#{1,6}\s+\S', lines[0]):
                if group:
                    emit(group, section)
                    group = ''
                section = re.sub(r'^#{1,6}\s+', '', lines[0])[:160]
            for part in bounded_parts(block.strip(), max_chars):
                if group and len(group) + len(part) + 2 > max_chars:
                    emit(group, section)
                    group = ''
                group = (group + '\n\n' + part).strip()
        if group:
            emit(group, section)
    return output
