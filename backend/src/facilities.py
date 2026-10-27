"""Facility catalogue: facilities/<id>.json."""
import re

import storage
import timeutil
from errors import bad_request, conflict, not_found

TYPES = ("lab", "seminar_hall", "study_room", "sports_court", "auditorium")
ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{2,39}$")
TIME_RE = re.compile(r"^([01]\d|2[0-4]):[0-5]\d$")


def key(facility_id):
    return f"facilities/{facility_id}.json"


def list_all(include_hidden=False):
    items = [obj for _, obj, _ in storage.get_many(storage.list_keys("facilities/"))]
    if not include_hidden:
        items = [f for f in items if not f.get("hidden")]
    return sorted(items, key=lambda f: (TYPES.index(f["type"]) if f["type"] in TYPES else 99, f["name"]))


def get(facility_id, include_hidden=False):
    if not isinstance(facility_id, str) or not ID_RE.match(facility_id):
        raise not_found("Facility not found")
    try:
        facility, etag = storage.get_json(key(facility_id))
    except storage.NotFound:
        raise not_found("Facility not found") from None
    if facility.get("hidden") and not include_hidden:
        raise not_found("Facility not found")
    return facility, etag


def slot_times(facility):
    """Start times ('HHMM') of every slot in a day."""
    start = timeutil.hhmm_to_minutes(facility["open"])
    end = timeutil.hhmm_to_minutes(facility["close"])
    step = int(facility["slotMinutes"])
    return [timeutil.minutes_to_hhmm(m) for m in range(start, end - step + 1, step)]


def slot_end(facility, hhmm):
    return timeutil.minutes_to_hhmm(timeutil.hhmm_to_minutes(hhmm) + int(facility["slotMinutes"]))


def open_hours(facility):
    return (timeutil.hhmm_to_minutes(facility["close"]) - timeutil.hhmm_to_minutes(facility["open"])) / 60


def validate(data, existing=None):
    """Return a clean facility record built from request data (merged onto existing)."""
    if not isinstance(data, dict):
        raise bad_request("Body must be a JSON object")
    merged = {**(existing or {}), **data}
    errors = {}

    fid = merged.get("id")
    if not isinstance(fid, str) or not ID_RE.match(fid):
        errors["id"] = "3-40 characters: lowercase letters, digits and dashes"
    name = merged.get("name")
    if not isinstance(name, str) or not 3 <= len(name.strip()) <= 60:
        errors["name"] = "3-60 characters"
    if merged.get("type") not in TYPES:
        errors["type"] = f"One of {', '.join(TYPES)}"
    cap = merged.get("capacity")
    if not isinstance(cap, int) or isinstance(cap, bool) or not 1 <= cap <= 1000:
        errors["capacity"] = "Whole number from 1 to 1000"
    slot = merged.get("slotMinutes")
    if slot not in (30, 60):
        errors["slotMinutes"] = "30 or 60"
    for field in ("open", "close"):
        if not isinstance(merged.get(field), str) or not TIME_RE.match(merged[field]):
            errors[field] = "Time as HH:MM"
    if "open" not in errors and "close" not in errors and "slotMinutes" not in errors:
        span = timeutil.hhmm_to_minutes(merged["close"]) - timeutil.hhmm_to_minutes(merged["open"])
        if span <= 0:
            errors["close"] = "Must be after opening time"
        elif span % slot or timeutil.hhmm_to_minutes(merged["open"]) % slot:
            errors["open"] = f"Opening hours must line up with {slot}-minute slots"
    for field in ("requiresApproval", "hidden"):
        if not isinstance(merged.get(field, False), bool):
            errors[field] = "true or false"
    for field, limit in (("location", 80), ("description", 200)):
        if not isinstance(merged.get(field, ""), str) or len(merged.get(field, "")) > limit:
            errors[field] = f"Text up to {limit} characters"
    if errors:
        raise bad_request("Some facility fields are invalid", fields=errors)

    return {
        "id": fid,
        "name": name.strip(),
        "type": merged["type"],
        "location": merged.get("location", "").strip(),
        "description": merged.get("description", "").strip(),
        "capacity": cap,
        "open": merged["open"],
        "close": merged["close"],
        "slotMinutes": slot,
        "requiresApproval": merged.get("requiresApproval", False),
        "hidden": merged.get("hidden", False),
    }


def create(data):
    facility = validate(data)
    try:
        storage.put_json(key(facility["id"]), facility, if_none_match=True)
    except storage.PreconditionFailed:
        raise conflict("A facility with this id already exists") from None
    return facility


def update(facility_id, data):
    existing, etag = get(facility_id, include_hidden=True)
    if "id" in data and data["id"] != facility_id:
        raise bad_request("The facility id cannot be changed")
    facility = validate(data, existing)
    try:
        storage.put_json(key(facility_id), facility, if_match=etag)
    except storage.PreconditionFailed:
        raise conflict("The facility changed while you were editing; reload and try again") from None
    return facility
