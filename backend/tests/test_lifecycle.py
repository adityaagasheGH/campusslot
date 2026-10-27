from datetime import date, datetime, timedelta

import pytest

import lifecycle as lc
import notify
import storage
import timeutil
from conftest import TOMORROW, book

DAY = date(2026, 10, 28)


@pytest.fixture(autouse=True)
def quiet_sns(monkeypatch):
    sent = []
    monkeypatch.setattr(notify, "publish", lambda s, m: sent.append((s, m)) or True)
    return sent


def test_check_in_window_is_15_minutes_each_side(tokens, api, clock):
    _, b = book(tokens["alice"], slots=["1000"])
    path = f"/bookings/{b['bookingId']}/check-in"
    clock.set(DAY, "0944")
    assert api("POST", path, tokens["alice"])[0] == 409
    clock.set(DAY, "0945")
    status, c = api("POST", path, tokens["alice"])
    assert status == 200 and c["status"] == "CHECKED_IN" and c["checkedInAt"]


def test_check_in_closes_15_minutes_after_start(tokens, api, clock):
    _, b = book(tokens["alice"], slots=["1000"])
    clock.set(DAY, "1016")
    assert api("POST", f"/bookings/{b['bookingId']}/check-in", tokens["alice"])[0] == 409


def test_only_owner_can_check_in_or_cancel(tokens, api, clock):
    _, b = book(tokens["alice"], slots=["1000"])
    clock.set(DAY, "1000")
    assert api("POST", f"/bookings/{b['bookingId']}/check-in", tokens["bob"])[0] == 404
    assert api("POST", f"/bookings/{b['bookingId']}/cancel", tokens["bob"])[0] == 404
    assert api("GET", f"/bookings/{b['bookingId']}", tokens["bob"])[0] == 404
    assert api("GET", f"/bookings/{b['bookingId']}", tokens["admin"])[0] == 200


def test_cancel_before_start_frees_slots(tokens, api):
    _, b = book(tokens["alice"], slots=["1000", "1030"])
    status, c = api("POST", f"/bookings/{b['bookingId']}/cancel", tokens["alice"])
    assert status == 200 and c["status"] == "CANCELLED"
    assert storage.list_keys(f"locks/study-room-1/{TOMORROW}/") == []
    assert book(tokens["bob"], slots=["1000"])[0] == 201


def test_cannot_cancel_after_start(tokens, api, clock):
    _, b = book(tokens["alice"], slots=["1000"])
    clock.set(DAY, "1000")
    assert api("POST", f"/bookings/{b['bookingId']}/cancel", tokens["alice"])[0] == 409


def test_sweeper_marks_no_show_and_frees_slots(tokens, clock, quiet_sns):
    _, b = book(tokens["alice"], slots=["1000"])
    clock.set(DAY, "1014")
    assert lc.sweep()[lc.NO_SHOW] == []
    clock.set(DAY, "1015")
    summary = lc.sweep()
    assert len(summary[lc.NO_SHOW]) == 1
    booking, _ = storage.get_json(lc.booking_key(b["bookingId"]))
    assert booking["status"] == "NO_SHOW" and booking["history"][-1]["by"] == "system:sweeper"
    assert storage.list_keys(f"locks/study-room-1/{TOMORROW}/") == []
    assert len(quiet_sns) == 1 and "released" in quiet_sns[0][0]


def test_sweeper_expires_unapproved_requests(tokens, clock):
    _, b = book(tokens["alice"], facility="main-auditorium", slots=["1000"], people=100)
    clock.set(DAY, "1000")
    assert len(lc.sweep()[lc.EXPIRED]) == 1
    assert storage.get_json(lc.booking_key(b["bookingId"]))[0]["status"] == "EXPIRED"
    assert storage.list_keys("locks/main-auditorium/") == []


