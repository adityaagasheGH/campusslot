"""Availability, booking, cancel and check-in for students."""
import secrets
from datetime import timedelta

import facilities
import lifecycle as lc
import notify
import obs
import storage
import timeutil
from errors import bad_request, conflict, not_found

BOOKING_WINDOW_DAYS = 14
MAX_SLOTS = 4
MAX_ACTIVE = 3


def new_booking_id(day):
    return f"{day.strftime('%Y%m%d')}-{secrets.token_hex(6)}"


def load(booking_id):
    """Return (booking, etag) or raise 404."""
    if not isinstance(booking_id, str) or len(booking_id) != 21 or booking_id[8] != "-" or not booking_id[:8].isdigit():
        raise not_found("Booking not found")
    try:
        return storage.get_json(lc.booking_key(booking_id))
    except storage.NotFound:
        raise not_found("Booking not found") from None


def _bookings_of(user_id, id_prefix=""):
    ids = [k.rsplit("/", 1)[1] for k in storage.list_keys(f"user-index/{user_id}/{id_prefix}")]
    return [b for _, b, _ in storage.get_many(lc.booking_key(i) for i in ids)]


# --- availability ---------------------------------------------------------------

def availability(user, facility_id, date_text):
    facility, _ = facilities.get(facility_id)
    day = timeutil.parse_date(date_text)
    if not day:
        raise bad_request("date must be YYYY-MM-DD")
    now = timeutil.now()
    taken = {k.rsplit("/", 1)[1] for k in storage.list_keys(f"locks/{facility_id}/{day.isoformat()}/")}
    mine = set()
    for b in _bookings_of(user["sub"], day.strftime("%Y%m%d")):
        if b["facilityId"] == facility_id and b["status"] in lc.HOLDING:
            mine.update(b["slots"])
    slots = []
    for t in facilities.slot_times(facility):
        if timeutil.at(day, t) <= now:
            state = "past"
        elif t in mine:
            state = "yours"
        elif t in taken:
            state = "taken"
        else:
            state = "available"
        slots.append({"time": t, "end": facilities.slot_end(facility, t), "state": state})
    return {
        "facility": facility,
        "date": day.isoformat(),
        "bookable": 0 <= (day - now.date()).days <= BOOKING_WINDOW_DAYS,
        "slots": slots,
    }


# --- create -------------------------------------------------------------------

def _validate_request(body, facility):
    errors = {}
    now = timeutil.now()
    day = timeutil.parse_date(body.get("date"))
    if not day:
        errors["date"] = "Date as YYYY-MM-DD"
    elif not 0 <= (day - now.date()).days <= BOOKING_WINDOW_DAYS:
        errors["date"] = f"Bookings open for today and the next {BOOKING_WINDOW_DAYS} days"

    slots = body.get("slots")
    grid = facilities.slot_times(facility)
    if not isinstance(slots, list) or not slots or not all(isinstance(s, str) for s in slots):
        errors["slots"] = "Choose at least one slot"
    elif len(slots) > MAX_SLOTS:
        errors["slots"] = f"At most {MAX_SLOTS} consecutive slots"
    elif len(set(slots)) != len(slots) or not set(slots) <= set(grid):
        errors["slots"] = "Slots must be within opening hours and aligned to the slot grid"
    else:
        slots = sorted(slots, key=grid.index)
        idx = [grid.index(s) for s in slots]
        if idx != list(range(idx[0], idx[0] + len(idx))):
            errors["slots"] = "Slots must be consecutive"
        elif day and timeutil.at(day, slots[0]) <= now:
            errors["slots"] = "That slot has already started"

    purpose = body.get("purpose")
    if not isinstance(purpose, str) or not 3 <= len(purpose.strip()) <= 200:
        errors["purpose"] = "Purpose must be 3-200 characters"
    people = body.get("people")
    if not isinstance(people, int) or isinstance(people, bool) or not 1 <= people <= facility["capacity"]:
        errors["people"] = f"Number of people from 1 to {facility['capacity']}"

    if errors:
        raise bad_request("Please fix the highlighted fields", fields=errors)
    return day, slots, purpose.strip(), people


