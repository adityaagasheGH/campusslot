import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import boto3
import pytest
from moto import mock_aws

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend" / "src"))

import accounts  # noqa: E402
import notify  # noqa: E402
import storage  # noqa: E402
import timeutil  # noqa: E402
import app  # noqa: E402

BUCKET = "campusslot-data-test"
FACILITIES = json.loads((ROOT / "scripts" / "facilities.json").read_text())


class Clock:
    """A settable clock: tests move time forward explicitly."""

    def __init__(self, start):
        self.value = start

    def __call__(self):
        return self.value

    def set(self, day, hhmm):
        self.value = timeutil.at(day, hhmm)

    def advance(self, **kw):
        self.value += timedelta(**kw)


@pytest.fixture
def clock():
    c = Clock(datetime(2026, 10, 27, 10, 5, tzinfo=timeutil.IST))
    timeutil.set_clock(c)
    yield c
    timeutil.set_clock(None)


@pytest.fixture
def aws(monkeypatch, clock):
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("DATA_BUCKET", BUCKET)
    monkeypatch.setenv("AUTH_SIGNING_KEY", "k" * 64)
    # Fewer hashing rounds keep the suite fast; the production count is tested separately.
    monkeypatch.setattr(accounts, "ITERATIONS", 1000)
    monkeypatch.setattr(accounts, "_DUMMY", {"salt": "00" * 16, "hash": "00" * 32, "iterations": 1000})
    with mock_aws():
        storage.reset()
        notify.reset()
        boto3.client("s3").create_bucket(Bucket=BUCKET)
        sns = boto3.client("sns")
        topic = sns.create_topic(Name="campusslot-admin-alerts")["TopicArn"]
        monkeypatch.setenv("TOPIC_ARN", topic)
        for f in FACILITIES:
            storage.put_json(f"facilities/{f['id']}.json", f)
        yield
        storage.reset()
        notify.reset()


def _user(email, role, name):
    user = accounts.make_user(email, name, role, "correct-horse-1", iterations=1000)
    accounts.save_new_user(user)
    return user


@pytest.fixture
def users(aws):
    return {
        "admin": _user("office@campus.test", "admin", "Facility Office"),
        "alice": _user("alice@campus.test", "student", "Alice"),
        "bob": _user("bob@campus.test", "student", "Bob"),
    }


@pytest.fixture
def tokens(users):
    return {k: accounts.issue_token(u) for k, u in users.items()}


def call(method, path, token=None, body=None, query=None):
    headers = {"content-type": "application/json"}
    if token:
        headers["authorization"] = f"Bearer {token}"
    event = {
        "rawPath": path,
        "queryStringParameters": query,
        "headers": headers,
        "body": json.dumps(body) if body is not None else None,
        "isBase64Encoded": False,
        "requestContext": {"requestId": "req-test", "http": {"method": method, "path": path}},
    }
    resp = app.handler(event, None)
    return resp["statusCode"], json.loads(resp["body"]) if resp["body"] else None


@pytest.fixture
def api():
    return call


TOMORROW = "2026-10-28"


def book(token, facility="study-room-1", date=TOMORROW, slots=("1000",), purpose="Group study", people=3):
    return call("POST", "/bookings", token, {
        "facilityId": facility, "date": date, "slots": list(slots), "purpose": purpose, "people": people,
    })
