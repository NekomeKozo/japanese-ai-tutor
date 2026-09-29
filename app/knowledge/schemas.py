from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class KnowledgeModel(BaseModel):
    model_config = ConfigDict(extra='forbid', hide_input_in_errors=True)


class KnowledgeSource(KnowledgeModel):
    source_id: str = Field(pattern=r'^src_[a-f0-9]{24}$')
    relative_path: str  # Private inventory only; never sent to providers or clients.
    title: str | None = None  # Only explicitly supplied titles are used.
    format: str
    category: str | None = None
    inferred_category: str | None = None
    size_bytes: int = Field(ge=0)
    version: str = ''
    status: str = 'pending'
    page_count: int = 0
    text_pages: int = 0
    skipped_pages: int = 0


class ExtractedPage(KnowledgeModel):
    page: int = Field(ge=1)
    text: str


class ExtractedDocument(KnowledgeModel):
    source: KnowledgeSource
    pages: list[ExtractedPage] = Field(default_factory=list)


class KnowledgeChunk(KnowledgeModel):
    chunk_id: str = Field(pattern=r'^chk_[a-f0-9]{32}$')
    source_id: str
    title: str | None = None
    page: int = Field(ge=1)
    section: str | None = None
    category: str | None = None
    inferred_category: str | None = None
    text: str = Field(min_length=1, max_length=2400)
    content_hash: str


class SearchResult(KnowledgeModel):
    chunk: KnowledgeChunk
    score: float


class KnowledgeContext(KnowledgeModel):
    status: Literal['disabled', 'not_needed', 'no_match', 'available', 'unavailable']
    results: list[SearchResult] = Field(default_factory=list)
    payload: str = ''
