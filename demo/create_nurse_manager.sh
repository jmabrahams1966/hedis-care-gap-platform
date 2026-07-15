#!/usr/bin/env bash
# Create a NURSE MANAGER (care_manager role) staff login for the USFHP/SVMC tenant.
# The tenant currently only has a payer_admin; this adds a care-manager account so
# the "Nurse Manager" role has a real login. Same one-off Fargate run-task pattern
# as the bootstrap. Run:  bash demo/create_nurse_manager.sh
set -euo pipefail
REGION=us-east-1
CLUSTER=hedis-care-gap-cluster
TASKDEF=hedis-care-gap:4
SUBNETS='["subnet-0de8ee128cc98d50a","subnet-0834bfda4a707fd1b"]'
SG='["sg-08fb0adc014162781"]'

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
"        ex=(await db.execute(select(StaffUser).where(StaffUser.email==EMAIL))).scalar_one_or_none()\n"
"        if ex: print('NURSE_MANAGER_EXISTS'); return\n"
"        db.add(StaffUser(tenant_id=t.id,email=EMAIL,password_hash=hash_password(PW),role=StaffRole.care_manager.value,name='USFHP Nurse Manager'))\n"
"        await db.commit(); print('NURSE_MANAGER_CREATED')\n"
"asyncio.run(main())\n"
)
print(json.dumps({"containerOverrides":[{"name":"backend","command":["python","-c",script]}]}))
PY
)

echo "→ creating nurse manager ($NM_EMAIL)"
TASK=$(aws ecs run-task --region "$REGION" --cluster "$CLUSTER" --task-definition "$TASKDEF" \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=$SUBNETS,securityGroups=$SG,assignPublicIp=DISABLED}" \
  --overrides "$OVERRIDES" --query "tasks[0].taskArn" --output text)
aws ecs wait tasks-stopped --region "$REGION" --cluster "$CLUSTER" --tasks "$TASK"
TID=$(basename "$TASK")
aws logs get-log-events --region "$REGION" --log-group-name /ecs/hedis-care-gap \
  --log-stream-name "backend/backend/$TID" --query "events[].message" --output text 2>/dev/null | sed 's/^/  /'

cat <<EOF

================  NURSE MANAGER LOGIN  ================
  URL:      https://usfhp-svmc.cogai-payor.com
  Email:    $NM_EMAIL
  Password: $NM_PW
======================================================
EOF
