from dataclasses import dataclass

@dataclass(frozen=True)
class ReviewPolicy:
    algorithm_version: int = 1
    desired_retention: float = .9
    maximum_interval: int = 365
    again_below: float = .45
    good_at: float = .7
    easy_at: float = .9
    easy_confidence: float = .35
    learning_minutes: int = 15
    max_daily_attempts: int = 3
    persistent_lapses: int = 4
    max_reviews_per_session: int = 7
    max_review_minutes: int = 45
    backlog_threshold: int = 20
    initial_max_days: float = 3
    low_confidence_max_days: float = 7
    good_growth_limit: float = 2.5
    easy_growth_limit: float = 3.
    hard_growth_limit: float = 1.2

POLICY = ReviewPolicy()
