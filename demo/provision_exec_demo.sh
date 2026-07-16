#!/usr/bin/env bash
###############################################################################
# Provision one executive demo account on the USFHP/SVMC tenant.
#
#   bash demo/provision_exec_demo.sh <email> "<Full Name>"
#   e.g. bash demo/provision_exec_demo.sh jane.doe@example.org "Jane Doe"
#
# Each run gives that person BOTH sides of the product:
#   1. a payer_admin staff login  -> Quality Overview, queue, care workspace,
#      outreach sequences, KaveraChat AI assist
#   2. a member record on their own email -> they can request a check-in link
#      from the Member tab and experience the patient flow end-to-end
#
# Care gaps auto-open for the member because this calls the same _create_member
# the API uses — not a raw INSERT.
#
# Idempotent: resets the staff password (and clears lockout) if the account
# exists; reports the member if already present.
#
# Prints credentials ONLY after (a) the container confirms the DB write and
# (b) the staff login actually succeeds against the live API. See the header of
# create_nurse_manager.sh for why that ceremony exists.
#
# ⚠️ Run this only AFTER the magic-link fix is deployed and verified against a
#    real M365 inbox — otherwise their first click may 401. See
#    docs/RECONCILE_AND_HARDEN.md item 5.
###############################################################################
set -euo pipefail

if [ $# -lt 2 ]; then
  echo "usage: bash demo/provision_exec_demo.sh <email> \"<Full Name>\"" >&2
  exit 2
fi
EMAIL="$1"
FULLNAME="$2"

REGION=us-east-1
CLUSTER=hedis-care-gap-cluster
TASKDEF=hedis-care-gap
CONTAINER=backend
LOGGROUP=/ecs/hedis-care-gap
SUBNETS='["subnet-0de8ee128cc98d50a","subnet-0834bfda4a707fd1b"]'
SG='["sg-08fb0adc014162781"]'
API=https://api.cogai-payor.com
SITE=https://usfhp-svmc.cogai-payor.com

# Member ID they'll type on the Member tab. Short, unambiguous, no lookalikes.
SLUG=$(echo "$EMAIL" | cut -d@ -f1 | tr '[:lower:]' '[:upper:]' | tr -cd 'A-Z0-9' | cut -c1-8)
MEMBER_ID="DEMO-${SLUG}"
MEMBER_DOB="1970-01-01"
STAFF_PW="USFHP-demo-$(openssl rand -hex 4)"

OVERRIDES=$(python3 - "$EMAIL" "$FULLNAME" "$STAFF_PW" "$MEMBER_ID" "$MEMBER_DOB" <<'PY'
import json, sys
email, name, pw, mid, dob = sys.argv[1:6]
first = name.split()[0] if name.split() else "Demo"
last = name.split()[-1] if len(name.split()) > 1 else "User"
script = (
"import asyncio\n"
"from sqlalchemy import select\n"
"from app.db import SessionLocal, init_db\n"
"from app.models import Tenant, StaffUser, StaffRole, Member, MagicToken\n"
"from app.security import hash_password, generate_magic_token, magic_token_expiry\n"
"from app.routers.members import _create_member\n"
"from app.schemas import MemberCreate\n"
f"EMAIL={email!r}\nNAME={name!r}\nPW={pw!r}\nMID={mid!r}\nDOB={dob!r}\n"
f"FIRST={first!r}\nLAST={last!r}\n"
"async def main():\n"
"    await init_db()\n"
"    async with SessionLocal() as db:\n"
"        t=(await db.execute(select(Tenant).where(Tenant.slug=='usfhp-svmc'))).scalar_one_or_none()\n"
"        if not t: print('NO_TENANT'); return\n"
"        u=(await db.execute(select(StaffUser).where(StaffUser.email==EMAIL))).scalar_one_or_none()\n"
"        if u:\n"
"            u.password_hash=hash_password(PW); u.failed_login_count=0; u.locked_until=None\n"
"            u.role=StaffRole.payer_admin.value; u.tenant_id=t.id\n"
"            print('STAFF_RESET')\n"
"        else:\n"
"            db.add(StaffUser(tenant_id=t.id,email=EMAIL,password_hash=hash_password(PW),role=StaffRole.payer_admin.value,name=NAME))\n"
"            print('STAFF_CREATED')\n"
"        m=(await db.execute(select(Member).where(Member.external_member_id==MID))).scalar_one_or_none()\n"
"        if m:\n"
"            print('MEMBER_EXISTS alias=%s' % m.alias)\n"
"        else:\n"
"            m=await _create_member(db,t.id,MemberCreate(external_member_id=MID,first_name=FIRST,last_name=LAST,date_of_birth=DOB,sex='U',email=EMAIL,preferred_channel='email',consent_email=True))\n"
"            print('MEMBER_CREATED alias=%s' % m.alias)\n"
"        raw, th = generate_magic_token()\n"
"        db.add(MagicToken(member_id=m.id, token_hash=th, purpose='screening', expires_at=magic_token_expiry()))\n"
"        await db.commit()\n"
"        print('MAGIC_TOKEN %s' % raw)\n"
"asyncio.run(main())\n"
)
print(json.dumps({"containerOverrides":[{"name":"backend","command":["python","-c",script]}]}))
PY
)

echo "==> 1/3  Provisioning $FULLNAME <$EMAIL> on usfhp-svmc"
TASK=$(aws ecs run-task --region "$REGION" --cluster "$CLUSTER" --task-definition "$TASKDEF" \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=$SUBNETS,securityGroups=$SG,assignPublicIp=DISABLED}" \
  --overrides "$OVERRIDES" --query "tasks[0].taskArn" --output text)
aws ecs wait tasks-stopped --region "$REGION" --cluster "$CLUSTER" --tasks "$TASK"

echo "==> 2/3  Reading task output"
TID=$(basename "$TASK")
LOG=$(aws logs get-log-events --region "$REGION" --log-group-name "$LOGGROUP" \
  --log-stream-name "$CONTAINER/$CONTAINER/$TID" --query "events[].message" --output text 2>/dev/null || true)
echo "    ${LOG:-<no log output>}"

case "$LOG" in
  *NO_TENANT*) echo "ERROR: tenant 'usfhp-svmc' missing. Run bootstrap_and_create_usfhp.sh first." >&2; exit 1 ;;
  *STAFF_CREATED*|*STAFF_RESET*) : ;;
  *) echo "ERROR: no DB-write marker. NOT printing credentials." >&2; exit 1 ;;
