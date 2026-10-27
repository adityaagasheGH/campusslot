"""Helper shared by the scripts: read an output of the campusslot stack."""
import os
import sys

import boto3

STACK = os.environ.get("STACK", "campusslot")

if tuple(int(p) for p in boto3.__version__.split(".")[:3]) < (1, 35, 60):
    sys.exit(f"boto3 {boto3.__version__} is too old for S3 conditional writes. Run:\n"
             "  python3 -m pip install --user --upgrade 'boto3>=1.35.60'")


def output(name):
    cfn = boto3.client("cloudformation", region_name=os.environ.get("AWS_REGION", "us-east-1"))
    outputs = cfn.describe_stacks(StackName=STACK)["Stacks"][0].get("Outputs", [])
    for o in outputs:
        if o["OutputKey"] == name:
            return o["OutputValue"]
    sys.exit(f"Stack {STACK} has no output {name}; run scripts/deploy.sh first")


if __name__ == "__main__":
    print(output(sys.argv[1]))
