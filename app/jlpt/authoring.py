"""Developer-only RAG candidates. No endpoint or automatic publication path."""
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from app.jlpt.bank import Bank
from app.jlpt.schemas import Question
from app.knowledge.service import GROUNDING_INSTRUCTIONS, KnowledgeService
from app.learner.catalog import TOPICS
from app.llm.base import Message


async def candidate(settings, provider, knowledge, bank, *, level, section, topic_id, root):
    if settings.environment != 'development':
        raise ValueError('Candidate authoring is development-only')
    if level not in ('N5','N4') or section not in ('vocabulary','kanji','grammar','reading'):
        raise ValueError('Unsupported candidate scope')
    if topic_id not in TOPICS or TOPICS[topic_id].skill != section:
        raise ValueError('Choose an existing topic in the selected section')
    context = await knowledge.context_for(f'{TOPICS[topic_id].label} Japanese {section}', task='quiz')
    if context.status != 'available' or not context.results:
        raise ValueError('Relevant reference context is required for RAG authoring')
    instructions = ('Create one ORIGINAL Japanese learning question as a candidate for editorial review. '
        'Never reproduce reference exercises or sentences. Give one unambiguous answer, plausible distinct '
        'distractors and a short original explanation. Reading questions need an original passage. '
        'Do not put source text, paths or provenance IDs in question fields. Never publish or approve. '
        'Use candidate status, rag_candidate source_type, version 1. Return JSON matching the schema.\n'
        + GROUNDING_INSTRUCTIONS)
    query = json.dumps(dict(level=level,section=section,topic_id=topic_id,
        id='jlpt_candidate_'+uuid4().hex), ensure_ascii=False)
    async with asyncio.timeout(settings.llm_timeout_seconds):
        raw = await provider.generate(instructions=instructions,
            messages=KnowledgeService.messages([Message('user', query)], context), schema=Question.model_json_schema())
    if not isinstance(raw, str) or len(raw.encode()) > 18000:
        raise ValueError('Invalid candidate size')
    question = Question.model_validate_json(raw)
    if (question.level, question.section, question.topic_id) != (level, section, topic_id):
        raise ValueError('Candidate changed the requested scope')
    question = question.model_copy(update={'status':'candidate', 'source_type':'rag_candidate'})
    KnowledgeService.check_response(question, context)
    # Both stable IDs and content are checked against the approved bank and prior candidates.
    folder = Path(root).resolve() / 'knowledge_base' / 'jlpt_candidates'
    if folder.is_symlink() or folder.resolve() != folder:
        raise ValueError('Candidate directory must not redirect outside the private output directory')
    folder.mkdir(parents=True, exist_ok=True)
    existing = []
    for path in folder.glob('*.json'):
        if path.is_symlink(): raise ValueError('Invalid candidate file')
        existing.append(Question.model_validate(json.loads(path.read_text(encoding='utf-8'))['question']))
    Bank([*bank.items, *existing, question])
    record = dict(question=question.model_dump(), generated_at=datetime.now(timezone.utc).isoformat(),
        provider=settings.llm_provider, model=settings.llm_model,
        references=[dict(source_id=r.chunk.source_id,chunk_id=r.chunk.chunk_id,page=r.chunk.page) for r in context.results],
        review_checklist=['Japanese accuracy','single valid answer','level and distractors','originality and privacy','topic and dimension'],
        review_status='pending_manual_review')
    path = folder / (uuid4().hex+'.json')
    with path.open('x', encoding='utf-8') as out:
        json.dump(record,out,ensure_ascii=False,indent=2)
    return path