esac

# Pre-minted link so the recipient doesn't have to type a member ID and wait for
# mail. NOTE: this is convenience, not immunity — if you paste it into an email,
# their scanner touches it exactly like any other link. What protects that click
# is the reuse grace in auth.py::verify_magic_link, not this.
RAW_TOKEN=$(printf '%s' "$LOG" | tr ' \t' '\n\n' | grep -A1 '^MAGIC_TOKEN$' | tail -1)
if [ -z "$RAW_TOKEN" ]; then
  echo "ERROR: no MAGIC_TOKEN in task output — not printing a link that won't work." >&2
  exit 1
fi
MAGIC_LINK="${SITE}/verify?token=${RAW_TOKEN}"

echo "==> 3/3  Verifying the staff login actually works"
if ! curl -fsS -X POST "$API/api/auth/staff/login" -H 'Content-Type: application/json' \
      -d "{\"email\":\"$EMAIL\",\"password\":\"$STAFF_PW\"}" >/dev/null 2>&1; then
  echo "ERROR: login check FAILED — not printing credentials." >&2
  exit 1
fi
echo "    ok"

cat <<EOF

===============  DEMO ACCESS — $FULLNAME  ===============
Site:  $SITE

STAFF (click "Admin" on the sign-in screen):
  Email:     $EMAIL
  Password:  $STAFF_PW
  Sees: Quality Overview, care-gap queue, case workspace, outreach
        sequences, and the AI assist (Summarize case / Draft reply).

PATIENT VIEW — one-click (paste this link into your email to them):
  $MAGIC_LINK

PATIENT VIEW — self-serve fallback (if the link above is spent):
  Site: $SITE  ->  "Member" -> "Use member ID"
  Member ID:      $MEMBER_ID
  Date of birth:  $MEMBER_DOB
  Sends a fresh check-in link to $EMAIL.

All data in this tenant is synthetic. Please don't enter real member
information — there's no BAA in place for this demo.
=========================================================

Notes for you (do not forward):
  * The link above is a live credential for that member — treat it like a
    password. It expires in ~7 days and is single-use, with a 60-minute grace
    so a mail scanner's touch doesn't lock them out.
  * If they report "Link is invalid or expired", the self-serve fallback above
    always mints a fresh one. Then check the audit trail:
      action=magic_verify_rejected, metadata.used_age_seconds
    Seconds => a scanner raced them (raise magic_reuse_grace_minutes).
    Hours   => delivery-time detonation (see RECONCILE_AND_HARDEN item 5).
EOF
