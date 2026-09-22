"""Phase 4 owns session composition; this adapts a due queue to its activity contract."""
from app.learner.catalog import TOPICS
from app.mastery.catalog import curriculum_key
from app.review.content import title

def compose(plan,queue,request):
    if not queue['items']: return plan
    ratio=1. if request.session_type=='review' else .8 if queue['backlog'] else plan['strategy']['target_review_ratio']
    budget=request.available_minutes if request.session_type=='review' else max(2,int(request.available_minutes*ratio))
    selected=[]; used=0; seen=set()
    for item in queue['items']:
        if used+item['duration_minutes']>budget: continue
        topic=TOPICS[item['topic_id']]; dim=item['dimension']
        selected.append(dict(order=len(selected)+1,topic_id=topic.key,title=title(topic.key,dim),skill=topic.skill,
            activity_type='sentence_construction' if dim in ('production','application') else 'guided_practice',
            difficulty=topic.difficulty,duration_minutes=item['duration_minutes'],purpose='review',
            reason_codes=['persistent_difficulty' if item['persistent_difficulty'] else 'scheduled_review'],
            reason='Revisit the explanation, then try a different example.' if item['persistent_difficulty'] else 'Ready for a spaced review of '+dim.replace('_',' ')+'.',
            focus_dimension=dim,review_schedule_id=item['review_id'],review_version=item['version'],
            review_variant=item['review_count'],reteach=item['persistent_difficulty']))
        used+=item['duration_minutes']; seen.add(topic.key)
    if not selected: return plan
    if request.session_type!='review':
        for original in plan['activities']:
            if len(selected)>=7: break
            if curriculum_key(original['topic_id']) in seen: continue
            remaining=request.available_minutes-used
            if remaining<2: break
            a=dict(original); a['duration_minutes']=min(a['duration_minutes'],remaining); a['order']=len(selected)+1
            selected.append(a); used+=a['duration_minutes']; seen.add(curriculum_key(a['topic_id']))
    review_minutes=sum(a['duration_minutes'] for a in selected if a['purpose']=='review')
    plan.update(activities=selected,estimated_minutes=used,
        note='Your most useful due reviews come first. Remaining items will be available in a later session.')
    plan['strategy'].update(target_review_ratio=ratio,review_ratio=round(review_minutes/used,3),new_ratio=round(1-review_minutes/used,3))
    if queue['backlog']: plan['strategy']['name']='review_heavy'
    return plan
