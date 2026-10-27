"""Booking statuses, the transitions between them, slot locks, and the sweeper.

Every status change is written with If-Match on the ETag that was read, so two
actors (say a last-second check-in and the sweeper) can never overwrite each other."""
from datetime import timedelta

import notify
import obs
import storage
import timeutil

PENDING, CONFIRMED, CHECKED_IN = "PENDING", "CONFIRMED", "CHECKED_IN"
COMPLETED, CANCELLED, REJECTED, EXPIRED, NO_SHOW = "COMPLETED", "CANCELLED", "REJECTED", "EXPIRED", "NO_SHOW"

HOLDING = {PENDING, CONFIRMED, CHECKED_IN}        # statuses whose slots stay locked
FREES_SLOTS = {CANCELLED, REJECTED, EXPIRED, NO_SHOW}
ALLOWED = {
    PENDING: {CONFIRMED, REJECTED, EXPIRED, CANCELLED},
    CONFIRMED: {CHECKED_IN, NO_SHOW, CANCELLED},
    CHECKED_IN: {COMPLETED},
}
CHECK_IN_WINDOW = timedelta(minutes=15)
ORPHAN_LOCK_AGE = timedelta(minutes=5)


class StaleBooking(Exception):
    """The booking changed after it was read; the transition was not applied."""


class InvalidTransition(Exception):
    pass


# --- keys ---------------------------------------------------------------------

def booking_date(booking_id):
    d = booking_id[:8]
    return f"{d[:4]}-{d[4:6]}-{d[6:8]}"


def booking_key(booking_id):
    return f"bookings/{booking_date(booking_id)}/{booking_id}.json"


def lock_key(facility_id, day, hhmm):
    return f"locks/{facility_id}/{day}/{hhmm}"


def index_key(user_id, booking_id):
    return f"user-index/{user_id}/{booking_id}"


# --- times --------------------------------------------------------------------

def start_of(booking):
    return timeutil.at(timeutil.parse_date(booking["date"]), booking["startTime"])


def end_of(booking):
    return timeutil.at(timeutil.parse_date(booking["date"]), booking["endTime"])


def is_active(booking, now=None):
    now = now or timeutil.now()
    return booking["status"] in HOLDING and end_of(booking) > now


# --- locks --------------------------------------------------------------------

def release_locks(booking):
    """Delete the booking's slot locks, but only the ones it still owns."""
    for hhmm in booking["slots"]:
        k = lock_key(booking["facilityId"], booking["date"], hhmm)
        lock, _ = storage.try_get_json(k)
        if lock and lock.get("bookingId") == booking["bookingId"]:
            storage.delete(k)


# --- transitions ----------------------------------------------------------------

def transition(booking, etag, to, actor, note=None, **fields):
    """Apply one status change with If-Match. Returns (booking, new_etag)."""
    frm = booking["status"]
    if to not in ALLOWED.get(frm, set()):
        raise InvalidTransition(f"{frm} -> {to}")
    at = timeutil.iso_now()
    updated = {**booking, **fields, "status": to, "updatedAt": at}
    entry = {"at": at, "by": actor, "from": frm, "to": to}
    if note:
        entry["note"] = note
    updated["history"] = [*booking.get("history", []), entry]
    try:
        new_etag = storage.put_json(booking_key(booking["bookingId"]), updated, if_match=etag)
    except storage.PreconditionFailed:
        raise StaleBooking(booking["bookingId"]) from None
    if to in FREES_SLOTS:
        release_locks(updated)
    return updated, new_etag


def due_transition(booking, now):
    """What the sweeper should do with this booking right now, or None."""
    status = booking["status"]
    if status == CONFIRMED and now >= start_of(booking) + CHECK_IN_WINDOW:
        return NO_SHOW, "No check-in within 15 minutes of the start"
    if status == PENDING and now >= start_of(booking):
        return EXPIRED, "Not approved before the start time"
    if status == CHECKED_IN and now >= end_of(booking):
        return COMPLETED, None
    return None


def sweep(actor="system:sweeper"):
    """Idempotent: a second run right after the first changes nothing."""
    now = timeutil.now()
    summary = {"checked": 0, NO_SHOW: [], EXPIRED: [], COMPLETED: [], "orphanLocksDeleted": 0, "stale": 0}

    days = [(now.date() - timedelta(days=d)).isoformat() for d in (1, 0)]
    keys = [k for day in days for k in storage.list_keys(f"bookings/{day}/")]
    for _, booking, etag in storage.get_many(keys):
        summary["checked"] += 1
        due = due_transition(booking, now)
        if not due:
            continue
        to, note = due
        try:
            transition(booking, etag, to, actor, note)
        except StaleBooking:
            summary["stale"] += 1  # someone changed it just now; next run will look again
            continue
        summary[to].append(_describe(booking))

    summary["orphanLocksDeleted"] = _delete_orphan_locks(now)

    if summary[NO_SHOW]:
        obs.metric("NoShowsReleased", len(summary[NO_SHOW]))
    released = summary[NO_SHOW] + summary[EXPIRED]
    if released:
        lines = [f"{len(summary[NO_SHOW])} no-show(s) and {len(summary[EXPIRED])} expired request(s) were released:", ""]
        lines += [f"- {kind}: {d}" for kind in (NO_SHOW, EXPIRED) for d in summary[kind]]
        notify.publish("CampusSlot: slots released", "\n".join(lines))
    obs.log("sweep_done", actor=actor, checked=summary["checked"], noShows=len(summary[NO_SHOW]),
            expired=len(summary[EXPIRED]), completed=len(summary[COMPLETED]),
            orphanLocks=summary["orphanLocksDeleted"], stale=summary["stale"])
    return summary


def _describe(b):
    return f"{b['facilityName']} {b['date']} {b['startTime'][:2]}:{b['startTime'][2:]}-{b['endTime'][:2]}:{b['endTime'][2:]} ({b['userEmail']})"


def _delete_orphan_locks(now):
    """Locks left behind by a request that crashed half-way: older than 5 minutes and
    not held by a booking that is still holding its slots."""
    today = now.date().isoformat()
    cutoff = now - ORPHAN_LOCK_AGE
    candidates = []
    for obj in storage.list_objects("locks/"):
        parts = obj["Key"].split("/")
        if len(parts) == 4 and parts[2] >= today and obj["LastModified"] < cutoff:
            candidates.append(obj["Key"])
    deleted = 0
    bookings = {}
    for k, lock, _ in storage.get_many(candidates):
        bid = lock.get("bookingId", "")
        if bid not in bookings:
            bookings[bid] = storage.try_get_json(booking_key(bid))[0] if len(bid) > 9 else None
        b = bookings[bid]
        if not b or b["status"] not in HOLDING:
            storage.delete(k)
            deleted += 1
    return deleted
