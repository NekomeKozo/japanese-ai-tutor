"""Local, explicitly scoped scheduler maintenance; stop server and back up first."""
import argparse
from pathlib import Path
from uuid import UUID
from app.assessment.repository import AssessmentRepository
from app.review.service import ReviewService,identity

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database',type=Path,required=True)
    parser.add_argument('--learner-id',type=UUID,required=True)
    parser.add_argument('--topic',required=True)
    parser.add_argument('--dimension')
    parser.add_argument('--action',choices=('rebuild','suspend','resume'),default='rebuild')
    args=parser.parse_args()
    if not args.database.is_file(): parser.error('Database must already exist')
    repo=AssessmentRepository(str(args.database))
    with repo.connection() as db:
        if db.execute('PRAGMA user_version').fetchone()[0] not in (5,6,7): parser.error('Run the current app to migrate first')
        if not db.execute('SELECT 1 FROM review_schedules WHERE learner_id=? AND topic_id=?',(str(args.learner_id),args.topic)).fetchone():
            parser.error('No schedules found for this learner/topic')
    repo.ready=True; service=ReviewService(repo)
    if args.action=='rebuild': service.reschedule_topic(args.learner_id,args.topic)
    else:
        if not args.dimension: parser.error('Suspension/resume requires a dimension')
        service.suspend_review(args.learner_id,identity(args.learner_id,args.topic,args.dimension),args.action=='suspend')
    print('Selected review target updated. Original learning evidence retained.')

if __name__=='__main__': main()
