"""Pure deterministic ranking/planning functions; storage and LLM calls live elsewhere."""
import logging
from datetime import datetime, timezone

from app.curriculum.catalog import CATALOG, REVIEW_ONLY
from app.curriculum.policy import DEFAULT_POLICY, GOAL_WEIGHTS, REASONS
from app.mastery.catalog import curriculum_key
from app.mastery.policy import POLICY as MASTERY_POLICY

logger = logging.getLogger(__name__)


def age_days(value, now):
    if not value: return 0
    return max(0, (now - datetime.fromisoformat(value)).total_seconds() / 86400)


def ability(profile, skill):
    state = profile['skills'].get(skill, {})
    estimate = state.get('estimate')
    if estimate is None:
        return 0.0  # No global JLPT fallback for an unmeasured skill.
    recent = state.get('recent_average')
    adjustment = 0
    if state.get('recent_count',0) >= 3 and recent is not None:
        adjustment = -.5 if recent < .5 else .5 if recent >= .9 else 0
    return max(0, min(14, estimate + adjustment))


def prerequisite_status(key, profile, states, catalog=CATALOG):
    state = states.get(key)
    if state:
        if state['status'] in ('strong','familiar'): return 'satisfied'
        if state['status'] == 'needs_review': return 'not_satisfied'
        # Mere exposure does not demonstrate readiness.
        if state.get('recent_score') is not None and state['recent_score'] >= .6:
            return 'partially_satisfied'
    topic = catalog[key]
    skill = profile['skills'].get(topic.skill,{})
    if skill.get('placement_evidence',0) >= 2 and skill.get('confidence',0) >= .35 and ability(profile,topic.skill) >= topic.difficulty + 1:
        return 'partially_satisfied'  # Placement is a prior, not topic mastery.
    return 'unknown'


def strategy(profile, request, now, policy=DEFAULT_POLICY):
    scores = [s['recent_average'] for s in profile['skills'].values() if s.get('recent_count',0)>=3 and s.get('recent_average') is not None]
    avg = sum(scores)/len(scores) if scores else None
    ratio = policy.base_review
    weak_count = len(profile['weak_topics'])
    ratio += min(.2, .05 * weak_count)
    if avg is not None: ratio += max(-.2,min(.2,(.75-avg)*.5))
    if profile['placement_confidence'] < .35: ratio += .1
    returning = age_days(profile.get('last_activity_at'),now) >= policy.returning_days
    if returning: ratio += .2
    if request.session_type == 'review': ratio = 1.0
    elif request.session_type == 'new_material': ratio -= .15
    ratio = round(max(policy.minimum_review,min(policy.maximum_review,ratio)),2) if request.session_type!='review' else 1.0
    name = 'quick_session' if request.available_minutes<=10 or request.session_type=='quick_practice' else 'review_heavy' if ratio>=.65 else 'progression' if ratio<.45 else 'goal_focused' if profile['preferences']['primary_goal']!='general' else 'balanced'
    return {'name':name,'target_review_ratio':ratio,'returning_learner':returning}


