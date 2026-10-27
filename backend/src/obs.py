"""Structured logging and CloudWatch custom metrics via the Embedded Metric Format.

Every line printed to stdout lands in the function's log group. EMF lines are turned
into metrics by CloudWatch itself, so no PutMetricData calls or extra permissions."""
import json
import os
import time

NAMESPACE = "CampusSlot"


def log(event, **fields):
    print(json.dumps({"event": event, **fields}, default=str, separators=(",", ":")))


def metric(name, value=1, unit="Count"):
    service = os.environ.get("SERVICE_NAME", "api")
    print(json.dumps({
        "_aws": {
            "Timestamp": int(time.time() * 1000),
            "CloudWatchMetrics": [{
                "Namespace": NAMESPACE,
                "Dimensions": [["Service"]],
                "Metrics": [{"Name": name, "Unit": unit}],
            }],
        },
        "Service": service,
        name: value,
    }, separators=(",", ":")))
