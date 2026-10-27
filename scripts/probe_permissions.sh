#!/usr/bin/env bash
# Find out what this AWS account (e.g. the AWS Academy lab) allows: create one tiny
# resource per service, delete it straight away, and report ALLOWED or DENIED.
set -uo pipefail
export AWS_DEFAULT_REGION="${AWS_REGION:-us-east-1}" AWS_PAGER=""
ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
TAG="campusslot-probe-$(date +%s)"
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT

probe() {  # probe NAME "create command" "cleanup command"
  local name="$1" create="$2" cleanup="$3"
  if out=$(eval "$create" 2>&1); then
    printf '  \033[32mALLOWED\033[0m  %s\n' "$name"
    eval "$cleanup" >/dev/null 2>&1 || printf '           (cleanup failed for %s: remove %s by hand)\n' "$name" "$TAG"
  else
    printf '  \033[31mDENIED \033[0m  %s  %s\n' "$name" "$(grep -oE '(AccessDenied|not authorized|UnauthorizedOperation|explicit deny)[^.]*' <<<"$out" | head -1)"
  fi
}

echo "Probing account $ACCOUNT in $AWS_DEFAULT_REGION"

probe "S3 bucket"                "aws s3api create-bucket --bucket $TAG" ":"
probe "S3 conditional write"     "aws s3api put-object --bucket $TAG --key k --if-none-match '*' --body /dev/null && ! aws s3api put-object --bucket $TAG --key k --if-none-match '*' --body /dev/null" \
                                 "aws s3 rb s3://$TAG --force"
probe "DynamoDB table"           "aws dynamodb create-table --table-name $TAG --attribute-definitions AttributeName=pk,AttributeType=S --key-schema AttributeName=pk,KeyType=HASH --billing-mode PAY_PER_REQUEST" \
                                 "aws dynamodb wait table-exists --table-name $TAG; aws dynamodb delete-table --table-name $TAG"
probe "API Gateway HTTP API"     "aws apigatewayv2 create-api --name $TAG --protocol-type HTTP --query ApiId --output text > $TMP/api" \
                                 "aws apigatewayv2 delete-api --api-id \$(cat $TMP/api)"
probe "Cognito user pool"        "aws cognito-idp create-user-pool --pool-name $TAG --query UserPool.Id --output text > $TMP/pool" \
                                 "aws cognito-idp delete-user-pool --user-pool-id \$(cat $TMP/pool)"
probe "IAM role"                 "aws iam create-role --role-name $TAG --assume-role-policy-document '{\"Version\":\"2012-10-17\",\"Statement\":[{\"Effect\":\"Allow\",\"Principal\":{\"Service\":\"lambda.amazonaws.com\"},\"Action\":\"sts:AssumeRole\"}]}'" \
                                 "aws iam delete-role --role-name $TAG"
printf 'def h(e, c):\n    return 1\n' > "$TMP/p.py"; (cd "$TMP" && python3 -m zipfile -c f.zip p.py)
probe "Lambda function (LabRole)" "aws lambda create-function --function-name $TAG --runtime python3.13 --handler p.h --zip-file fileb://$TMP/f.zip --role arn:aws:iam::$ACCOUNT:role/LabRole && aws lambda wait function-active-v2 --function-name $TAG" ":"
probe "Lambda function URL"      "aws lambda create-function-url-config --function-name $TAG --auth-type NONE" \
                                 "aws lambda delete-function --function-name $TAG"
probe "SNS topic"                "aws sns create-topic --name $TAG --query TopicArn --output text > $TMP/topic" \
                                 "aws sns delete-topic --topic-arn \$(cat $TMP/topic)"
probe "SQS queue"                "aws sqs create-queue --queue-name $TAG --query QueueUrl --output text > $TMP/q" \
                                 "aws sqs delete-queue --queue-url \$(cat $TMP/q)"
probe "SES account access"       "aws sesv2 get-account" ":"
probe "EventBridge rule"         "aws events put-rule --name $TAG --schedule-expression 'rate(1 day)' --state DISABLED" \
                                 "aws events delete-rule --name $TAG"
probe "EventBridge Scheduler"    "aws scheduler create-schedule-group --name $TAG" \
                                 "aws scheduler delete-schedule-group --name $TAG"
probe "CloudFront OAC"           "aws cloudfront create-origin-access-control --origin-access-control-config Name=$TAG,SigningProtocol=sigv4,SigningBehavior=always,OriginAccessControlOriginType=s3 --query '[OriginAccessControl.Id,ETag]' --output text > $TMP/oac" \
                                 "read id etag < $TMP/oac; aws cloudfront delete-origin-access-control --id \$id --if-match \$etag"
probe "CloudWatch dashboard"     "aws cloudwatch put-dashboard --dashboard-name $TAG --dashboard-body '{\"widgets\":[]}'" \
                                 "aws cloudwatch delete-dashboards --dashboard-names $TAG"
probe "CloudWatch log group"     "aws logs create-log-group --log-group-name /$TAG" \
                                 "aws logs delete-log-group --log-group-name /$TAG"
probe "Secrets Manager secret"   "aws secretsmanager create-secret --name $TAG --secret-string x" \
                                 "aws secretsmanager delete-secret --secret-id $TAG --force-delete-without-recovery"
probe "Step Functions"           "aws stepfunctions list-state-machines" ":"
probe "CloudFormation"           "aws cloudformation validate-template --template-body '{\"Resources\":{\"T\":{\"Type\":\"AWS::SNS::Topic\"}}}'" ":"
