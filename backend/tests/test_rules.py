from conftest import TOMORROW, book


def test_normal_booking_is_confirmed(tokens):
    status, b = book(tokens["alice"], slots=["1000", "1030"])
    assert status == 201
    assert b["status"] == "CONFIRMED"
    assert (b["startTime"], b["endTime"]) == ("1000", "1100")
    assert b["bookingId"].startswith("20261028-")


def test_date_must_be_within_14_days(tokens):
    assert book(tokens["alice"], date="2026-11-10")[0] == 201  # today + 14
    status, b = book(tokens["alice"], date="2026-11-11")
    assert status == 400 and "date" in b["error"]["fields"]
    assert book(tokens["alice"], date="2026-10-26")[0] == 400


def test_slots_must_be_on_grid_and_inside_hours(tokens):
    assert book(tokens["alice"], slots=["1015"])[0] == 400          # 30-minute grid
    assert book(tokens["alice"], slots=["0630"])[0] == 400          # opens 07:00
    assert book(tokens["alice"], slots=["2200"])[0] == 400          # closes 22:00
    assert book(tokens["alice"], facility="computer-lab-1", slots=["0930"])[0] == 400  # 60-min grid


def test_slots_must_be_consecutive_and_at_most_four(tokens):
    status, b = book(tokens["alice"], slots=["1000", "1100"])
    assert status == 400 and "consecutive" in b["error"]["fields"]["slots"]
    status, b = book(tokens["alice"], slots=["1000", "1030", "1100", "1130", "1200"])
    assert status == 400 and "4" in b["error"]["fields"]["slots"]
    assert book(tokens["alice"], slots=["1130", "1000", "1100", "1030"])[0] == 201  # order does not matter


def test_slot_must_not_have_started(tokens):
    status, b = book(tokens["alice"], date="2026-10-27", slots=["1000"])  # now is 10:05
    assert status == 400 and "started" in b["error"]["fields"]["slots"]
    assert book(tokens["alice"], date="2026-10-27", slots=["1030"])[0] == 201


def test_purpose_and_people_limits(tokens):
    assert book(tokens["alice"], purpose="ab")[0] == 400
    assert book(tokens["alice"], purpose="x" * 201)[0] == 400
    assert book(tokens["alice"], people=7)[0] == 400   # capacity 6
    assert book(tokens["alice"], people=0)[0] == 400
    assert book(tokens["alice"], people=6)[0] == 201


def test_at_most_three_active_bookings(tokens):
    for t in ("0800", "0900", "1000"):
        assert book(tokens["alice"], slots=[t])[0] == 201
    status, b = book(tokens["alice"], slots=["1100"])
    assert status == 409 and b["error"]["reason"] == "LIMIT"
    assert book(tokens["bob"], slots=["1100"])[0] == 201  # the limit is per student


def test_hidden_facility_cannot_be_booked(tokens, api):
    assert api("PUT", "/admin/facilities/study-room-2", tokens["admin"], {"hidden": True})[0] == 200
    assert book(tokens["alice"], facility="study-room-2")[0] == 404
    _, body = api("GET", "/facilities", tokens["alice"])
    assert "study-room-2" not in [f["id"] for f in body["facilities"]]
    assert len(body["facilities"]) == 6


def test_availability_marks_available_taken_yours_past(tokens, api):
    book(tokens["alice"], date="2026-10-27", slots=["1100"])
    book(tokens["bob"], date="2026-10-27", slots=["1200"])
    status, body = api("GET", "/facilities/study-room-1/availability", tokens["alice"], query={"date": "2026-10-27"})
    assert status == 200
    states = {s["time"]: s["state"] for s in body["slots"]}
    assert states["0930"] == "past"
    assert states["1000"] == "past"      # started at 10:00, now 10:05
    assert states["1030"] == "available"
    assert states["1100"] == "yours"
    assert states["1200"] == "taken"
    assert len(body["slots"]) == 30      # 07:00-22:00 in 30-minute slots


def test_availability_needs_valid_date_and_facility(tokens, api):
    assert api("GET", "/facilities/study-room-1/availability", tokens["alice"], query={"date": "bad"})[0] == 400
    assert api("GET", "/facilities/no-such-room/availability", tokens["alice"], query={"date": TOMORROW})[0] == 404
