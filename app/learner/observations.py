import json
import logging

from pydantic import ValidationError

from app.learner.catalog import normalize_topic
from app.learner.schemas import LearningObservation

logger = logging.getLogger(__name__)


def extract_observations(raw: str):
    """Bad evidence never discards an otherwise valid teaching response."""
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        return raw, []
    candidates = payload.pop('learning_observations', [])
    observations, seen = [], set()
    if not isinstance(candidates, list):
        logger.warning('Malformed learning observations ignored')
        candidates = []
    for candidate in candidates[:8]:
        try:
            observation = LearningObservation.model_validate(candidate)
            key, _ = normalize_topic(observation.topic_key, observation.skill)
            if key not in seen:
                observations.append(observation)
                seen.add(key)
        except (ValidationError, ValueError):
            logger.warning('Malformed learning observation ignored')
    return json.dumps(payload, ensure_ascii=False), observations
