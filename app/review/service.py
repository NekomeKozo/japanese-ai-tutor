import json
import logging
from datetime import datetime, timedelta
from uuid import NAMESPACE_URL, uuid5
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from app.errors import TutorError
from app.learner.catalog import TOPICS
from app.mastery.schemas import Evidence
from app.review.clock import Clock, utc
from app.review.policy import POLICY
from app.review.scheduler import ReviewScheduler

logger = logging.getLogger(__name__)

def exists(db):
    return bool(db.execute("SELECT 1 FROM sqlite_master WHERE name='review_schedules'").fetchone())

def identity(learner, topic, dimension):
    return str(uuid5(NAMESPACE_URL,f'review:{learner}:{topic}:{dimension}'))

def save(db, learner, topic, dimension, state, suspended=False):
    db.execute('INSERT INTO review_schedules VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(schedule_id) DO UPDATE SET '
        'due_at=excluded.due_at,suspended=excluded.suspended,version=excluded.version,state_json=excluded.state_json',
        (identity(learner,topic,dimension),learner,topic,dimension,state['due_at'],int(suspended),state['version'],json.dumps(state)))

def process_event(db, event_id):
    if not exists(db):
        return
    metadata = json.loads(db.execute('SELECT metadata_json FROM learning_events WHERE event_id=?',(str(event_id),)).fetchone()[0])
    rows = db.execute('SELECT payload FROM mastery_evidence WHERE event_id=? ORDER BY topic_id,dimension',(str(event_id),)).fetchall()
    for (payload,) in rows:
        e = Evidence.model_validate_json(payload)
        if e.quality < .5:
            continue  # Ambiguous legacy/chat observations are not retrieval trials.
        key=identity(e.learner_id,e.topic_id,e.dimension)
        if metadata.get('review_schedule_id') and metadata['review_schedule_id'] != key:
            continue
        if db.execute('SELECT 1 FROM review_attempts WHERE schedule_id=? AND event_id=?',(key,e.event_id)).fetchone():
            continue
        found=db.execute('SELECT state_json,suspended FROM review_schedules WHERE schedule_id=?',(key,)).fetchone()
        previous=json.loads(found[0]) if found else None
        if found and found[1]:
            continue
        mastery=json.loads(db.execute('SELECT state_json FROM topic_mastery WHERE learner_id=? AND topic_id=?',
            (e.learner_id,e.topic_id)).fetchone()[0])['dimensions'][e.dimension]
        now=utc(e.timestamp)
        if previous and now < datetime.fromisoformat(previous['last_reviewed_at']):
            logger.warning('Out-of-order review evidence left schedule unchanged')
            continue
        state=ReviewScheduler().process_review(previous,e,mastery,now)
        save(db,e.learner_id,e.topic_id,e.dimension,state)
        attempt=dict(evidence=e.model_dump(mode='json'),mastery=mastery,previous=previous,result=state)
        db.execute('INSERT INTO review_attempts VALUES (?,?,?,?,?)',(key,e.event_id,e.learner_id,now.isoformat(),json.dumps(attempt)))
        logger.info('Review completed: rating=%s lapse=%s persistent_difficulty=%s',state['last_rating'],
                    state['lapse_count']> (previous or {}).get('lapse_count',0),state['persistent_difficulty'])

def bootstrap(db, now, learner_id=None):
    now=utc(now)
    day_counts={}
    for learner,topic,payload in db.execute('SELECT learner_id,topic_id,state_json FROM topic_mastery WHERE (? IS NULL OR learner_id=?) ORDER BY learner_id,topic_id',(learner_id,learner_id)).fetchall():
        mastery=json.loads(payload)
        for dimension, value in mastery['dimensions'].items():
            if value['score'] is None:
                continue
            key=identity(learner,topic,dimension)
            if db.execute('SELECT 1 FROM review_schedules WHERE schedule_id=?',(key,)).fetchone():
                continue
            row=db.execute('SELECT payload FROM mastery_evidence WHERE learner_id=? AND topic_id=? AND dimension=? ORDER BY recorded_at DESC,event_id DESC LIMIT 1',(learner,topic,dimension)).fetchone()
            if not row:
                continue
            e=Evidence.model_validate_json(row[0])
            state=ReviewScheduler().schedule_new_item(None,e,value,now)
            strong=value['score']>=.8 and value['confidence']>=.5
            # At most ten newly bootstrapped targets per day; no immediate review storm.
            days=4 if strong else 1
            while day_counts.get((learner,days),0)>=10: days+=1
            slot=day_counts.get((learner,days),0); day_counts[(learner,days)]=slot+1
            # Spread inside a UTC day, avoiding midnight rollover between buckets.
            due=(now+timedelta(days=days)).replace(hour=9,minute=0,second=0,microsecond=0)+timedelta(minutes=slot*23)
            state.update(due_at=due.isoformat(),
                         last_reviewed_at=e.timestamp.isoformat(),review_count=0,daily_count=0,bootstrap=True)
            state['card']['due']=state['due_at']
            state['card']['last_review']=e.timestamp.isoformat()
            state['interval_days']=(datetime.fromisoformat(state['due_at'])-e.timestamp).total_seconds()/86400
            save(db,learner,topic,dimension,state)

