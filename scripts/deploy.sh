#!/usr/bin/env bash
# Deploy (or update) the whole CampusSlot stack. Run from AWS CloudShell in us-east-1:
#
#   bash scripts/deploy.sh
#
# Optional environment variables:
#   ALERT_EMAIL       facility office email (default kherakartik17@gmail.com)
#   LAMBDA_ROLE_ARN   role for both functions; found automatically (LabRole) if unset,
#                     set to "" on a normal account to create least-privilege roles.
set -euo pipefail
cd "$(dirname "$0")/.."

REGION="${AWS_REGION:-us-east-1}"
export AWS_DEFAULT_REGION="$REGION" AWS_PAGER=""
STACK="campusslot"
ALERT_EMAIL="${ALERT_EMAIL:-kherakartik17@gmail.com}"
KEY_FILE="$HOME/.campusslot/signing-key"

step() { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }

step "Checking the AWS session"
ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
echo "Account $ACCOUNT, region $REGION"
ARTIFACTS="campusslot-artifacts-${ACCOUNT}-${REGION}"

step "Checking boto3 (the seed and account scripts need S3 conditional writes)"
if ! python3 -c 'import boto3, sys; v = tuple(map(int, boto3.__version__.split(".")[:3])); sys.exit(v < (1, 35, 60))' 2>/dev/null; then
  python3 -m pip install --user --quiet --upgrade 'boto3>=1.35.60'
fi
python3 -c 'import boto3; print("boto3", boto3.__version__)'

step "Choosing the Lambda role"
if [ -z "${LAMBDA_ROLE_ARN+x}" ]; then
  if out=$(aws iam get-role --role-name LabRole --query Role.Arn --output text 2>&1); then
    LAMBDA_ROLE_ARN="$out"
  elif grep -q NoSuchEntity <<<"$out"; then
    LAMBDA_ROLE_ARN=""
  else
    LAMBDA_ROLE_ARN="arn:aws:iam::${ACCOUNT}:role/LabRole"   # lab accounts may hide iam:GetRole
  fi
fi
if [ -n "$LAMBDA_ROLE_ARN" ]; then echo "Using existing role $LAMBDA_ROLE_ARN"; else echo "Creating least-privilege roles"; fi

step "Signing key"
if [ ! -s "$KEY_FILE" ]; then
  mkdir -p "$(dirname "$KEY_FILE")"
  python3 -c 'import secrets; print(secrets.token_hex(32))' > "$KEY_FILE"
  chmod 600 "$KEY_FILE"
  echo "Generated a new 64-character key in $KEY_FILE"
else
  echo "Reusing $KEY_FILE"
fi
SIGNING_KEY=$(cat "$KEY_FILE")

step "Packaging the backend"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
python3 -m zipfile -c "$TMP/backend.zip" backend/src/*.py
HASH=$(sha256sum "$TMP/backend.zip" | cut -c1-12)
CODE_KEY="lambda/campusslot-backend-${HASH}.zip"
if ! aws s3api head-bucket --bucket "$ARTIFACTS" 2>/dev/null; then
  aws s3api create-bucket --bucket "$ARTIFACTS" >/dev/null
  aws s3api put-public-access-block --bucket "$ARTIFACTS" --public-access-block-configuration \
    BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
fi
aws s3 cp "$TMP/backend.zip" "s3://$ARTIFACTS/$CODE_KEY" --only-show-errors
echo "Uploaded $(du -k "$TMP/backend.zip" | cut -f1) KB as $CODE_KEY"

step "Deploying the CloudFormation stack (about 5-10 minutes the first time)"
STATUS=$(aws cloudformation describe-stacks --stack-name "$STACK" --query 'Stacks[0].StackStatus' --output text 2>/dev/null || echo NONE)
if [ "$STATUS" = "ROLLBACK_COMPLETE" ]; then
  echo "A previous first deploy failed; deleting the empty stack before retrying"
  aws cloudformation delete-stack --stack-name "$STACK"
  aws cloudformation wait stack-delete-complete --stack-name "$STACK"
fi
if ! aws cloudformation deploy \
  --stack-name "$STACK" \
  --template-file infrastructure/template.yaml \
  --capabilities CAPABILITY_IAM \
  --no-fail-on-empty-changeset \
  --parameter-overrides \
    CodeBucket="$ARTIFACTS" CodeKey="$CODE_KEY" AuthSigningKey="$SIGNING_KEY" \
    AlertEmail="$ALERT_EMAIL" LambdaRoleArn="$LAMBDA_ROLE_ARN"; then
  echo
  echo "Deploy failed. The first failing resources were:"
  aws cloudformation describe-stack-events --stack-name "$STACK" \
    --query "StackEvents[?contains(ResourceStatus,'FAILED')].[LogicalResourceId,ResourceStatusReason]" \
    --output text | tail -5
  exit 1
fi

output() {
  aws cloudformation describe-stacks --stack-name "$STACK" \
    --query "Stacks[0].Outputs[?OutputKey=='$1'].OutputValue" --output text
}
WEBSITE=$(output WebsiteUrl)
API_URL=$(output ApiUrl); API_URL="${API_URL%/}"
WEB_BUCKET=$(output WebBucketName)
DIST_ID=$(output DistributionId)

step "Building the website"
(cd frontend && npm ci --no-audit --no-fund --loglevel=error && npm run build)
printf '{ "apiUrl": "%s" }\n' "$API_URL" > frontend/dist/config.json

step "Uploading the website"
aws s3 sync frontend/dist/assets "s3://$WEB_BUCKET/assets" --delete --only-show-errors \
  --cache-control "public, max-age=31536000, immutable"
aws s3 cp frontend/dist/index.html "s3://$WEB_BUCKET/index.html" --only-show-errors \
  --cache-control "no-cache" --content-type "text/html; charset=utf-8"
aws s3 cp frontend/dist/config.json "s3://$WEB_BUCKET/config.json" --only-show-errors \
  --cache-control "no-cache" --content-type "application/json"
aws cloudfront create-invalidation --distribution-id "$DIST_ID" --paths /index.html /config.json / \
  --query Invalidation.Id --output text >/dev/null

step "Checking the API"
curl -fsS "$API_URL/health" && echo

cat <<EOF

CampusSlot is deployed.

  Website   $WEBSITE
  API       $API_URL

Next steps:
  1. Confirm the SNS subscription email sent to $ALERT_EMAIL (needed for alerts).
  2. python3 scripts/seed_facilities.py      # load the 7 facilities
  3. bash scripts/create_users.sh            # create the admin and student accounts
  4. bash scripts/smoke_test.sh              # 15 checks against the live stack

A new CloudFront distribution can take a few minutes before the website answers.
EOF
