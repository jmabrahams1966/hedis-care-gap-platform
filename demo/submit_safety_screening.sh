#!/usr/bin/env bash
###############################################################################
# WORKAROUND for the broken frontend submit step: submits a completed PHQ-9
# depression screening for member USF-999 DIRECTLY through the backend (a one-off
# Fargate task running the SAME logic as POST /api/screenings), producing a
# safety-flagged care-gap in the USFHP/SVMC care-manager queue.
#
# Uses PHQ-9 = [1,1,1,1,1,1,1,1,2]  (item 9 = 2 -> positive safety item; total 10
# = moderate) and GAD-7 = [1x7], mirroring what the member would have submitted.
#
# Run:  bash demo/submit_safety_screening.sh
###############################################################################
set -euo pipefail
REGION=us-east-1
CLUSTER=hedis-care-gap-cluster
TASKDEF=hedis-care-gap:4
CONTAINER=backend
SUBNETS='["subnet-0de8ee128cc98d50a","subnet-0834bfda4a707fd1b"]'
SG='["sg-08fb0adc014162781"]'
EXT_ID="${EXT_ID:-USF-999}"

OVERRIDES=$(python3 - "$EXT_ID" <<'PY'
import json, sys
ext = sys.argv[1]
script = (
"import asyncio\n"
"from datetime import datetime, timedelta\n"
"from sqlalchemy import select\n"
"from app.db import SessionLocal, init_db\n"
"from app.models import Member, CareGap, GapStatus, NumeratorSource, ScreeningSubmission\n"
"from app.measures import get_measure\n"
f"EXT={ext!r}\n"
"RESP={'phq9':[1,1,1,1,1,1,1,1,2],'gad7':[1,1,1,1,1,1,1]}\n"
"async def main():\n"
"    await init_db()\n"
"    async with SessionLocal() as db:\n"
"        m=(await db.execute(select(Member).where(Member.external_member_id==EXT))).scalars().first()\n"
"        if not m: print('MEMBER_NOT_FOUND'); return\n"
"        gap=(await db.execute(select(CareGap).where(CareGap.member_id==m.id, CareGap.measure_code=='mental_health', CareGap.status.in_([GapStatus.open.value, GapStatus.outreach_sent.value])))).scalars().first()\n"
"        if not gap: print('NO_OPEN_DEPRESSION_GAP'); return\n"
"        measure=get_measure('mental_health')\n"
"        ev=measure.evaluate_submission(RESP)\n"
"        db.add(ScreeningSubmission(care_gap_id=gap.id, member_id=m.id, measure_code='mental_health', instrument_scores=ev['instrument_scores'], safety_flag=ev['safety_flag']))\n"
"        if gap.numerator_source != NumeratorSource.claims_confirmed.value:\n"
"            gap.numerator_met=ev['numerator_met']\n"
"            gap.numerator_source=NumeratorSource.self_report.value if ev['numerator_met'] else NumeratorSource.unconfirmed.value\n"
"        gap.safety_flag=ev['safety_flag']\n"
"        wd=measure.follow_up_window_days(ev)\n"
"        if wd is not None:\n"
"            gap.status=GapStatus.needs_follow_up.value\n"
"            gap.follow_up_due_at=datetime.utcnow()+timedelta(days=wd)\n"
"        elif gap.numerator_met:\n"
"            gap.status=GapStatus.completed.value; gap.closed_at=datetime.utcnow()\n"
"        await db.commit()\n"
"        print('SCREENING_SUBMITTED safety_flag=%s status=%s' % (ev['safety_flag'], gap.status))\n"
"asyncio.run(main())\n"
)
print(json.dumps({"containerOverrides":[{"name":"backend","command":["python","-c",script]}]}))
PY
)

echo "→ launching one-off screening-submit task for $EXT_ID"
TASK_ARN=$(aws ecs run-task --region "$REGION" --cluster "$CLUSTER" \
  --task-definition "$TASKDEF" --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=$SUBNETS,securityGroups=$SG,assignPublicIp=DISABLED}" \
  --overrides "$OVERRIDES" --query "tasks[0].taskArn" --output text)
echo "   task: $TASK_ARN  (waiting...)"
aws ecs wait tasks-stopped --region "$REGION" --cluster "$CLUSTER" --tasks "$TASK_ARN"

TID=$(basename "$TASK_ARN")
echo "   result:"
aws logs get-log-events --region "$REGION" --log-group-name /ecs/hedis-care-gap \
  --log-stream-name "backend/$CONTAINER/$TID" --query "events[].message" --output text 2>/dev/null | sed 's/^/     /'
echo
echo "✓ If you see SCREENING_SUBMITTED safety_flag=True — refresh the care-manager"
echo "  queue at https://usfhp-svmc.cogai-payor.com (login admin@usfhp-svmc.demo)."
echo "  A red 'Safety flag' case for that member should be pinned to the top."
