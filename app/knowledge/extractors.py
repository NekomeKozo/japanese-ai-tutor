"""Local ingestion only. Never imported by the web startup path."""
import hashlib
import logging
import re
from pathlib import Path

from app.knowledge.normalize import normalize
from app.knowledge.schemas import ExtractedDocument, ExtractedPage, KnowledgeSource

SUPPORTED = {'.pdf', '.txt', '.md'}
MAX_FILE_BYTES = 150 * 1024 * 1024
MAX_PAGES = 3000
MAX_PAGE_CHARS = 100000


def inventory(root: Path) -> list[KnowledgeSource]:
    root = root.resolve(strict=True)
    items = []
    for path in sorted(root.rglob('*')):
        if not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(root):
            continue
        relative = path.relative_to(root).as_posix()
        # Stable under content edits, independent of the absolute machine path.
        sid = 'src_' + hashlib.sha256(relative.encode()).hexdigest()[:24]
        suffix = path.suffix.lower()
        inferred = next((name for name, pattern in (
            ('vocabulary', r'vocab|word|単語'), ('kanji', r'kanji|漢字'),
            ('grammar', r'grammar|文法')) if re.search(pattern, relative.casefold())), None)
        items.append(KnowledgeSource(source_id=sid, relative_path=relative, format=suffix,
            inferred_category=inferred,
            size_bytes=path.stat().st_size,
            status='pending' if suffix in SUPPORTED else 'unsupported'))
    if not items:
        raise ValueError('Reference folder is empty')
    return items


def extract(source: KnowledgeSource, root: Path) -> ExtractedDocument:
    source = source.model_copy(deep=True)
    result = ExtractedDocument(source=source)
    if source.format not in SUPPORTED:
        source.status = 'unsupported'
        return result
    root = root.resolve(strict=True)
    path = root / source.relative_path
    if path.is_symlink() or not path.resolve().is_relative_to(root):
        source.status = 'unsafe_path'
        return result
    if path.stat().st_size > MAX_FILE_BYTES:
        source.status = 'size_limit'
        return result
    try:
        with path.open('rb') as stream:
            source.version = hashlib.file_digest(stream, 'sha256').hexdigest()
        if source.format == '.pdf':
            from pypdf import PdfReader
            # Third-party diagnostics can contain document strings; retain only our statuses.
            previous = logging.root.manager.disable
            logging.disable(logging.CRITICAL)
            try:
                reader = PdfReader(path)
                if reader.is_encrypted:
                    source.status = 'encrypted'
                    return result
                source.page_count = len(reader.pages)
                if source.page_count > MAX_PAGES:
                    source.status = 'page_limit'
                    return result
                for number, page in enumerate(reader.pages, 1):
                    try:
                        text = normalize(page.extract_text() or '')
                        if len(text) > MAX_PAGE_CHARS:
                            source.skipped_pages += 1
                            continue
                        if sum(c.isalnum() for c in text) < 30:
                            source.skipped_pages += 1
                            continue
                        result.pages.append(ExtractedPage(page=number, text=text))
                    except Exception:
                        source.skipped_pages += 1
            finally:
                logging.disable(previous)
        else:
            text = normalize(path.read_text(encoding='utf-8-sig'))
            if len(text) > 2_000_000:
                source.status = 'text_limit'
                return result
            source.page_count = 1
            if text:
                result.pages.append(ExtractedPage(page=1, text=text))
        source.text_pages = len(result.pages)
        source.status = ('partial' if source.skipped_pages else 'extracted') if result.pages else 'ocr_needed_or_empty'
    except Exception:
        source.status = 'extraction_failed'
        result.pages = []
    return result
