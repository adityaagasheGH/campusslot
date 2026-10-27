#!/usr/bin/env bash
# Delete everything CampusSlot created: both buckets' contents, the stack (all 20
# resources) and the artifacts bucket. All bookings and accounts are lost.
set -euo pipefail
cd "$(dirname "$0")/.."
export AWS_DEFAULT_REGION="${AWS_REGION:-us-east-1}" AWS_PAGER=""
STACK=campusslot

ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
ARTIFACTS="campusslot-artifacts-${ACCOUNT}-${AWS_DEFAULT_REGION}"

read -rp "This permanently deletes CampusSlot and all its data in account $ACCOUNT. Type 'campusslot' to continue: " answer
[ "$answer" = "campusslot" ] || { echo "Cancelled."; exit 1; }

for name in WebBucketName DataBucketName; do
  b=$(aws cloudformation describe-stacks --stack-name "$STACK" \
      --query "Stacks[0].Outputs[?OutputKey=='$name'].OutputValue" --output text 2>/dev/null || true)
  if [ -n "$b" ] && [ "$b" != "None" ]; then
    echo "Emptying s3://$b"
    aws s3 rm "s3://$b" --recursive --only-show-errors
  fi
done

echo "Deleting stack $STACK (CloudFront takes a few minutes)"
aws cloudformation delete-stack --stack-name "$STACK"
aws cloudformation wait stack-delete-complete --stack-name "$STACK"

if aws s3api head-bucket --bucket "$ARTIFACTS" 2>/dev/null; then
  echo "Deleting s3://$ARTIFACTS"
  aws s3 rb "s3://$ARTIFACTS" --force >/dev/null
fi
echo "Done. The signing key in ~/.campusslot is kept; delete it if you will not redeploy."
