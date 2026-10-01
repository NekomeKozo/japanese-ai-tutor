import json
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4, uuid5

from app.errors import TutorError
from app.jlpt.schemas import Question, Start
from app.jlpt.scoring import evaluate, results
from app.jlpt.selection import select
from app.learner.catalog import TOPICS
from app.learner.events import process_event
from app.learner.schemas import LearningEvent


class JLPTService:
    def __init__(self, repository, bank, clock=None):
        self.repository, self.bank = repository, bank
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def _learner(self, db, learner):
        if not db.execute('SELECT 1 FROM learner_state WHERE learner_id=?', (str(learner),)).fetchone():
            raise TutorError('learner_not_found', 'Learner not found.', 404)

    def _load(self, db, learner, session):
        row = db.execute('SELECT request_json,bank_version,status,started_at,deadline_at,completed_at,version '
                         'FROM jlpt_sessions WHERE learner_id=? AND session_id=?', (str(learner),str(session))).fetchone()
        if not row:
            raise TutorError('jlpt_not_found', 'JLPT practice was not found for this learner.', 404)
        state = dict(zip(('request','bank_version','status','started_at','deadline_at','completed_at','version'),row))
        state['request'] = json.loads(state['request'])
        state.update(session_id=str(session), learner_id=str(learner))
        questions = [Question.model_validate_json(r[0]) for r in db.execute(
            'SELECT question_json FROM jlpt_session_questions WHERE session_id=? ORDER BY order_index', (str(session),))]
        attempts = {q:dict(submission_id=s,answer=a,correct=c,created_at=t) for q,s,a,c,t in db.execute(
            'SELECT question_id,submission_id,answer,correct,created_at FROM jlpt_attempts WHERE session_id=?',(str(session),))}
        return state, questions, attempts

    def _evidence(self, db, state, question, attempt):
        topic = TOPICS[question.topic_id]
        event_id = uuid5(UUID(state['session_id']), question.id)
        event = LearningEvent(event_id=event_id, learner_id=state['learner_id'],
            event_type='performance', topic_key=question.topic_id, skill=topic.skill,
            score=float(attempt['correct']), difficulty=question.difficulty, source='quiz')
        process_event(db, event, metadata_extra={'jlpt_session_id':state['session_id'],
            'jlpt_question_id':question.id, 'jlpt_bank_version':state['bank_version'],
            'mastery':{'dimension':question.dimension,
                'evidence_type':'recognition' if question.choices else 'recall',
                'activity_type':question.question_type, 'context_id':f'jlpt:{question.id}:v{question.version}',
                'quality':.8, 'hint_used':False, 'reading_context':question.reading_context}})

    def _close(self, db, state, questions, attempts, status='completed'):
        if state['status'] != 'in_progress':
            return
        if status == 'completed' and state['request']['mode'] == 'mock':
            # No learner/mastery/review side channel may reveal correctness during mock.
            for q in questions:
                if q.id in attempts:
                    self._evidence(db, state, q, attempts[q.id])
        ended = self.clock().isoformat()
        if state['deadline_at'] and status == 'completed':
            ended = min(ended, state['deadline_at'])
        db.execute('UPDATE jlpt_sessions SET status=?,completed_at=?,version=version+1 WHERE session_id=?',
                   (status,ended,state['session_id']))
        state.update(status=status,completed_at=ended,version=state['version']+1)

    def _expire(self, db, state, questions, attempts):
        if state['status']=='in_progress' and state['deadline_at'] and self.clock() >= datetime.fromisoformat(state['deadline_at']):
            self._close(db,state,questions,attempts)

    def _feedback(self, q, attempt):
        return {**q.public(), 'topic':TOPICS[q.topic_id].label, 'answer':attempt.get('answer'),
                'correct':bool(attempt.get('correct',0)), 'correct_answers':q.answers, 'explanation':q.explanation}

    def _public(self, state, questions, attempts):
        request = state['request']
        end = datetime.fromisoformat(state['completed_at']) if state['completed_at'] else self.clock()
        elapsed = max(0,int((end-datetime.fromisoformat(state['started_at'])).total_seconds()))
        remaining = max(0,int((datetime.fromisoformat(state['deadline_at'])-self.clock()).total_seconds())) if state['deadline_at'] else None
        out = {k:state[k] for k in ('session_id','bank_version','status','started_at','deadline_at','completed_at','version')}
        out.update({k:request[k] for k in ('level','section','mode','timed')})
        out.update(question_count=len(questions),answered_count=len(attempts),elapsed_seconds=elapsed,
                   remaining_seconds=remaining,question=None,feedback=None,result=None,review=[])
        if state['status']=='in_progress':
            current = next((q for q in questions if q.id not in attempts),None)
            out['question'] = current.public() if current else None
            if request['mode'] != 'mock' and attempts:
                last = next(q for q in reversed(questions) if q.id in attempts)
                out['feedback'] = self._feedback(last,attempts[last.id])
        elif state['status']=='completed':
            out['result'] = results(questions,attempts)
            out['review'] = [self._feedback(q,attempts.get(q.id,{})) for q in questions]
            out['result']['needs_review'] = sorted({TOPICS[q.topic_id].label for q in questions if q.id in attempts and not attempts[q.id]['correct']})
            out['result']['done_well'] = sorted({TOPICS[q.topic_id].label for q in questions if attempts.get(q.id,{}).get('correct')})
        return out

    def start(self, learner, body):
        self.repository.require_ready()
        with self.repository.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            self._learner(db,learner)
            previous = db.execute('SELECT learner_id,session_id,request_json FROM jlpt_sessions WHERE request_id=?',(str(body.request_id),)).fetchone()
            if previous:
                if previous[0] != str(learner) or previous[2] != body.model_dump_json():
                    raise TutorError('jlpt_request_conflict','That start request was already used.',409)
                state,questions,attempts = self._load(db,learner,previous[1])
                self._expire(db,state,questions,attempts)
                return self._public(state,questions,attempts)
            active = db.execute("SELECT session_id FROM jlpt_sessions WHERE learner_id=? AND status='in_progress'",(str(learner),)).fetchone()
            if active:
                current = self._load(db,learner,active[0])
                self._expire(db,*current)
                if current[0]['status']=='in_progress':
                    raise TutorError('jlpt_active','Resume or end your active JLPT practice first.',409)
            recent = {r[0] for r in db.execute('SELECT a.question_id FROM jlpt_attempts a JOIN jlpt_sessions s ON a.session_id=s.session_id '
                'WHERE s.learner_id=? ORDER BY a.created_at DESC LIMIT 40',(str(learner),))}
            weaknesses = {}
            if body.mode == 'weakness':
                for key,payload in db.execute('SELECT topic_key,recent_json FROM learner_topics WHERE learner_id=?',(str(learner),)):
                    scores = json.loads(payload)
                    if len(scores)>=3 and sum(scores)/len(scores)<.6:
                        weaknesses[key] = 1-sum(scores)/len(scores)
            chosen = select(self.bank,body,recent,weaknesses)
            session = str(uuid4()); now = self.clock()
            deadline = (now+timedelta(seconds=sum(120 if q.section=='reading' else 60 for q in chosen))).isoformat() if body.timed else None
            db.execute('INSERT INTO jlpt_sessions VALUES (?,?,?,?,?,?,?,?,?,?)',
                (session,str(learner),str(body.request_id),body.model_dump_json(),self.bank.version,'in_progress',now.isoformat(),deadline,None,0))
            for index,q in enumerate(chosen):
                db.execute('INSERT INTO jlpt_session_questions VALUES (?,?,?,?)',(session,q.id,index,q.model_dump_json()))
            return self._public(*self._load(db,learner,session))

    def get(self, learner, session):
        self.repository.require_ready()
        with self.repository.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            data=self._load(db,learner,session)
            self._expire(db,*data)
            return self._public(*data)

    def active(self, learner):
        self.repository.require_ready()
        with self.repository.connection() as db:
            db.execute('BEGIN IMMEDIATE'); self._learner(db,learner)
            row=db.execute("SELECT session_id FROM jlpt_sessions WHERE learner_id=? AND status='in_progress'",(str(learner),)).fetchone()
            if not row: return None
            data=self._load(db,learner,row[0]); self._expire(db,*data)
            # Return a newly expired result once so the UI can explain the deadline.
            return self._public(*data)

    def answer(self, learner, session, body):
        self.repository.require_ready()
        with self.repository.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            state,questions,attempts=self._load(db,learner,session)
            replay=db.execute('SELECT session_id,question_id,answer FROM jlpt_attempts WHERE submission_id=?',(str(body.submission_id),)).fetchone()
            if replay:
                if replay != (str(session),body.question_id,body.answer):
                    raise TutorError('jlpt_submission_conflict','That submission ID was used for another answer.',409)
                self._expire(db,state,questions,attempts)
                return self._public(state,questions,attempts)
            self._expire(db,state,questions,attempts)
            if state['status'] != 'in_progress':
                if state['deadline_at'] and self.clock()>=datetime.fromisoformat(state['deadline_at']):
                    return self._public(state,questions,attempts)
                raise TutorError('jlpt_closed','This practice has ended. Open its results or start another session.',409)
            current=next((q for q in questions if q.id not in attempts),None)
            if not current or current.id != body.question_id:
                raise TutorError('jlpt_question_conflict','This question has already been answered or is not current. Reload the saved practice.',409)
            correct=evaluate(current,body.answer)
            attempt=dict(answer=body.answer,correct=correct,submission_id=str(body.submission_id),created_at=self.clock().isoformat())
            db.execute('INSERT INTO jlpt_attempts VALUES (?,?,?,?,?,?)',
                (str(session),current.id,attempt['submission_id'],body.answer,correct,attempt['created_at']))
            if state['request']['mode']!='mock': self._evidence(db,state,current,attempt)
            db.execute('UPDATE jlpt_sessions SET version=version+1 WHERE session_id=?',(str(session),))
            state['version']+=1; attempts[current.id]=attempt
            return self._public(state,questions,attempts)

    def finish(self, learner, session, abandon=False):
        self.repository.require_ready()
        with self.repository.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            data=self._load(db,learner,session)
            self._expire(db,*data)
            self._close(db,*data,status='abandoned' if abandon else 'completed')
            return self._public(*data)

    def history(self, learner):
        self.repository.require_ready()
        with self.repository.connection() as db:
            self._learner(db,learner)
            rows=db.execute('SELECT s.session_id,s.request_json,s.status,s.started_at,s.completed_at,COUNT(q.question_id),COALESCE(SUM(a.correct),0) '
                'FROM jlpt_sessions s JOIN jlpt_session_questions q ON q.session_id=s.session_id '
                'LEFT JOIN jlpt_attempts a ON a.session_id=q.session_id AND a.question_id=q.question_id '
                'WHERE s.learner_id=? GROUP BY s.session_id,s.request_json,s.status,s.started_at,s.completed_at '
                'ORDER BY s.started_at DESC LIMIT 30',(str(learner),)).fetchall()
            output=[]
            for session,payload,status,started,ended,count,raw_correct in rows:
                request=json.loads(payload)
                correct=raw_correct if status=='completed' else None
                output.append(dict(session_id=session,status=status,started_at=started,completed_at=ended,
                    level=request['level'],mode=request['mode'],section=request['section'],question_count=count,
                    accuracy=round(100*correct/count,1) if correct is not None and count else None))
            return output

    def explanation(self, learner, session, question_id):
        """Explicit review is exposure only, once per saved question."""
        with self.repository.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            state, questions, attempts = self._load(db, learner, session)
            self._expire(db, state, questions, attempts)
            q = next((q for q in questions if q.id == question_id), None)
            available = state['status'] == 'completed' or (
                state['request']['mode'] != 'mock' and question_id in attempts)
            if not q or not available:
                raise TutorError('jlpt_feedback_unavailable', 'Finish this question or mock before reviewing its explanation.', 409)
            topic = TOPICS[q.topic_id]
            event = LearningEvent(event_id=uuid5(UUID(str(session)), 'explanation:'+q.id),
                learner_id=learner, event_type='concept_explained', topic_key=q.topic_id,
                skill=topic.skill, source='quiz')
            process_event(db, event, metadata_extra={'jlpt_session_id':str(session), 'jlpt_question_id':q.id})
            return self._feedback(q, attempts.get(q.id, {}))