def test_sweeper_completes_checked_in_bookings(tokens, api, clock):
    _, b = book(tokens["alice"], slots=["1000", "1030"])
    clock.set(DAY, "1000")
    api("POST", f"/bookings/{b['bookingId']}/check-in", tokens["alice"])
    clock.set(DAY, "1059")
    assert lc.sweep()[lc.COMPLETED] == []
    clock.set(DAY, "1100")
    assert len(lc.sweep()[lc.COMPLETED]) == 1
    assert storage.get_json(lc.booking_key(b["bookingId"]))[0]["status"] == "COMPLETED"


def test_sweep_is_idempotent(tokens, clock, quiet_sns):
    book(tokens["alice"], slots=["1000"])
    clock.set(DAY, "1100")
    first, second = lc.sweep(), lc.sweep()
    assert len(first[lc.NO_SHOW]) == 1
    assert second[lc.NO_SHOW] == [] and second[lc.EXPIRED] == [] and second[lc.COMPLETED] == []
    assert len(quiet_sns) == 1


def test_sweeper_sees_yesterdays_bookings_after_midnight(tokens, api, clock):
    _, b = book(tokens["alice"], slots=["2130"])
    clock.set(DAY, "2130")
    api("POST", f"/bookings/{b['bookingId']}/check-in", tokens["alice"])
    clock.set(DAY + timedelta(days=1), "0010")
    assert len(lc.sweep()[lc.COMPLETED]) == 1


def test_last_second_check_in_is_not_overwritten_by_stale_sweeper(tokens, api, clock):
    _, b = book(tokens["alice"], slots=["1000"])
    clock.set(DAY, "1015")
    stale, stale_etag = storage.get_json(lc.booking_key(b["bookingId"]))   # sweeper reads...
    assert api("POST", f"/bookings/{b['bookingId']}/check-in", tokens["alice"])[0] == 200  # ...student checks in
    with pytest.raises(lc.StaleBooking):
        lc.transition(stale, stale_etag, lc.NO_SHOW, "system:sweeper")
    assert storage.get_json(lc.booking_key(b["bookingId"]))[0]["status"] == "CHECKED_IN"
    assert storage.list_keys(f"locks/study-room-1/{TOMORROW}/")  # slot still held


def test_sweeper_deletes_orphan_locks_older_than_5_minutes(tokens, clock):
    # S3 stamps LastModified with real time, so this test runs on the real clock.
    real_now = datetime.now(timeutil.IST)
    clock.value = real_now
    next_day = (real_now.date() + timedelta(days=1)).isoformat()
    _, live = book(tokens["alice"], date=next_day, slots=["1000"])
    storage.put_json(f"locks/study-room-1/{next_day}/2100", {"bookingId": "20261028-deadbeef0000"})
    clock.value = real_now + timedelta(minutes=1)
    assert lc.sweep()["orphanLocksDeleted"] == 0        # too young: its request may still be running
    clock.value = real_now + timedelta(minutes=6)
    assert lc.sweep()["orphanLocksDeleted"] == 1
    assert storage.list_keys(f"locks/study-room-1/{next_day}/") == [f"locks/study-room-1/{next_day}/1000"]
    assert live["status"] == "CONFIRMED"                 # the live booking keeps its lock


def test_every_change_is_recorded_in_history(tokens, api, clock):
    _, b = book(tokens["alice"], slots=["1000"])
    clock.set(DAY, "1000")
    _, c = api("POST", f"/bookings/{b['bookingId']}/check-in", tokens["alice"])
    assert [(h["from"], h["to"]) for h in c["history"]] == [(None, "CONFIRMED"), ("CONFIRMED", "CHECKED_IN")]
    assert all(h["at"] and h["by"] for h in c["history"])


def test_my_bookings_splits_upcoming_and_past(tokens, api, clock):
    book(tokens["alice"], slots=["1000"])
    _, b2 = book(tokens["alice"], slots=["1100"])
    api("POST", f"/bookings/{b2['bookingId']}/cancel", tokens["alice"])
    _, mine = api("GET", "/bookings/mine", tokens["alice"])
    assert [b["startTime"] for b in mine["upcoming"]] == ["1000"]
    assert [b["status"] for b in mine["past"]] == ["CANCELLED"]
