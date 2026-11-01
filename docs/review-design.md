# Review scheduling

GoiGrow uses maintained `fsrs==6.3.2` behind the application-owned `ReviewScheduler`
interface. It supports explicit UTC review times, JSON persistence and deterministic
operation with fuzzing disabled. FSRS model parameters and the application's conservative
policy limits remain distinct from mastery scores/confidence.

`app/review` owns scheduling, ratings, queues, bootstrap and replay. Study owns the
saved activity lifecycle, submissions and recap. Mastery, scheduling and activity results
commit in the shared SQLite/PostgreSQL transaction. No extra model call schedules a card.
Provider failure leaves a review due; unsupported dimensions do not become invented tasks.

Reference: https://github.com/open-spaced-repetition/py-fsrs.

## Algorithm and application policy v1

`ReviewScheduler` is the only module importing FSRS. It exposes new-item and review
calculations with explicit evidence, a mastery-dimension snapshot and an aware timestamp.
The adapter persists FSRS Card JSON, including stability/difficulty. These parameters are
not mastery mastery or stability. FSRS default model weights remain unchanged. The
configured desired retention is **0.90**: a moderate starting target, not a guarantee
or an attempt to force near-perfect recall. Retention, thresholds and principal limits
are centralized in `app/review/policy.py` and injectable in tests.

FSRS receives UTC, an explicit review time and a stable card ID derived from the
learner/topic/dimension. Its random fuzzing is disabled. Application version 1 applies
these conservative constraints to its proposed interval:

- One 15-minute learning step and one 15-minute relearning step.
- Initial interval capped at 3 days before spreading.
- Subsequent daily-interval growth limited to 1.2× for Hard, 2.5× for Good, 3× for Easy.
  Recognition growth is capped at 1.6×. These are ceilings, not guaranteed increases.
- Confidence below .35 caps the interval at 7 days before spreading. A dimension with
  needs-review status caps it at one day.
- Three scored encounters on one UTC day require at least one day before returning.
  This is a due-date safeguard, not a limit on a learner choosing ordinary practice.
- Four lifetime lapses or four consecutive Again results flag persistent difficulty.
  Persistent Again results also require at least one day; nothing is auto-suspended.
- For intervals >=2 days, deterministic spreading multiplies the interval by
  `.95 + (stable_card_id % 1001)/10000`, within approximately ±5%. Thus soft 3/7-day caps
  can become 3.15/7.35 days. The final hard maximum is 365 days and minimum 15 minutes.
- The final interval updates Card.due, keeping the persisted card and indexed due time
  consistent. Model stability/difficulty are the FSRS outputs, not custom mastery values.

This is FSRS with application policy limits, not the unmodified FSRS schedule. These
limits need calibration, especially the conservative low-confidence cap inherited from
mastery's small question bank. Changing policy/model should increment application version
and use explicit replay rather than silently changing old dates.

## Rating map

| Evidence | Rating |
|---|---|
| Score < .45 | Again |
| .45 <= score < .70, significant hints, or revealed answer metadata | Hard |
| Score >= .70 without the Easy conditions | Good |
| Score >= .90 with all independence/challenge/mastery gates below | Easy |

Easy requires hint_used=false, quality>=.7, a production/recall/application task, a known
learner level with difficulty at least level-1, dimension confidence>=.35 and score>=.68.
Unknown hint/level metadata cannot produce Easy. No response-time penalty exists. Partial
credit remains in both learning-memory and review-attempt evidence even when mapped to a rating.
mastery filters revealed positive evidence before scheduling; the rating guard also
supports explicit revealed evidence if another trusted caller supplies it later.

## Explicit flashcard recall ratings

Due-review flashcards also accept Again, Hard, Good and Easy as explicit self-reported
recall. This path shares scheduling policy and retry/version protection, but records
its self-report provenance rather than fabricating a graded score or mastery evidence.
Free Practice does not reschedule the learner's due queue. Authored recall content uses
the same canonical topics and existing due-target selection limits.

