"""Load the facility catalogue (scripts/facilities.json) into the data bucket.

    python3 scripts/seed_facilities.py           # adds missing facilities, keeps edited ones
    python3 scripts/seed_facilities.py --force   # overwrites them with the file's version
"""
import json
import os
import sys
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from stack_outputs import output  # noqa: E402


def main():
    force = "--force" in sys.argv
    bucket = os.environ.get("DATA_BUCKET") or output("DataBucketName")
    s3 = boto3.client("s3", region_name=os.environ.get("AWS_REGION", "us-east-1"))
    facilities = json.loads((HERE / "facilities.json").read_text())
    for f in facilities:
        args = {"Bucket": bucket, "Key": f"facilities/{f['id']}.json",
                "Body": json.dumps(f).encode(), "ContentType": "application/json"}
        if not force:
            args["IfNoneMatch"] = "*"
        try:
            s3.put_object(**args)
            print(f"  added    {f['name']}")
        except ClientError as err:
            if err.response["Error"]["Code"] != "PreconditionFailed":
                raise
            print(f"  kept     {f['name']} (already there; use --force to overwrite)")
    print(f"{len(facilities)} facilities in s3://{bucket}/facilities/")


if __name__ == "__main__":
    main()
