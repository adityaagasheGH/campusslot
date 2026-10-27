from datetime import date

import lifecycle as lc
import notify
from conftest import TOMORROW, book

DAY = date(2026, 10, 28)


def test_search_by_date_facility_and_status(tokens, api, monkeypatch):
    monkeypatch.setattr(notify, "publish", lambda s, m: True)
    book(tokens["alice"], slots=["1000"])
    book(tokens["bob"], facility="badminton-court", slots=["1800"], people=2)
    book(tokens["bob"], facility="seminar-hall-a", slots=["1000"], people=20)
    _, all_ = api("GET", "/admin/bookings", tokens["admin"], query={"date": TOMORROW})
    assert len(all_["bookings"]) == 3
    _, court = api("GET", "/admin/bookings", tokens["admin"], query={"date": TOMORROW, "facilityId": "badminton-court"})
    assert [b["userEmail"] for b in court["bookings"]] == ["bob@campus.test"]
    _, pending = api("GET", "/admin/bookings", tokens["admin"], query={"date": TOMORROW, "status": "pending"})
    assert [b["facilityId"] for b in pending["bookings"]] == ["seminar-hall-a"]
    assert api("GET", "/admin/bookings", tokens["admin"])[0] == 400


def test_admin_adds_edits_and_hides_facility(tokens, api):
    new = {"id": "squash-court", "name": "Squash Court", "type": "sports_court", "capacity": 2,
           "open": "06:00", "close": "21:00", "slotMinutes": 30}
    assert api("POST", "/admin/facilities", tokens["admin"], new)[0] == 201
    assert api("POST", "/admin/facilities", tokens["admin"], new)[0] == 409
    status, f = api("PUT", "/admin/facilities/squash-court", tokens["admin"], {"capacity": 4, "hidden": True})
    assert status == 200 and f["capacity"] == 4 and f["hidden"] is True
    _, listed = api("GET", "/facilities", tokens["admin"], query={"includeHidden": "1"})
    assert "squash-court" in [x["id"] for x in listed["facilities"]]
    assert api("GET", "/facilities/squash-court", tokens["alice"])[0] == 404


def test_facility_validation(tokens, api):
    bad = {"id": "X", "name": "a", "type": "pool", "capacity": 0, "open": "9", "close": "08:00", "slotMinutes": 45}
    status, body = api("POST", "/admin/facilities", tokens["admin"], bad)
    assert status == 400
    assert set(body["error"]["fields"]) >= {"id", "name", "type", "capacity", "open", "slotMinutes"}
    misaligned = {"id": "room-x", "name": "Room X", "type": "lab", "capacity": 5,
                  "open": "09:30", "close": "12:00", "slotMinutes": 60}
    assert api("POST", "/admin/facilities", tokens["admin"], misaligned)[0] == 400


def test_utilization_counts_booked_used_and_no_shows(tokens, api, clock, monkeypatch):
    monkeypatch.setattr(notify, "publish", lambda s, m: True)
    _, used = book(tokens["alice"], slots=["1000", "1030"])    # 1 h, will check in
    book(tokens["bob"], slots=["1200"])                       # 0.5 h, no-show
    _, cancelled = book(tokens["bob"], slots=["1500"])
    api("POST", f"/bookings/{cancelled['bookingId']}/cancel", tokens["bob"])
    clock.set(DAY, "1000")
    api("POST", f"/bookings/{used['bookingId']}/check-in", tokens["alice"])
    clock.set(DAY, "1300")
    lc.sweep()
    status, rep = api("GET", "/admin/reports/utilization", tokens["admin"], query={"from": TOMORROW, "to": TOMORROW})
    assert status == 200
    row = next(r for r in rep["facilities"] if r["facilityId"] == "study-room-1")
    assert row["offeredHours"] == 15.0
    assert row["bookedHours"] == 1.5
    assert row["usedHours"] == 1.0
    assert row["noShows"] == 1 and row["noShowRate"] == 0.5
    assert row["cancelled"] == 1


def test_utilization_range_is_at_most_31_days(tokens, api):
    q = {"from": "2026-10-01", "to": "2026-11-01"}
    assert api("GET", "/admin/reports/utilization", tokens["admin"], query=q)[0] == 400
    q = {"from": "2026-10-01", "to": "2026-10-31"}
    status, rep = api("GET", "/admin/reports/utilization", tokens["admin"], query=q)
    assert status == 200 and rep["days"] == 31 and len(rep["facilities"]) == 7


def test_admin_can_run_sweep_on_demand(tokens, api, clock, monkeypatch):
    monkeypatch.setattr(notify, "publish", lambda s, m: True)
    book(tokens["alice"], slots=["1000"])
    clock.set(DAY, "1030")
    status, summary = api("POST", "/admin/sweep", tokens["admin"])
    assert status == 200 and len(summary["NO_SHOW"]) == 1
