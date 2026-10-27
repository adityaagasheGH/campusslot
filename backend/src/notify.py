"""Emails to the facility office through the SNS topic. Best-effort: a failure is logged
and counted but never fails the request that triggered it."""
import os

import boto3

import obs

_client = None


def _sns():
    global _client
    if _client is None:
        _client = boto3.client("sns")
    return _client


def reset():
    global _client
    _client = None


def publish(subject, message):
    topic = os.environ.get("TOPIC_ARN")
    if not topic:
        obs.log("notify_skipped", subject=subject)
        return False
    try:
        _sns().publish(TopicArn=topic, Subject=subject[:100], Message=message)
        return True
    except Exception as err:  # noqa: BLE001 - best effort by design
        obs.log("notify_failed", subject=subject, error=str(err))
        obs.metric("NotificationFailures")
        return False