## States and lapse behavior

Catalog items do not have schedules. A first eligible scored retrieval creates Learning
or Review state according to FSRS; there is no separate stored empty New card. Failed
Review-state retrieval enters Relearning and increments lapse_count. Further failures
remain learning/relearning; they do not repeatedly count the same lapse. Historical
mastery remains intact and receives only its normal bounded update.

Suspension is orthogonal to the FSRS state and preserves the card. It excludes the target
from due queues and scheduling updates while ordinary practice can still update mastery.
Resume restores eligibility at the preserved due date. Persistent difficulty is visible
to the planner: grammar gets a brief re-teaching instruction and a transfer exercise;
fixed vocabulary/kanji get an alternate learning-strategy prompt. Their hint credit is
reduced. A lifetime four-lapse flag is durable in v1; automated recovery of that flag is
a future calibration decision, not implicit auto-suspension.

## Dimension targets and content

The unique target is learner + canonical topic + dimension. On the graded-evidence path, normalized scored evidence with quality>=.5 creates
or updates a schedule. Explanation alone does not
create a card. Vocabulary recognition/meaning/reading/production and grammar recognition/
understanding/application/production are independent. Kanji meaning, recognition, on-
and kun-reading use distinct targets and retained word contexts. Untested production
stays unscheduled. Unsupported handwriting or unreviewed readings never enter the
executable queue; their schedule, if historical evidence exists, is preserved and counted
separately as unsupported, rather than fabricated into another task.

Vocabulary reading and word production, plus reviewed kanji readings, use local fixed
answers. Meaning paraphrases and generated grammar may use the existing semantic grader.
Recognition uses local choices. Two deterministic prompt variants and rotating choice
positions prevent identical wording on every encounter; grammar receives a bounded
variant index. This is modest variety, not a comprehensive content bank. Production
headings and plan labels use English cues so they do not reveal the Japanese answer.

Grammar generation reuses ContentService and its 4,000-byte context limit. Only selected
topic, dimension, difficulty, level, preferences and variant are sent. No dates, FSRS
state or full learning history are sent. Failed content generation/semantic grading
leaves the target due and records no scored event or review attempt.

## Queue, priority and study composition

An indexed query selects nonsuspended schedules with due_at<=now and joins compact
persisted mastery. It never reads the lifetime event/attempt history to build a queue.
All priorities are deterministic, with stable ID tie-breaking:

```
overdue = 4 * min(1, overdue_days/14)
foundation = max(0, 1-topic_difficulty/7)
priority = overdue + foundation + prerequisite_flag + goal_alignment_flag
           + (1-dimension_score)*confidence + min(2, .4*lapses)
           + persistent_difficulty_flag + needs_review_flag
```

Missing dimension score falls back to .5. Overdue influence saturates rather than
becoming infinite. The planner's existing goal/catalog/prerequisite definitions supply
relevance. A priority >=3 is exposed as High; numeric rank and FSRS values remain private.

The queue estimates 4 minutes for grammar application/production, 3 for other production,
2 for shorter recall/recognition. It selects at most 7 activities to fit the existing
curriculum plan contract, within the requested time and a 45-minute review ceiling. It
interleaves content kinds where possible and selects at most one dimension per topic in
one plan. Other due dimensions remain available in later plans. No global compulsory
daily quota exists. Large backlog begins at 20 executable due targets.

curriculum still creates and owns study sessions. Review-only plans allocate their time to
due targets; balanced plans use their existing review ratio, raised to .8 with a backlog,
then fill remaining time with eligible curriculum activities. Due reviews precede new
material. Requested focus is respected; when no supported due items match, original
planning remains available. An already-active plan is resumed unchanged.