def create(user, body):
    if not isinstance(body, dict):
        raise bad_request("Body must be a JSON object")
    facility, _ = facilities.get(body.get("facilityId"))
    day, slots, purpose, people = _validate_request(body, facility)

    now = timeutil.now()
    active = [b for b in _bookings_of(user["sub"], "") if lc.is_active(b, now)]
    if len(active) >= MAX_ACTIVE:
        raise conflict(f"You already have {MAX_ACTIVE} active bookings; cancel one first", reason="LIMIT")

    booking_id = new_booking_id(day)
    claimed, taken = [], []
    lock_body = {"bookingId": booking_id, "userId": user["sub"], "createdAt": timeutil.iso_now()}
    for t in slots:
        k = lc.lock_key(facility["id"], day.isoformat(), t)
        try:
            storage.put_json(k, lock_body, if_none_match=True)
            claimed.append(k)
        except storage.PreconditionFailed:
            taken.append(t)
            break  # one clash is enough to refuse; report every clash below
    if taken:
        for k in claimed:
            storage.delete(k)
        existing = {k.rsplit("/", 1)[1] for k in storage.list_keys(f"locks/{facility['id']}/{day.isoformat()}/")}
        taken = sorted(set(taken) | (set(slots) & existing))
        obs.metric("BookingConflicts")
        raise conflict("Someone else booked that slot first", reason="SLOT_TAKEN", takenSlots=taken)

    status = lc.PENDING if facility.get("requiresApproval") else lc.CONFIRMED
    at = timeutil.iso_now()
    booking = {
        "bookingId": booking_id,
        "userId": user["sub"],
        "userEmail": user["email"],
        "userName": user.get("name", ""),
        "facilityId": facility["id"],
        "facilityName": facility["name"],
        "date": day.isoformat(),
        "slots": slots,
        "startTime": slots[0],
        "endTime": facilities.slot_end(facility, slots[-1]),
        "purpose": purpose,
        "people": people,
        "status": status,
        "createdAt": at,
        "updatedAt": at,
        "history": [{"at": at, "by": user["email"], "from": None, "to": status}],
    }
    try:
        storage.put_marker(lc.index_key(user["sub"], booking_id))
        storage.put_json(lc.booking_key(booking_id), booking, if_none_match=True)
    except Exception:
        for k in claimed:
            storage.delete(k)
        raise
    obs.metric("BookingsCreated")

    if status == lc.PENDING:
        notify.publish(
            f"CampusSlot: approval needed for {facility['name']}",
            "\n".join([
                "A booking request is waiting for approval.", "",
                f"Facility:  {facility['name']}",
                f"When:      {booking['date']} {_fmt(booking['startTime'])}-{_fmt(booking['endTime'])} IST",
                f"Requester: {user.get('name', '')} <{user['email']}>",
                f"Purpose:   {purpose}",
                f"People:    {people}", "",
                "Approve or reject it in CampusSlot under Manage > Approvals.",
                f"Booking ID: {booking_id}",
            ]),
        )
    return booking


def _fmt(hhmm):
    return f"{hhmm[:2]}:{hhmm[2:]}"


# --- my bookings ------------------------------------------------------------------

def mine(user):
    now = timeutil.now()
    items = _bookings_of(user["sub"])
    upcoming = sorted((b for b in items if lc.end_of(b) > now and b["status"] in lc.HOLDING),
                      key=lambda b: (b["date"], b["startTime"]))
    past = sorted((b for b in items if b not in upcoming),
                  key=lambda b: (b["date"], b["startTime"]), reverse=True)
    return {"upcoming": upcoming, "past": past}


def get_for(user, booking_id):
    booking, _ = load(booking_id)
    if booking["userId"] != user["sub"] and user["role"] != "admin":
        raise not_found("Booking not found")
    return booking


def cancel(user, booking_id):
    booking, etag = load(booking_id)
    if booking["userId"] != user["sub"]:
        raise not_found("Booking not found")
    if booking["status"] not in (lc.PENDING, lc.CONFIRMED):
        raise conflict(f"A {booking['status'].lower().replace('_', ' ')} booking cannot be cancelled")
    if timeutil.now() >= lc.start_of(booking):
        raise conflict("Bookings can only be cancelled before they start")
    return _apply(booking, etag, lc.CANCELLED, user["email"])


def check_in(user, booking_id):
    booking, etag = load(booking_id)
    if booking["userId"] != user["sub"]:
        raise not_found("Booking not found")
    if booking["status"] != lc.CONFIRMED:
        raise conflict("Only confirmed bookings can be checked in")
    now, start = timeutil.now(), lc.start_of(booking)
    if not start - lc.CHECK_IN_WINDOW <= now <= start + lc.CHECK_IN_WINDOW:
        raise conflict("Check-in is open from 15 minutes before to 15 minutes after the start")
    result = _apply(booking, etag, lc.CHECKED_IN, user["email"], checkedInAt=timeutil.iso_now())
    obs.metric("CheckIns")
    return result


