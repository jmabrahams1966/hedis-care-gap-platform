#!/usr/bin/env bash
# Populate the USFHP / St. Vincent's demo tenant with a roster (members + dependents).
# Uses the tenant's OWN admin login you created in the superadmin UI — never the superadmin password.
#
# Usage:
#   ADMIN_EMAIL="admin@usfhp-svmc.demo" ADMIN_PASSWORD="the-password-you-set" bash demo/populate_usfhp.sh
#
set -euo pipefail
API="${API:-https://api.cogai-payor.com}"
: "${ADMIN_EMAIL:?set ADMIN_EMAIL to the tenant admin you created}"
: "${ADMIN_PASSWORD:?set ADMIN_PASSWORD}"
CSV="$(cd "$(dirname "$0")" && pwd)/usfhp_roster.csv"
[ -f "$CSV" ] || { echo "roster not found: $CSV"; exit 1; }

echo "→ Logging in as $ADMIN_EMAIL"
TOKEN=$(curl -fsS -X POST "$API/api/auth/staff/login" \
  -H 'Content-Type: application/json' \
  -d "{\"email\":\"$ADMIN_EMAIL\",\"password\":\"$ADMIN_PASSWORD\"}" \
  | python3 -c 'import sys,json;print(json.load(sys.stdin)["token"])')
[ -n "${TOKEN:-}" ] || { echo "login failed"; exit 1; }

echo "→ Uploading roster ($CSV)"
curl -fsS -X POST "$API/api/members/bulk-csv" \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@$CSV;type=text/csv" \
  | python3 -m json.tool

echo "✓ Done — refresh the care-manager queue at https://usfhp-svmc.cogai-payor.com"