def rank_candidates(profile, request, history, now, policy=DEFAULT_POLICY, catalog=CATALOG):
    states = {t['topic_key']:t for t in profile['topic_memory']}
    mistakes = {m['mistake_key']:m for m in profile['common_mistakes'] if m['status']=='active'}
    focus = request.requested_focus or (request.session_type if request.session_type in ('grammar','vocabulary','kanji','reading','sentence_construction') else None)
    goal = profile['preferences']['primary_goal']
    weights = GOAL_WEIGHTS.get('JLPT' if goal.startswith('JLPT') else goal, GOAL_WEIGHTS['general'])
    distribution = history.get('skill_minutes',{})
    total = sum(distribution.values())
    counts = history.get('topic_sessions',{})
    weak_skills = {t['skill'] for t in profile['weak_topics'] if t['topic_key'] not in catalog}
    # Raise prerequisites of blocked, nearby content to build a path forward.
    foundations = set()
    for topic in catalog.values():
        if topic.difficulty <= ability(profile,topic.skill)+policy.maximum_difficulty_jump:
            for key in topic.prerequisites:
                if prerequisite_status(key,profile,states,catalog) in ('not_satisfied','unknown'):
                    foundations.add(key)
    ranked=[]
    for topic in catalog.values():
        if focus and topic.skill != focus: continue
        if topic.key in REVIEW_ONLY and topic.key not in states: continue
        skill_state=profile['skills'].get(topic.skill,{})
        if not focus and topic.skill in ('hiragana','katakana') and 'Strong' in skill_state.get('estimated_level',''):
            script=states.get(topic.key,{})
            if script.get('recent_score',1) is None or script.get('recent_score',1)>=.8:
                continue
        target=ability(profile,topic.skill)
        review_margin=1 if topic.key in states and states[topic.key].get('recent_score') is not None else 0
        if topic.difficulty > target+policy.maximum_difficulty_jump+review_margin: continue
        prerequisites = {key:prerequisite_status(key,profile,states,catalog) for key in topic.prerequisites}
        if any(s in ('not_satisfied','unknown') for s in prerequisites.values()):
            logger.debug('Curriculum candidate blocked by prerequisites: %s',topic.key)
            continue
        state=states.get(topic.key)
        mastery = profile.get('mastery', {}).get(curriculum_key(topic.key))
        dimension_focus = None
        seen=bool(state and state['encounters'])
        reasons=[]
        score=1 + weights.get(topic.skill,.7)
        if mastery and mastery['evidence_count'] >= 3:
            score += MASTERY_POLICY.mastery_priority_bonus * mastery['confidence'] * (.7 - mastery['score'])
            if mastery['status'] == 'needs_review':
                score += MASTERY_POLICY.mastery_priority_bonus * mastery['confidence']
                reasons.append('mastery_decline')
            supported = (('production', 'reading') if topic.skill == 'vocabulary' else
                         ('production', 'application') if topic.skill == 'grammar' else
                         ('on_reading',) if topic.key == 'kanji_gaku_reading' else ())
            for dimension in supported:
                value = mastery['dimensions'].get(dimension, {})
                if value.get('score') is not None and value['score'] < MASTERY_POLICY.production_gap and value.get('evidence_count',0) >= 2:
                    dimension_focus = dimension
                    score += MASTERY_POLICY.mastery_priority_bonus * value['confidence']
                    reasons.insert(0, 'mastery_dimension')
                    break
        if topic.skill in weak_skills:
            score+=policy.weak_bonus/2
            reasons.append('prerequisite_reinforcement')
        if state and state['status']=='needs_review': score+=policy.weak_bonus; reasons.append('needs_review')
        if topic.key in mistakes and mistakes[topic.key]['recent_occurrences']>=3:
            score+=policy.repeated_error_bonus; reasons.insert(0,'repeated_recent_errors')
        if state and state.get('recent_score') is not None:
            # One failure has only a small influence; repeated evidence drives major review.
            evidence=min(state['correct_count']+state['incorrect_count'],3)/3
            score+=(1-state['recent_score'])*evidence
            if state['status']=='strong': score-=2
        if seen:
            days=age_days(state['last_seen_at'],now)
            score+=min(1,days/30)*policy.age_bonus
            if days>=30: reasons.append('long_time_since_review')
        if topic.key in foundations: score+=1; reasons.append('prerequisite_reinforcement')
        if goal in topic.goals or goal.startswith('JLPT') and topic.skill in ('grammar','kanji','reading','vocabulary'):
            score+=policy.goal_bonus; reasons.append('goal_alignment')
        if total and distribution.get(topic.skill,0)/total<.15:
            score+=policy.underexposure_bonus; reasons.append('underrepresented_skill')
        score-=policy.repetition_penalty*counts.get(topic.key,0)
        score-=abs(topic.difficulty-target)*.2
        score-=policy.partial_prerequisite_penalty*sum(s=='partially_satisfied' for s in prerequisites.values())
        if focus: reasons.insert(0,'learner_requested_focus')
        if not reasons: reasons=['reinforcement' if seen else 'beginner_foundation' if profile['profile_source']=='default' else 'appropriate_next_topic']
        # The topic establishes an upper bound; review can be simplified after struggle.
        difficulty=round(max(0,min(topic.difficulty,target+policy.maximum_difficulty_jump)),2)
        if state and state.get('recent_score') is not None and state['recent_score']<.5: difficulty=max(0,difficulty-.5)
        ranked.append({'topic_id':topic.key,'title':topic.title,'skill':topic.skill,'difficulty':difficulty,
            'activity_type':'sentence_construction' if dimension_focus == 'production' and topic.skill=='grammar' else topic.activity_type,
            'focus_dimension':dimension_focus,'purpose':'review' if seen else 'new_material',
            'reason_codes':reasons,'reason':REASONS[reasons[0]],'priority':round(score,4),'prerequisites':prerequisites})
    return sorted(ranked,key=lambda c:(-c['priority'],c['difficulty'],c['topic_id']))


