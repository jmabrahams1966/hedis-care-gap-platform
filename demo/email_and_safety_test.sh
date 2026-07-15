#!/usr/bin/env bash
###############################################################################
# Sets up BOTH optional-polish items on the live USFHP/SVMC tenant:
#   (2) Real email check-in test  — adds a member whose email is YOUR inbox.
#   (1) Safety-flag demo case      — you then complete that member's PHQ-9 with a
#                                     positive item 9, which lights up a safety
#                                     flag in the care-manager queue.
#
# Run:
#   ADMIN_EMAIL="admin@usfhp-svmc.demo" ADMIN_PASSWORD="USFHP-demo-40ccfd38" \
#     bash demo/email_and_safety_test.sh
#
# Then follow the printed 3 steps (start a check-in, open the email, answer the
# PHQ-9). One member covers both items.
###############################################################################
set -euo pipefail
API="${API:-https://api.cogai-payor.com}"
INBOX="${INBOX:-jma@nybrainspine.com}"     # where the real check-in email goes
: "${ADMIN_EMAIL:?set ADMIN_EMAIL (usfhp-svmc tenant admin)}"
: "${ADMIN_PASSWORD:?set ADMIN_PASSWORD}"

MEMBER_ID="USF-999"
MEMBER_DOB="1992-03-15"

echo "→ login as tenant admin"
TOKEN=$(curl -fsS -X POST "$API/api/auth/staff/login" -H 'Content-Type: application/json' \
  -d "{\"email\":\"$ADMIN_EMAIL\",\"password\":\"$ADMIN_PASSWORD\"}" \
  | python3 -c 'import sys,json;print(json.load(sys.stdin)["token"])')

echo "→ add test member $MEMBER_ID (email = $INBOX)"
TMPCSV=$(mktemp /tmp/usfhp_testmember.XXXX.csv)
cat > "$TMPCSV" <<CSV
external_member_id,external_dependent_id,guardian_external_member_id,first_name,last_name,date_of_birth,sex,conditions,phone,email,preferred_channel,preferred_language,consent_sms,consent_email
$MEMBER_ID,,,Alex,Rivera,$MEMBER_DOB,M,,+15550100999,$INBOX,email,en,false,true
CSV
curl -fsS -X POST "$API/api/members/bulk-csv" -H "Authorization: Bearer $TOKEN" \
  -F "file=@$TMPCSV;type=text/csv" \
  | python3 -c 'import sys,json;d=json.load(sys.stdin);print("   members added:",len(d.get("created_members") or d.get("members") or []),"errors:",len(d.get("errors",[])))'
rm -f "$TMPCSV"

cat <<EOF

============================================================
 Member ready. Now do these 3 steps to satisfy BOTH items:

 1. Go to  https://usfhp-svmc.cogai-payor.com  → "Start a check-in"
       Member ID:      $MEMBER_ID
       Date of birth:  $MEMBER_DOB
    → Click "Send me a link".   ✅ ITEM 2: a real check-in email
      should land in $INBOX within a minute. Confirm the link
      points to https://app.cogai-payor.com/verify?token=...

 2. Open that email, click the link (or paste the token on the
    verify page). You'll land on the PHQ-9 depression screen.

 3. Answer the 9 questions; for QUESTION 9 ("thoughts that you
    would be better off dead...") pick anything OTHER than
    "Not at all".  Submit.
       ✅ ITEM 1: the care-manager queue at
       https://usfhp-svmc.cogai-payor.com (log in as
       $ADMIN_EMAIL) will now show a red "Safety flag" case
       pinned to the top, with the 988 crisis card shown to the member.
============================================================
EOF
