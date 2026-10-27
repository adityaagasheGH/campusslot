#!/usr/bin/env bash
# 15 automated checks against the live stack.
#
#   bash scripts/smoke_test.sh
#   SMOKE_EMAIL=student@example.com bash scripts/smoke_test.sh   # also runs the signed-in checks
#
# With SMOKE_EMAIL set (a *student* account) the password is asked for, hidden.
set -uo pipefail
cd "$(dirname "$0")/.."
export AWS_DEFAULT_REGION="${AWS_REGION:-us-east-1}" AWS_PAGER=""

out() { aws cloudformation describe-stacks --stack-name campusslot --query "Stacks[0].Outputs[?OutputKey=='$1'].OutputValue" --output text; }
SITE=$(out WebsiteUrl); API=$(out ApiUrl); API="${API%/}"; WEB_BUCKET=$(out WebBucketName)
HOST="${SITE#https://}"
PASS=0; FAIL=0; SKIP=0; N=0

check() {  # check "description" command...
  N=$((N + 1)); local name="$1"; shift
  if "$@" >/dev/null 2>&1; then PASS=$((PASS + 1)); printf ' \033[32mPASS\033[0m %2d  %s\n' "$N" "$name"
  else FAIL=$((FAIL + 1)); printf ' \033[31mFAIL\033[0m %2d  %s\n' "$N" "$name"; fi
}
skip() { N=$((N + 1)); SKIP=$((SKIP + 1)); printf ' \033[33mSKIP\033[0m %2d  %s\n' "$N" "$1"; }
status() { curl -s -o /dev/null -w '%{http_code}' "$@"; }
is() { [ "$1" = "$2" ]; }

echo "Website $SITE"
echo "API     $API"
echo

check "Website loads over HTTPS"                 bash -c "curl -fsS '$SITE/' | grep -q 'id=\"root\"'"
check "Plain HTTP redirects to HTTPS"            is "$(status "http://$HOST/")" 301
check "Security headers (HSTS) are sent"         bash -c "curl -sSI '$SITE/' | grep -qi '^strict-transport-security'"
check "config.json points at this API"           bash -c "curl -fsS '$SITE/config.json' | grep -q '$API'"
check "Deep links load the app (SPA fallback)"   bash -c "curl -fsS '$SITE/my-bookings' | grep -q 'id=\"root\"'"
check "Website bucket is not public"             is "$(status "https://$WEB_BUCKET.s3.amazonaws.com/index.html")" 403
check "API health answers 200"                   is "$(status "$API/health")" 200
check "Request without a token gets 401"         is "$(status "$API/facilities")" 401
check "Forged token gets 401"                    is "$(status -H 'authorization: Bearer abc.def.ghi' "$API/facilities")" 401
check "Wrong password gets 401"                  is "$(status -X POST -H 'content-type: application/json' \
                                                   -d '{"email":"nobody@example.com","password":"wrong-password"}' "$API/auth/sign-in")" 401
check "CORS allows the website origin"           bash -c "curl -sS -X OPTIONS -D - -o /dev/null -H 'origin: $SITE' \
                                                   -H 'access-control-request-method: POST' '$API/bookings' | grep -qi '^access-control-allow-origin: $SITE'"
check "CORS refuses other origins"               bash -c "! curl -sS -X OPTIONS -D - -o /dev/null -H 'origin: https://evil.example' \
                                                   -H 'access-control-request-method: POST' '$API/bookings' | grep -qi 'access-control-allow-origin: https://evil'"
check "Errors carry a request ID"                bash -c "curl -sS '$API/facilities' | grep -q requestId"

if [ -n "${SMOKE_EMAIL:-}" ]; then
  read -rsp "Password for $SMOKE_EMAIL: " SMOKE_PASSWORD; echo
  BODY=$(python3 -c 'import json,sys; print(json.dumps({"email": sys.argv[1], "password": sys.argv[2]}))' "$SMOKE_EMAIL" "$SMOKE_PASSWORD")
  TOKEN=$(curl -sS -X POST -H 'content-type: application/json' -d "$BODY" "$API/auth/sign-in" \
          | python3 -c 'import json,sys; print(json.load(sys.stdin).get("token",""))' 2>/dev/null)
  check "Sign-in works and facilities are listed" bash -c "[ -n '$TOKEN' ] && curl -fsS -H 'authorization: Bearer $TOKEN' '$API/facilities' | grep -q '\"slotMinutes\"'"
  check "A student cannot open admin routes"      is "$(status -H "authorization: Bearer $TOKEN" "$API/admin/approvals")" 403
else
  skip "Sign-in works and facilities are listed (set SMOKE_EMAIL)"
  skip "A student cannot open admin routes (set SMOKE_EMAIL)"
fi

echo
echo "$PASS passed, $FAIL failed, $SKIP skipped"
[ "$FAIL" -eq 0 ]