def _apply(booking, etag, to, actor, note=None, **fields):
    try:
        return lc.transition(booking, etag, to, actor, note, **fields)[0]
    except lc.StaleBooking:
        raise conflict("This booking just changed; reload and try again") from None
    except lc.InvalidTransition:
        raise conflict("That change is not possible for this booking") from None


# --- admin --------------------------------------------------------------------

def approve(admin, booking_id):
    booking, etag = load(booking_id)
    if booking["status"] != lc.PENDING:
        raise conflict("Only pending requests can be approved")
    if timeutil.now() >= lc.start_of(booking):
        raise conflict("This request has already started and can no longer be approved")
    return _apply(booking, etag, lc.CONFIRMED, admin["email"], "Approved")


def reject(admin, booking_id, body):
    reason = (body or {}).get("reason") if isinstance(body, dict) else None
    if not isinstance(reason, str) or not 3 <= len(reason.strip()) <= 200:
        raise bad_request("A reason of 3-200 characters is required", fields={"reason": "3-200 characters"})
    booking, etag = load(booking_id)
    if booking["status"] != lc.PENDING:
        raise conflict("Only pending requests can be rejected")
    return _apply(booking, etag, lc.REJECTED, admin["email"], reason.strip(), rejectReason=reason.strip())


def _bookings_on(days):
    keys = [k for d in days for k in storage.list_keys(f"bookings/{d}/")]
    return [b for _, b, _ in storage.get_many(keys)]


def approvals():
    today = timeutil.today()
    days = [(today + timedelta(days=i)).isoformat() for i in range(BOOKING_WINDOW_DAYS + 1)]
    pending = [b for b in _bookings_on(days) if b["status"] == lc.PENDING]
    return sorted(pending, key=lambda b: (b["date"], b["startTime"]))


def search(params):
    day = timeutil.parse_date(params.get("date"))
    if not day:
        raise bad_request("date (YYYY-MM-DD) is required")
    items = _bookings_on([day.isoformat()])
    if params.get("facilityId"):
        items = [b for b in items if b["facilityId"] == params["facilityId"]]
    if params.get("status"):
        items = [b for b in items if b["status"] == params["status"].upper()]
    q = (params.get("q") or "").strip().lower()
    if q:
        items = [b for b in items if q in b["userEmail"].lower() or q in b.get("userName", "").lower()]
    return sorted(items, key=lambda b: (b["startTime"], b["facilityName"]))


def utilization(params):
    start, end = timeutil.parse_date(params.get("from")), timeutil.parse_date(params.get("to"))
    if not start or not end:
        raise bad_request("from and to (YYYY-MM-DD) are required")
    days = (end - start).days + 1
    if days < 1:
        raise bad_request("to must be on or after from")
    if days > 31:
        raise bad_request("The report covers at most 31 days")
    dates = [(start + timedelta(days=i)).isoformat() for i in range(days)]
    all_bookings = _bookings_on(dates)

    rows = []
    for f in facilities.list_all(include_hidden=True):
        mine_ = [b for b in all_bookings if b["facilityId"] == f["id"]]
        hours = lambda bs: sum(len(b["slots"]) * f["slotMinutes"] for b in bs) / 60  # noqa: E731
        booked = [b for b in mine_ if b["status"] in (lc.CONFIRMED, lc.CHECKED_IN, lc.COMPLETED, lc.NO_SHOW)]
        used = [b for b in mine_ if b["status"] in (lc.CHECKED_IN, lc.COMPLETED)]
        no_shows = [b for b in mine_ if b["status"] == lc.NO_SHOW]
        decided = len(used) + len(no_shows)
        offered = facilities.open_hours(f) * days
        rows.append({
            "facilityId": f["id"],
            "facilityName": f["name"],
            "type": f["type"],
            "offeredHours": round(offered, 1),
            "bookedHours": round(hours(booked), 1),
            "usedHours": round(hours(used), 1),
            "bookings": len(mine_),
            "noShows": len(no_shows),
            "noShowRate": round(len(no_shows) / decided, 3) if decided else None,
            "bookedPct": round(hours(booked) / offered, 3) if offered else 0,
            "usedPct": round(hours(used) / offered, 3) if offered else 0,
            "cancelled": sum(1 for b in mine_ if b["status"] == lc.CANCELLED),
            "rejectedOrExpired": sum(1 for b in mine_ if b["status"] in (lc.REJECTED, lc.EXPIRED)),
        })
    return {"from": start.isoformat(), "to": end.isoformat(), "days": days, "facilities": rows}
