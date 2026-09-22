"""The only module importing FSRS; deterministic application policy wraps its output."""
import copy
import hashlib
from datetime import timedelta
from fsrs import Card, Scheduler, Rating, State
from app.review.clock import utc
from app.review.policy import POLICY
from app.review.ratings import rating

class ReviewScheduler:
    def __init__(self, policy=POLICY):
        self.policy = policy
        self.engine = Scheduler(desired_retention=policy.desired_retention, enable_fuzzing=False,
            learning_steps=(timedelta(minutes=policy.learning_minutes),),
            relearning_steps=(timedelta(minutes=policy.learning_minutes),), maximum_interval=policy.maximum_interval)

    def calculate_next_review(self, previous, evidence, mastery, now):
        now = utc(now)
        result = copy.deepcopy(previous) if previous else {}
        key = f'{evidence.learner_id}:{evidence.topic_id}:{evidence.dimension}'
        number = int(hashlib.sha256(key.encode()).hexdigest()[:12],16)
        card = Card.from_dict(result['card']) if result else Card(card_id=number,due=now)
        if card.last_review and now < card.last_review:
            raise ValueError('Review clock moved backwards')
        label = rating(evidence, mastery, self.policy)
        before_state = card.state
        updated, _ = self.engine.review_card(card, Rating[label.capitalize()], review_datetime=now)
        lapse = int(label == 'again' and before_state == State.Review)
        lapses = result.get('lapse_count',0) + lapse
        failures = result.get('consecutive_failures',0)+1 if label=='again' else 0
        persistent = lapses >= self.policy.persistent_lapses or failures >= self.policy.persistent_lapses
        today = now.date().isoformat()
        daily = result.get('daily_count',0)+1 if result.get('daily_date')==today else 1
        days = (updated.due-now).total_seconds()/86400
        if not previous:
            days = min(days,self.policy.initial_max_days)
        elif label!='again' and previous['interval_days']>=1:
            growth={'hard':self.policy.hard_growth_limit,'good':self.policy.good_growth_limit,'easy':self.policy.easy_growth_limit}[label]
            if evidence.evidence_type=='recognition': growth=min(growth,1.6)
            days=min(days,previous['interval_days']*growth)
        if mastery.get('confidence',0) < .35:
            days = min(days,self.policy.low_confidence_max_days)
        if mastery.get('status') == 'needs_review':
            days = min(days,1.)
        if daily >= self.policy.max_daily_attempts or persistent and label=='again':
            days = max(days,1.)
        # Deterministic spreading, separate from FSRS's disabled random fuzzing.
        if days >= 2:
            days *= .95 + (number % 1001)/10000
        days = max(self.policy.learning_minutes/1440,min(self.policy.maximum_interval,days))
        updated.due = now + timedelta(days=days)
        result.update(card=updated.to_dict(), state=updated.state.name.lower(), due_at=updated.due.isoformat(),
            last_reviewed_at=now.isoformat(), interval_days=days, review_count=result.get('review_count',0)+1,
            lapse_count=lapses, consecutive_failures=failures, persistent_difficulty=persistent,
            daily_date=today,daily_count=daily,algorithm_version=self.policy.algorithm_version,
            algorithm='fsrs-6.3.2/application-v1',created_at=result.get('created_at',now.isoformat()),
            updated_at=now.isoformat(),last_rating=label,version=result.get('version',0)+1)
        return result

    schedule_new_item = calculate_next_review
    process_review = calculate_next_review
