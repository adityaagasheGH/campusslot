#!/usr/bin/env bash
# Create CampusSlot accounts interactively (passwords are typed hidden).
#
#   bash scripts/create_users.sh                          # asks for each account
#   bash scripts/create_users.sh EMAIL "Name" student     # one account
set -euo pipefail
cd "$(dirname "$0")/.."
export AWS_DEFAULT_REGION="${AWS_REGION:-us-east-1}"
export DATA_BUCKET="${DATA_BUCKET:-$(python3 scripts/stack_outputs.py DataBucketName)}"

if [ $# -eq 3 ]; then
  python3 scripts/create_user.py "$1" "$2" "$3"
  exit
fi

echo "Creating accounts in s3://$DATA_BUCKET (leave the email empty to finish)."
echo "Suggested for the demo: 1 admin (the facility office) and 2 students."
while true; do
  echo
  read -rp "Email: " email
  [ -z "$email" ] && break
  read -rp "Full name: " name
  read -rp "Role [student/admin] (student): " role
  role="${role:-student}"
  python3 scripts/create_user.py "$email" "$name" "$role" || true
done
