from dataclasses import dataclass


@dataclass(frozen=True)
class Policy:
    base_review: float = .5
    minimum_review: float = .25
    maximum_review: float = .85
    weak_bonus: float = 4
    repeated_error_bonus: float = 3
    age_bonus: float = 1.5
    goal_bonus: float = 2
    underexposure_bonus: float = 1.5
    repetition_penalty: float = 1.3
    partial_prerequisite_penalty: float = 1.5
    maximum_difficulty_jump: float = 1
    history_days: int = 7
    returning_days: int = 30


DEFAULT_POLICY = Policy()
GOAL_WEIGHTS = {
    'general': {'grammar':1,'vocabulary':1,'kanji':.8,'reading':1,'sentence_construction':1},
    'JLPT': {'grammar':1.3,'vocabulary':1.2,'kanji':1.2,'reading':1.3,'sentence_construction':.5},
    'conversation': {'grammar':1,'vocabulary':1.3,'kanji':.5,'reading':.7,'sentence_construction':1.4},
    'travel': {'grammar':1,'vocabulary':1.4,'kanji':.7,'reading':1.2,'sentence_construction':1.2},
    'work': {'grammar':1.1,'vocabulary':1.2,'kanji':.8,'reading':1.1,'sentence_construction':1.3},
    'university': {'grammar':1.1,'vocabulary':1.2,'kanji':1,'reading':1.4,'sentence_construction':1.1},
}
REASONS = {
    'mastery_decline':'Recent evidence suggests revisiting a previously familiar topic.',
    'mastery_dimension':'Practice a weaker part of your knowledge of this topic.',
    'needs_review':'Recent attempts suggest this topic needs practice.',
    'repeated_recent_errors':'This topic has caused repeated recent mistakes.',
    'prerequisite_reinforcement':'This foundation supports topics you can study next.',
    'underrepresented_skill':'This skill has received less practice recently.',
    'long_time_since_review':'Revisit this previously studied topic after a gap.',
    'learner_requested_focus':'Selected for the focus you requested.',
    'goal_alignment':'This topic supports your learning goal.',
    'appropriate_next_topic':'An introductory next step within your current skill range.',
    'reinforcement':'Reinforce a topic you have already encountered.',
    'beginner_foundation':'Start with a foundation; there is not enough evidence for detailed personalization.',
}
