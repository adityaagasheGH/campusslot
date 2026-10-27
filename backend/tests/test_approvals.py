import pytest

import notify
import storage
from conftest import TOMORROW, book


@pytest.fixture
def sent(monkeypatch):
    messages = []
    monkeypatch.setattr(notify, "publish", lambda subject, message: messages.append((subject, message)) or True)
    return messages


def test_hall_request_is_pending_and_emails_the_office(tokens, sent):
    status, b = book(tokens["alice"], facility="seminar-hall-a", slots=["1000"], people=80, purpose="Robotics club talk")
    assert status == 201 and b["status"] == "PENDING"
    assert len(sent) == 1
    subject, message = sent[0]
    assert "Seminar Hall A" in subject
    assert "Robotics club talk" in message and "alice@campus.test" in message and "80" in message


def test_sns_failure_does_not_fail_the_booking(tokens, monkeypatch):
    monkeypatch.setenv("TOPIC_ARN", "arn:aws:sns:us-east-1:123456789012:does-not-exist")
    status, b = book(tokens["alice"], facility="main-auditorium", slots=["1000"], people=200)
    assert status == 201 and b["status"] == "PENDING"


def test_admin_sees_and_approves_pending(tokens, api, sent):
    _, b = book(tokens["alice"], facility="seminar-hall-a", slots=["1000"], people=50)
    _, queue = api("GET", "/admin/approvals", tokens["admin"])
    assert [x["bookingId"] for x in queue["bookings"]] == [b["bookingId"]]
    status, approved = api("POST", f"/admin/bookings/{b['bookingId']}/approve", tokens["admin"])
    assert status == 200 and approved["status"] == "CONFIRMED"
    assert approved["history"][-1]["by"] == "office@campus.test"
    assert api("GET", "/admin/approvals", tokens["admin"])[1]["bookings"] == []


def test_reject_needs_reason_and_frees_slots(tokens, api, sent):
    _, b = book(tokens["alice"], facility="seminar-hall-a", slots=["1000", "1100"], people=50)
    assert api("POST", f"/admin/bookings/{b['bookingId']}/reject", tokens["admin"], {"reason": ""})[0] == 400
    status, r = api("POST", f"/admin/bookings/{b['bookingId']}/reject", tokens["admin"], {"reason": "Exam scheduled"})
    assert status == 200 and r["status"] == "REJECTED" and r["rejectReason"] == "Exam scheduled"
    assert storage.list_keys(f"locks/seminar-hall-a/{TOMORROW}/") == []
    assert book(tokens["bob"], facility="seminar-hall-a", slots=["1000"], people=10)[0] == 201


def test_only_pending_can_be_approved(tokens, api):
    _, b = book(tokens["alice"])
    assert api("POST", f"/admin/bookings/{b['bookingId']}/approve", tokens["admin"])[0] == 409


def test_pending_cannot_be_approved_after_start(tokens, api, clock, sent):
    _, b = book(tokens["alice"], facility="seminar-hall-a", slots=["1000"], people=50)
    clock.advance(days=1)  # 28 Oct 10:05
    assert api("POST", f"/admin/bookings/{b['bookingId']}/approve", tokens["admin"])[0] == 409