def build_plan(profile,request,history=None,now=None,policy=DEFAULT_POLICY,catalog=CATALOG):
    now=now or datetime.now(timezone.utc)
    history=history or {}
    # Opening a chat window is not study evidence and must not erase a long study gap.
    strategy_profile={**profile,'last_activity_at':history['last_learning_at']} if history.get('last_learning_at') else profile
    chosen_strategy=strategy(strategy_profile,request,now,policy)
    candidates=rank_candidates(profile,request,history,now,policy,catalog)
    if not candidates:
        # Fixed foundations are always safe. Never relax prerequisites to force advanced content.
        fallback_focus=request.requested_focus or (request.session_type if request.session_type in ('grammar','vocabulary','kanji','reading','sentence_construction') else None)
        key={'grammar':'verb_forms','kanji':'kanji_numbers','reading':'reading_signs','sentence_construction':'copula_desu'}.get(fallback_focus,'vocab_greetings')
        topic=CATALOG[key]
        candidates=[{'topic_id':key,'title':topic.title,'skill':topic.skill,'difficulty':0,'activity_type':topic.activity_type,
            'purpose':'new_material','reason_codes':['beginner_foundation'],'reason':REASONS['beginner_foundation'],'priority':0,'prerequisites':{}}]
    minutes=request.available_minutes
    count=min(len(candidates),1 if minutes<10 else 2 if minutes<15 else 3 if minutes<25 else 5 if minutes<45 else 7)
    selected=[]
    for index in range(count):
        reviews=sum(c['purpose']=='review' for c in selected)
        want_review=reviews < chosen_strategy['target_review_ratio']*(index+1)
        pool=[c for c in candidates if c not in selected]
        preferred=[c for c in pool if (c['purpose']=='review')==want_review]
        if preferred: pool=preferred
        # Soft skill variety: preserve high-need review while admitting other skills.
        best=max(pool,key=lambda c:(c['priority']-2*sum(s['skill']==c['skill'] for s in selected),-c['difficulty'],c['topic_id']))
        selected.append(dict(best))
    selected.sort(key=lambda c:(c['purpose']!='review',c['difficulty'], -c['priority'],c['topic_id']))
    # Allocate actual minutes, not just counts, toward the desired review share.
    budget=min(minutes,count*12)
    durations=[min(3,budget//count)]*count
    for _ in range(budget-sum(durations)):
        review_minutes=sum(d for c,d in zip(selected,durations) if c['purpose']=='review')
        need_review=review_minutes/max(1,sum(durations)) < chosen_strategy['target_review_ratio']
        indices=[i for i in range(count) if durations[i]<12]
        preferred=[i for i in indices if (selected[i]['purpose']=='review')==need_review]
        indices=preferred or indices
        target=min(indices,key=lambda i:(durations[i],i))
        durations[target]+=1
    for index,(activity,duration) in enumerate(zip(selected,durations)):
        activity.update(order=index+1,duration_minutes=duration)
        activity.pop('priority'); activity.pop('prerequisites')
    actual=sum(a['duration_minutes'] for a in selected if a['purpose']=='review')/budget
    chosen_strategy.update(review_ratio=round(actual,3),new_ratio=round(1-actual,3))
    note='This introductory plan uses safe foundations; placement can improve personalization.' if profile['profile_source']=='default' else 'Built from your saved skill estimates and recent learning evidence.'
    if abs(actual-chosen_strategy['target_review_ratio'])>.2:
        note+=' The review/new balance is limited by eligible topics and prerequisites.'
    logger.info('Curriculum planned: strategy=%s activities=%d',chosen_strategy['name'],len(selected))
    return {'available_minutes':minutes,'estimated_minutes':budget,'strategy':chosen_strategy,'note':note,'activities':selected}
