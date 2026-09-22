from dataclasses import dataclass, field

VERSION = 1
DIMENSIONS = {
    'vocabulary': {'recognition': .15, 'meaning': .25, 'reading': .2, 'production': .4},
    'grammar': {'recognition': .15, 'understanding': .2, 'application': .25, 'production': .4},
    'kanji': {'recognition': .15, 'meaning': .25, 'on_reading': .25, 'kun_reading': .25, 'production': .1},
}


@dataclass(frozen=True)
class Policy:
    type_weights: dict = field(default_factory=lambda: {'recognition': .55, 'recall': .8,
        'comprehension': .75, 'application': .9, 'production': 1.0})
    source_weights: dict = field(default_factory=lambda: {'placement_assessment': .4, 'tutor_chat': .55,
        'quiz': .8, 'exercise': .85, 'curriculum': 1., 'manual_review': .8})
    prior_strength: float = 2.
    prior_mean: float = .5
    recent_window: int = 6
    recent_weight: float = .3
    maximum_step: float = .08
    difficulty_limit: float = .2
    hint_penalty: float = .5
    legacy_quality: float = .35
    confidence_scale: float = 12.
    familiar_minimum: int = 5
    strong_minimum: int = 8
    familiar_score: float = .68
    strong_score: float = .85
    familiar_confidence: float = .35
    strong_confidence: float = .65
    recognition_confidence_cap: float = .45
    placement_confidence_cap: float = .35
    decline_recent: float = .5
    history_score_change: float = .05
    history_confidence_change: float = .1
    mastery_priority_bonus: float = 2.
    production_gap: float = .65
    weakest_dimension_share: float = .2
    unknown_hint_factor: float = .85
    minimum_consistency: float = .4
    diversity_base: float = .6
    diversity_increment: float = .1
    time_distribution_base: float = .7
    confidence_independent_minimum: int = 5
    developing_minimum: int = 3
    developing_score: float = .45
    decline_history: float = .68
    decline_failures: int = 3
    decline_window: int = 4


POLICY = Policy()
