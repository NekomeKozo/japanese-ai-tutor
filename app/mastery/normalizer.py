import logging
from app.mastery.catalog import canonical, topic_type
from app.mastery.policy import POLICY
from app.mastery.schemas import Evidence, EvidenceContext

logger = logging.getLogger(__name__)


def normalize(row, metadata):
    """Normalize one persisted Phase 3 row, never arbitrary model output."""
    if row['event_type'] != 'performance' or row['score'] is None or metadata.get('unknown_topic'):
        return []
    try:
        context = EvidenceContext.model_validate(metadata.get('mastery', {}))
        fixed = row['source'] == 'curriculum' and metadata.get('fixed_template', False)
        key = canonical(row['topic_key'], fixed=fixed)
        kind = topic_type(key)
        if not kind:
            return []
        dimension = context.dimension
        evidence_type = context.evidence_type
        quality = context.quality
        if not dimension:
            # Historical chat claims cannot establish independent production or readings.
            dimension, evidence_type = 'recognition', 'recognition'
            quality *= POLICY.legacy_quality
        evidence_type = evidence_type or ('production' if dimension == 'production' else 'recall')
        if context.answer_revealed and row['score'] > 0:
            return []
        evidence = Evidence(event_id=row['event_id'], learner_id=row['learner_id'], topic_id=key,
            topic_type=kind, dimension=dimension, score=row['score'], difficulty=row['difficulty'] or 0,
            learner_level=context.learner_level, evidence_type=evidence_type, activity_type=context.activity_type,
            source=row['source'], context_id=context.context_id or f'unknown:{row["source"]}',
            hint_used=context.hint_used, answer_revealed=context.answer_revealed, quality=quality,
            reading_context=context.reading_context, timestamp=row['created_at'])
        if kind == 'kanji' and dimension in ('on_reading', 'kun_reading') and not context.reading_context:
            logger.warning('Mastery evidence skipped: missing reading context')
            return []
        if evidence_type == 'recognition' and dimension != 'recognition':
            # Choosing a meaning/reading tests recognition as well, not independent recall.
            # Overall counts deduplicate the originating event.
            return [evidence, evidence.model_copy(update={'dimension': 'recognition'})]
        return [evidence]
    except (ValueError, TypeError, KeyError):
        logger.warning('Mastery evidence skipped: invalid metadata or score')
        return []