Same-day relearning becomes available after the short interval in a **later plan**;
there is no automatic loop appending duplicate questions to a running plan. This preserves
the immutable plan/order/time-budget contract and adds spacing. A skipped activity stays
due and creates only the existing skip lifecycle event, not a failure/success rating.
Long absence changes due/overdue priority only; mastery is not automatically erased.

## Transactions and concurrency

learning-memory process_event → mastery normalized evidence/mastery → review scheduling all run
inside the caller's existing database transaction. In study completion, the stored answer
result is in the same transaction. Review-attempt identity is schedule_id + source_event_id;
existing event fingerprints and study submission IDs provide additional retry protection.
Retries return the same saved next-review date. Snapshot inputs/outputs support audit and
replay without storing private answer text in review tables.

A saved review activity carries a schedule version. Before content generation, after
generation and before graded commit, the service checks learner ownership, suspension
and version. If ordinary practice changed the target meanwhile, the learner skips the
stale activity and creates a fresh plan. It cannot silently double-update the old card.
Out-of-order event timestamps leave scheduling unchanged and emit a fixed diagnostic;
maintenance can replay explicitly. Database errors roll back all derived work.

## Migration and bootstrap

Schema v5 adds review_schedules and review_attempts, unique identities and due/attempt
indexes inside the existing migration transaction. Previous tables are unchanged.
Bootstrap visits measured mastery dimensions with supporting normalized evidence only.
It seeds one conservative FSRS state from the latest evidence; it does not invent a
sequence of past successful reviews. Review count starts at zero, original last-seen
time is retained, and bootstrap is marked internally. No fake attempt is added.

Strong dimensions (score>=.8, confidence>=.5) start no earlier than the fourth UTC day;
others start the next UTC day. Deterministic capacity allocation admits at most ten
new bootstrap targets per learner per UTC day, with 23-minute offsets from 09:00 UTC.
This bounds migration load without claiming that old mastery is forgotten. Repeated
initialization is idempotent. Existing due queues are not rewritten on subsequent startup.
This one-time global staggering uses UTC; the UI displays the corresponding local dates.

## Time, API and UI

Due time is an exact UTC timestamp, not an all-or-nothing midnight boundary. Clock is
injected in ReviewService; pure calculations receive explicit times. Naive timestamps
are rejected. Browser dates use the learner's local timezone. Forecast accepts an IANA
timezone, uses local midnight boundaries, and includes overdue items in Today. It never
makes a future-today item executable before its exact due time. `tzdata` supports Windows.

- GET `/api/learners/{id}/reviews/due?minutes=10&skill=grammar`
- GET `/api/learners/{id}/reviews/forecast?timezone=Asia/Manila`
- Existing POST `/api/curriculum/plan` with session_type=review starts the plan lifecycle.
- Existing study start/open/complete/skip/finish APIs perform review sessions. There is
  no parallel review-session system, manual rating endpoint or public mass-reset API.

Today's Study shows Daily Review counts, a manageable selected workload, local forecast
and Start review. Activities show progress and target dimension; feedback shows the next
date. Existing recap distinguishes successful, struggling and skipped activities.

## Maintenance and limits

Check the current schema guards first (some legacy CLIs reject schema 8). For a
supported isolated local database, stop the server, back up the data, then use `python -m app.review.maintenance` with
--database, --learner-id, --topic and action rebuild/suspend/resume. Suspension/resume
also requires --dimension. Rebuild replays original normalized evidence and the mastery
snapshot recorded with each attempt, preserving suspension and invalidating old plans.
It changes derived current state only; original events/mastery/attempts are retained.
Bootstrap-only cards with no attempts remain unchanged. No automatic optimizer runs.

FSRS weights and application thresholds have not been calibrated on this Japanese tutor.
mastery's intentionally low confidence and small content bank may cap intervals for a
long time. More varied reviewed content, hint instrumentation and retention evaluation
are needed before treating predictions as reliable. There are no notification/payment flows or voice/listening/handwriting SRS targets.
Audio progress and the application dashboard are separate from this scheduling policy.
