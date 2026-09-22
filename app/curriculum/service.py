import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from app.assessment.schemas import AnswerRequest, Question
from app.curriculum.catalog import CATALOG_VERSION
from app.curriculum.content import ContentService, teaching_reply
from app.curriculum.planner import build_plan
from app.curriculum.schemas import Lesson, StudyPlan
from app.errors import TutorError
from app.learner.events import process_event
from app.learner.initialization import now_iso
from app.learner.schemas import LearningEvent

logger=logging.getLogger(__name__)


class CurriculumService:
    def __init__(self,repository,learners,provider,evaluator,timeout):
        self.repository,self.learners=repository,learners
        self.content=ContentService(provider,timeout)
        self.evaluator=evaluator
        self.busy=set()
        from app.review.service import ReviewService
        self.reviews=ReviewService(repository)

    def _review_current(self,db,learner,activity):
        if not activity.get('review_schedule_id'): return
        row=db.execute('SELECT version,suspended FROM review_schedules WHERE learner_id=? AND schedule_id=?',
            (str(learner),str(activity['review_schedule_id']))).fetchone()
        if not row or row[1] or row[0]!=activity['review_version']:
            raise TutorError('review_changed','This review changed after the plan was made. Skip it and create a fresh plan.',409)

    def _owned(self,db,learner_id,session_id):
        row=db.execute('SELECT status,plan_json,created_at,started_at,completed_at FROM study_sessions WHERE learner_id=? AND session_id=?',
            (str(learner_id),str(session_id))).fetchone()
        if not row: raise TutorError('study_not_found','Study session not found for this learner.',404)
        return row

    def _activity(self,db,learner_id,session_id,activity_id):
        session=self._owned(db,learner_id,session_id)
        row=db.execute('SELECT status,content_json,result_json,submission_id,fingerprint FROM study_activities WHERE session_id=? AND activity_id=?',
            (str(session_id),str(activity_id))).fetchone()
        if not row: raise TutorError('activity_not_found','Activity not found in this study session.',404)
        return session,row

    def _current(self,db,session_id):
        row=db.execute("SELECT activity_id FROM study_activities WHERE session_id=? AND status IN ('not_started','in_progress') ORDER BY order_index LIMIT 1",(str(session_id),)).fetchone()
        return row[0] if row else None

    def _lifecycle(self,db,learner_id,session_id,kind,activity=None):
        activity=activity or {}
        event_id=str(uuid5(NAMESPACE_URL,f'study:{session_id}:{activity.get("activity_id","")}:{kind}'))
        metadata=json.dumps({k:activity[k] for k in ('activity_id','activity_type','purpose') if k in activity})
        db.execute('INSERT OR IGNORE INTO learning_events VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
            (event_id,str(learner_id),kind,activity.get('topic_id'),activity.get('skill'),None,activity.get('difficulty'),
             'curriculum',str(session_id),event_id,metadata,now_iso()))

    def history(self,learner_id):
        self.repository.require_ready()
        cutoff=(datetime.now(timezone.utc)-timedelta(days=7)).isoformat()
        with self.repository.connection() as db:
            distribution=dict(db.execute("SELECT a.skill,SUM(a.duration_minutes) FROM study_activities a JOIN study_sessions s ON s.session_id=a.session_id WHERE s.learner_id=? AND a.status='completed' AND a.completed_at>=? GROUP BY a.skill",(str(learner_id),cutoff)))
            counts=dict(db.execute("SELECT topic_id,COUNT(DISTINCT session_id) FROM study_activities WHERE status IN ('completed','skipped') AND session_id IN (SELECT session_id FROM study_sessions WHERE learner_id=? AND started_at IS NOT NULL ORDER BY created_at DESC LIMIT 4) GROUP BY topic_id",(str(learner_id),)))
            last=db.execute("SELECT MAX(created_at) FROM learning_events WHERE learner_id=? AND event_type IN ('performance','concept_explained','requested_help','assessment_completed')",(str(learner_id),)).fetchone()[0]
        return {'skill_minutes':distribution,'topic_sessions':counts,'last_learning_at':last}

    def active(self,learner_id):
        self.learners.profile(learner_id)
        with self.repository.connection() as db:
            row=db.execute("SELECT session_id FROM study_sessions WHERE learner_id=? AND status IN ('planned','in_progress')",(str(learner_id),)).fetchone()
        return self.get(learner_id,row[0]) if row else None

    def create(self,request):
        active=self.active(request.learner_id)
        if active:
            logger.info('Active curriculum plan resumed')
            return active
        profile=self.learners.profile(request.learner_id)
        from app.mastery.service import MasteryService
        profile['mastery'] = MasteryService(self.repository).curriculum_signals(request.learner_id)
        plan=build_plan(profile,request,self.history(request.learner_id))
        from app.review.composition import compose
        focus=request.requested_focus or (request.session_type if request.session_type in ('grammar','vocabulary','kanji','reading','sentence_construction') else None)
        due=self.reviews.get_due_reviews(request.learner_id,request.available_minutes,focus)
        plan=compose(plan,due,request)
        key=str(uuid4())
        for activity in plan['activities']: activity['activity_id']=str(uuid4())
        plan=StudyPlan.model_validate(plan).model_dump(mode='json')
        with self.repository.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            # Cross-process race: the winner's existing plan is returned unchanged.
            existing=db.execute("SELECT session_id FROM study_sessions WHERE learner_id=? AND status IN ('planned','in_progress')",(str(request.learner_id),)).fetchone()
            if existing: key=existing[0]
            else:
                db.execute('INSERT INTO study_sessions VALUES (?,?,?,?,?,?,?,?,?)',
                    (key,str(request.learner_id),'planned',request.model_dump_json(),json.dumps(plan,ensure_ascii=False),CATALOG_VERSION,now_iso(),None,None))
                for a in plan['activities']:
                    db.execute('INSERT INTO study_activities VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                        (a['activity_id'],key,a['order'],a['topic_id'],a['skill'],a['activity_type'],a['difficulty'],a['duration_minutes'],
                         'not_started',None,None,None,None,None))
                logger.info('Curriculum plan saved')
        return self.get(request.learner_id,key)

    def get(self,learner_id,session_id):
        self.repository.require_ready()
        with self.repository.connection() as db:
            status,plan_json,created,started,completed=self._owned(db,learner_id,session_id)
            plan=json.loads(plan_json)
            rows={key:(state,result) for key,state,result in db.execute('SELECT activity_id,status,result_json FROM study_activities WHERE session_id=?',(str(session_id),))}
        for a in plan['activities']:
            a['status']=rows[a['activity_id']][0]
            a['result']=json.loads(rows[a['activity_id']][1]) if rows[a['activity_id']][1] else None
        plan.update(session_id=str(session_id),learner_id=str(learner_id),status=status,created_at=created,started_at=started,completed_at=completed)
        plan['current_activity_id']=next((a['activity_id'] for a in plan['activities'] if a['status'] in ('not_started','in_progress')),None)
        plan['recap']=None
        if status=='completed':
            done=[a for a in plan['activities'] if a['status']=='completed']
            plan['recap']={'practiced':[a['title'] for a in done],
                'strong_performance':[a['title'] for a in done if a['result']['score']>=.8],
                'needs_review':[a['title'] for a in done if a['result']['score']<.6],
                'skipped_count':sum(a['status']=='skipped' for a in plan['activities']),
                'note':'This recap reflects these activities only. The next plan will use your updated learning evidence.'}
        return plan

    def start(self,learner_id,session_id):
        with self.repository.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            state=self._owned(db,learner_id,session_id)[0]
            if state not in ('planned','in_progress'): raise TutorError('study_closed','This study session has ended.',409)
            db.execute("UPDATE study_sessions SET status='in_progress',started_at=COALESCE(started_at,?) WHERE session_id=?",(now_iso(),str(session_id)))
            self._lifecycle(db,learner_id,session_id,'study_session_started')
        return self.get(learner_id,session_id)

    async def open_activity(self,learner_id,session_id,activity_id):
        key=str(activity_id)
        if key in self.busy: raise TutorError('activity_busy','Wait for the current activity request.',409)
        self.busy.add(key)
        try:
            with self.repository.connection() as db:
                session,row=self._activity(db,learner_id,session_id,activity_id)
                if row[1]:
                    return {'activity_id':key,'status':row[0],'response':teaching_reply(Lesson.model_validate_json(row[1])),'result':json.loads(row[2]) if row[2] else None}
                if session[0]!='in_progress' or self._current(db,session_id)!=key:
                    raise TutorError('activity_order','Start the session and finish or skip the current activity first.',409)
                activity=next(a for a in json.loads(session[1])['activities'] if a['activity_id']==key)
                self._review_current(db,learner_id,activity)
            lesson=await self.content.generate(activity,self.learners.profile(learner_id))
            with self.repository.connection() as db:
                db.execute('BEGIN IMMEDIATE')
                session,row=self._activity(db,learner_id,session_id,activity_id)
                self._review_current(db,learner_id,activity)
                if session[0]!='in_progress' or self._current(db,session_id)!=key:
                    raise TutorError('activity_conflict','This study session changed. Reload it to continue.',409)
                if row[1]: lesson=Lesson.model_validate_json(row[1])
                else:
                    db.execute("UPDATE study_activities SET content_json=?,status='in_progress' WHERE activity_id=?",(lesson.model_dump_json(),key))
                    event=LearningEvent(event_id=uuid5(UUID(key),'exposure'),learner_id=learner_id,event_type='concept_explained',topic_key=activity['topic_id'],
                        skill=activity['skill'],difficulty=activity['difficulty'],source='curriculum')
                    process_event(db,event,session_id=session_id)
            return {'activity_id':key,'status':'in_progress','response':teaching_reply(lesson),'result':None}
        finally: self.busy.discard(key)

    async def complete_activity(self,learner_id,session_id,activity_id,request):
        key=str(activity_id)
        fingerprint=hashlib.sha256(request.model_dump_json().encode()).hexdigest()
        if key in self.busy: raise TutorError('activity_busy','Wait for the current activity request.',409)
        self.busy.add(key)
        try:
            with self.repository.connection() as db:
                session,row=self._activity(db,learner_id,session_id,activity_id)
                if row[0]=='completed':
                    if row[3]==str(request.submission_id) and row[4]==fingerprint: return json.loads(row[2])
                    raise TutorError('activity_conflict','This activity already has a submitted result.',409)
                if session[0]!='in_progress' or row[0]!='in_progress' or self._current(db,session_id)!=key:
                    raise TutorError('activity_order','Open the current activity before submitting an answer.',409)
                activity=next(a for a in json.loads(session[1])['activities'] if a['activity_id']==key)
                lesson=Lesson.model_validate_json(row[1])
                self._review_current(db,learner_id,activity)
            question=Question(id=key,skill=activity['skill'],topic=activity['topic_id'],difficulty=activity['difficulty'],
                jlpt_reference=None,question_type='multiple_choice' if lesson.choices else 'sentence_construction',
                prompt=lesson.prompt,choices=lesson.choices,answers=lesson.answers,explanation=lesson.feedback,evaluation=lesson.evaluation,source='generated')
            grade=await self.evaluator.evaluate(question,AnswerRequest(question_id=key,submission_id=request.submission_id,answer=request.answer))
            if grade.score is None: raise TutorError('grading_unavailable','Your answer could not be graded. It was not counted as incorrect. Retry or skip.',503)
            result={'score':grade.score,'feedback':grade.detail.feedback_internal if grade.detail else lesson.feedback,
                'reference_answers':lesson.answers,'method':grade.method}
            with self.repository.connection() as db:
                db.execute('BEGIN IMMEDIATE')
                session,row=self._activity(db,learner_id,session_id,activity_id)
                if row[0]=='completed' and row[3]==str(request.submission_id) and row[4]==fingerprint: return json.loads(row[2])
                if session[0]!='in_progress' or row[0]!='in_progress' or self._current(db,session_id)!=key:
                    raise TutorError('activity_conflict','This activity changed before the answer was saved.',409)
                if db.execute('SELECT 1 FROM study_activities WHERE submission_id=?',(str(request.submission_id),)).fetchone():
                    raise TutorError('submission_conflict','Use a new submission ID for each activity.',409)
                self._review_current(db,learner_id,activity)
                db.execute("UPDATE study_activities SET status='completed',result_json=?,submission_id=?,fingerprint=?,completed_at=? WHERE activity_id=?",
                    (json.dumps(result,ensure_ascii=False),str(request.submission_id),fingerprint,now_iso(),key))
                event=LearningEvent(event_id=uuid5(UUID(key),'performance'),learner_id=learner_id,event_type='performance',
                    topic_key=activity['topic_id'],skill=activity['skill'],score=grade.score,difficulty=activity['difficulty'],source='curriculum')
                from app.mastery.context import task_context
                from app.curriculum.catalog import CATALOG
                fixed = not activity.get('review_schedule_id') and bool(CATALOG[activity['topic_id']].prompt)
                level_row = db.execute('SELECT estimate FROM skill_state WHERE learner_id=? AND skill=?',
                    (str(learner_id), activity['skill'])).fetchone()
                mastery = task_context(activity['topic_id'], activity['skill'], lesson.prompt,
                    question.question_type, lesson.evaluation, fixed=fixed,
                    level=level_row[0] if level_row else None, focus=activity.get('focus_dimension'))
                if activity.get('review_schedule_id'):
                    mastery.update(dimension=activity['focus_dimension'],hint_used=bool(activity.get('reteach')),
                        evidence_type='recognition' if lesson.choices else 'production' if activity['focus_dimension']=='production' else 'application' if activity['focus_dimension']=='application' else 'comprehension' if activity['focus_dimension']=='understanding' else 'recall',
                        reading_context=lesson.reading_context)
                process_event(db,event,session_id=session_id,metadata_extra={
                    'activity_id':key,'activity_type':activity['activity_type'],'purpose':activity['purpose'],
                    'grading_method':grade.method,'fixed_template':fixed,'mastery':mastery,
                    'review_schedule_id':activity.get('review_schedule_id')})
                if activity.get('review_schedule_id'):
                    result['next_review']=db.execute('SELECT due_at FROM review_schedules WHERE schedule_id=?',
                        (activity['review_schedule_id'],)).fetchone()[0]
                    db.execute('UPDATE study_activities SET result_json=? WHERE activity_id=?',(json.dumps(result,ensure_ascii=False),key))
                self._lifecycle(db,learner_id,session_id,'study_activity_completed',activity)
            return result
        finally: self.busy.discard(key)

    def skip(self,learner_id,session_id,activity_id):
        key=str(activity_id)
        with self.repository.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            session,row=self._activity(db,learner_id,session_id,activity_id)
            if row[0]=='skipped': return self.get(learner_id,session_id)
            if session[0]!='in_progress' or self._current(db,session_id)!=key:
                raise TutorError('activity_order','Only the current activity can be skipped.',409)
            activity=next(a for a in json.loads(session[1])['activities'] if a['activity_id']==key)
            db.execute("UPDATE study_activities SET status='skipped',completed_at=? WHERE activity_id=?",(now_iso(),key))
            self._lifecycle(db,learner_id,session_id,'study_activity_skipped',activity)
        return self.get(learner_id,session_id)

    def finish(self,learner_id,session_id,abandon=False):
        target='abandoned' if abandon else 'completed'
        with self.repository.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            state=self._owned(db,learner_id,session_id)[0]
            if state==target: return self.get(learner_id,session_id)
            if state not in ('planned','in_progress') or (not abandon and (state!='in_progress' or self._current(db,session_id))):
                raise TutorError('study_incomplete','Complete or skip the remaining activities before finishing.',409)
            now=now_iso()
            db.execute('UPDATE study_sessions SET status=?,completed_at=? WHERE session_id=?',(target,now,str(session_id)))
            self._lifecycle(db,learner_id,session_id,'study_session_'+target)
            db.execute('UPDATE learner_state SET last_activity_at=?,updated_at=? WHERE learner_id=?',(now,now,str(learner_id)))
        return self.get(learner_id,session_id)
