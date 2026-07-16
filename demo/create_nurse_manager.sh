#!/usr/bin/env bash
###############################################################################
# Create (or reset) a NURSE MANAGER (care_manager role) login for the USFHP/SVMC
# tenant. Same one-off Fargate run-task pattern as the bootstrap.
#
#   bash demo/create_nurse_manager.sh
#
# IDEMPOTENT: creates the account if missing; if it already exists, RESETS its
# password and clears any login lockout. Either way the credentials printed at
# the end are the ones now in the database.
#
# Why the ceremony: the previous version printed its credentials banner
# unconditionally, so when the account already existed the task did nothing and
# the script still handed out a freshly-generated password that had never been
# written to the DB. It looked like success and failed at login. The banner is
# now gated on (1) a marker the container prints AFTER the DB commit, and
# (2) a real login against the live API. If either fails, nothing is printed.
###############################################################################
set -euo pipefail
REGION=us-east-1
CLUSTER=hedis-care-gap-cluster
TASKDEF=hedis-care-gap          # family -> latest ACTIVE revision (don't pin; revisions roll)
CONTAINER=backend
LOGGROUP=/ecs/hedis-care-gap
SUBNETS='["subnet-0de8ee128cc98d50a","subnet-0834bfda4a707fd1b"]'
SG='["sg-08fb0adc014162781"]'
API=https://api.cogai-payor.com

NM_EMAIL="nurse@usfhp-svmc.demo"
NM_PW="USFHP-nurse-$(openssl rand -hex 4)"

OVERRIDES=$(python3 - "$NM_EMAIL" "$NM_PW" <<'PY'
import json, sys
email, pw = sys.argv[1], sys.argv[2]
script = (
"import asyncio\n"
"from sqlalchemy import select\n"
"from app.db import SessionLocal, init_db\n"
"from app.models import Tenant, StaffUser, StaffRole\n"
"from app.security import hash_password\n"
f"EMAIL={email!r}\nPW={pw!r}\n"
"async def main():\n"
"    await init_db()\n"
"    async with SessionLocal() as db:\n"
"        t=(await db.execute(select(Tenant).where(Tenant.slug=='usfhp-svmc'))).scalar_one_or_none()\n"
"        if not t: print('NO_TENANT'); return\n"
"        u=(await db.execute(select(StaffUser).where(StaffUser.email==EMAIL))).scalar_one_or_none()\n"
"        if u:\n"
"            u.password_hash=hash_password(PW); u.failed_login_count=0; u.locked_until=None\n"
"            await db.commit(); print('NURSE_MANAGER_RESET')\n"
"        else:\n"
"            db.add(StaffUser(tenant_id=t.id,email=EMAIL,password_hash=hash_password(PW),role=StaffRole.care_manager.value,name='USFHP Nurse Manager'))\n"
"            await db.commit(); print('NURSE_MANAGER_CREATED')\n"
"asyncio.run(main())\n"
)
print(json.dumps({"containerOverrides":[{"name":"backend","command":["python","-c",script]}]}))
PY
)

echo "==> 1/3  Launching one-off task for $NM_EMAIL"
TASK=$(aws ecs run-task --region "$REGION" --cluster "$CLUSTER" --task-definition "$TASKDEF" \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=$SUBNETS,securityGroups=$SG,assignPublicIp=DISABLED}" \
  --overrides "$OVERRIDES" --query "tasks[0].taskArn" --output text)
echo "    task: $TASK"
aws ecs wait tasks-stopped --region "$REGION" --cluster "$CLUSTER" --tasks "$TASK"

echo "==> 2/3  Reading task output (the DB write is the source of truth, not the exit code)"
TID=$(basename "$TASK")
LOG=$(aws logs get-log-events --region "$REGION" --log-group-name "$LOGGROUP" \
  --log-stream-name "$CONTAINER/$CONTAINER/$TID" --query "events[].message" --output text 2>/dev/null || true)
echo "    ${LOG:-<no log output>}"

case "$LOG" in
  *NURSE_MANAGER_CREATED*) ACTION="account created" ;;
  *NURSE_MANAGER_RESET*)   ACTION="existing account — password reset, lockout cleared" ;;
  *NO_TENANT*)
    echo "ERROR: tenant 'usfhp-svmc' does not exist. Run demo/bootstrap_and_create_usfhp.sh first." >&2
    exit 1 ;;
  *)
    echo "ERROR: the task did not confirm a database write." >&2
    echo "       NOT printing credentials — they would not work. Check the task log above." >&2
    exit 1 ;;
esac

echo "==> 3/3  Verifying the credentials actually log in"
if ! curl -fsS -X POST "$API/api/auth/staff/login" -H 'Content-Type: application/json' \
      -d "{\"email\":\"$NM_EMAIL\",\"password\":\"$NM_PW\"}" >/dev/null 2>&1; then
  echo "ERROR: login check against $API FAILED — not printing credentials." >&2
  exit 1
fi
echo "    ok"

cat <<EOF

================  NURSE MANAGER LOGIN  ================
  URL:      https://usfhp-svmc.cogai-payor.com
  Email:    $NM_EMAIL
  Password: $NM_PW
  Status:   $ACTION
  Verified: login against $API succeeded
=======================================================
EOF
