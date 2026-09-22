import json
from datetime import datetime
from app.learner.catalog import TOPICS
from app.review.policy import POLICY

def duration(kind,dimension):
    return 4 if kind=='grammar' and dimension in ('production','application') else 3 if dimension=='production' else 2

def queue(db,learner,now,minutes,skill=None):
    from app.review.content import supported
    from app.curriculum.catalog import CATALOG
    from app.mastery.catalog import curriculum_key
    preferences=json.loads(db.execute('SELECT preferences_json FROM learner_state WHERE learner_id=?',(learner,)).fetchone()[0])
    rows=db.execute('SELECT r.schedule_id,r.topic_id,r.dimension,r.state_json,m.state_json,r.due_at FROM review_schedules r '
        'LEFT JOIN topic_mastery m ON m.learner_id=r.learner_id AND m.topic_id=r.topic_id '
        'WHERE r.learner_id=? AND r.suspended=0 AND r.due_at<=? ORDER BY r.due_at,r.schedule_id',(learner,now.isoformat())).fetchall()
    candidates=[]; kinds=dict(vocabulary=0,grammar=0,kanji=0); unsupported=0
    for key,topic,dim,payload,mastery_json,due_at in rows:
        t=TOPICS[topic]
        if skill and t.kind!=skill: continue
        if not supported(topic,dim): unsupported+=1; continue
        state=json.loads(payload); mastery=json.loads(mastery_json) if mastery_json else {}
        m=mastery.get('dimensions',{}).get(dim,{})
        days=max(0,(now-datetime.fromisoformat(due_at)).total_seconds()/86400)
        overdue=4*min(1,days/14)
        foundation=max(0,1-t.difficulty/7)
        prerequisite=any(topic in tuple(curriculum_key(p) for p in c.prerequisites) for c in CATALOG.values())
        goals=next((c.goals for c in CATALOG.values() if curriculum_key(c.key)==topic),())
        aligned=preferences.get('primary_goal') in goals
        score=m.get('score') if m.get('score') is not None else .5
        priority=overdue+foundation+int(prerequisite)+int(aligned)+(1-score)*m.get('confidence',0)+min(2,state['lapse_count']*.4)+int(state['persistent_difficulty'])+int(m.get('status')=='needs_review')
        kinds[t.kind]+=1
        candidates.append(dict(review_id=key,topic_id=topic,title=t.label,topic_type=t.kind,skill=t.skill,
            dimension=dim,due_at=due_at,duration_minutes=duration(t.kind,dim),
            priority='high' if priority>=3 else 'normal',_rank=priority,version=state['version'],
            persistent_difficulty=state['persistent_difficulty'],review_count=state['review_count']))
    candidates.sort(key=lambda c:(-c['_rank'],c['due_at'],c['review_id']))
    selected=[]; used=0; seen=set(); available=min(minutes,POLICY.max_review_minutes)
    remaining=list(candidates)
    while remaining and len(selected)<POLICY.max_reviews_per_session:
        fits=[c for c in remaining if c['topic_id'] not in seen and c['duration_minutes']+used<=available]
        if not fits: break
        if selected:
            varied=[c for c in fits if c['topic_type']!=selected[-1]['topic_type']]
            if varied: fits=varied
        item=fits[0]; selected.append(item); remaining.remove(item); seen.add(item['topic_id']); used+=item['duration_minutes']
    for item in candidates: item.pop('_rank')
    return dict(due_count=len(candidates),estimated_minutes=sum(c['duration_minutes'] for c in candidates),
        selected_minutes=used,counts=kinds,backlog=len(candidates)>=POLICY.backlog_threshold,
        items=selected,unsupported_count=unsupported,remaining_count=len(candidates)-len(selected))