class ReviewService:
    def __init__(self,repository,clock=None):
        self.repository=repository
        self.clock=clock or Clock()

    def owned(self,db,learner):
        self.repository.require_ready()
        if not db.execute('SELECT 1 FROM learner_state WHERE learner_id=?',(str(learner),)).fetchone():
            raise TutorError('learner_not_found','Learner not found.',404)

    def get_due_reviews(self,learner,minutes=20,skill=None):
        from app.review.queue import queue
        with self.repository.connection() as db:
            self.owned(db,learner)
            return queue(db,str(learner),utc(self.clock.now()),minutes,skill)

    def forecast(self,learner,timezone_name='UTC'):
        try:
            zone=ZoneInfo(timezone_name)
        except (ZoneInfoNotFoundError,ValueError) as exc:
            raise TutorError('invalid_timezone','Choose a valid timezone.',422) from exc
        now=utc(self.clock.now()); local=now.astimezone(zone)
        tomorrow=(local+timedelta(days=1)).replace(hour=0,minute=0,second=0,microsecond=0)
        bounds=[utc(tomorrow),utc(tomorrow+timedelta(days=1)),utc(tomorrow+timedelta(days=6))]
        with self.repository.connection() as db:
            self.owned(db,learner)
            counts=[db.execute('SELECT count(*) FROM review_schedules WHERE learner_id=? AND suspended=0 AND due_at<?',
                (str(learner),date.isoformat())).fetchone()[0] for date in bounds]
        return dict(today=counts[0],tomorrow=counts[1]-counts[0],next_7_days=counts[2],timezone=timezone_name)

    def suspend_review(self,learner,schedule_id,suspended=True):
        with self.repository.connection() as db:
            db.execute('BEGIN IMMEDIATE'); self.owned(db,learner)
            row=db.execute('SELECT topic_id,dimension,state_json FROM review_schedules WHERE learner_id=? AND schedule_id=?',(str(learner),str(schedule_id))).fetchone()
            if not row:
                raise TutorError('review_not_found','Review target not found.',404)
            state=json.loads(row[2]); state['version']+=1
            save(db,str(learner),row[0],row[1],state,suspended)

    def resume_review(self,learner,schedule_id):
        self.suspend_review(learner,schedule_id,False)

    def reschedule_topic(self,learner,topic):
        """Explicit maintenance replay. Preserve suspension and invalidate old plans."""
        with self.repository.connection() as db:
            db.execute('BEGIN IMMEDIATE'); self.owned(db,learner)
            for key,dim,payload,suspended in db.execute('SELECT schedule_id,dimension,state_json,suspended FROM review_schedules WHERE learner_id=? AND topic_id=?',(str(learner),topic)).fetchall():
                current=json.loads(payload); state=None
                rows=db.execute('SELECT payload FROM review_attempts WHERE schedule_id=? ORDER BY reviewed_at,event_id',(key,)).fetchall()
                if not rows:
                    continue
                for index,(attempt,) in enumerate(rows):
                    data=json.loads(attempt)
                    if index==0: state=data['previous']
                    evidence=Evidence.model_validate(data['evidence'])
                    state=ReviewScheduler().process_review(state,evidence,data['mastery'],evidence.timestamp)
                state['version']=current['version']+1
                save(db,str(learner),topic,dim,state,suspended)

    get_review_backlog = get_due_reviews
    get_high_priority_reviews = get_due_reviews
    get_review_load_estimate = get_due_reviews
