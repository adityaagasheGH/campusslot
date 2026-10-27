"""campusslot-api: the Lambda function behind the function URL.

The function URL sends every path and method here; this module matches the path to one
of 19 routes, checks the token, runs the route and writes one JSON log line."""
import base64
import json
import re
import time
import uuid

import accounts
import bookings
import facilities
import lifecycle
import obs
from errors import ApiError, bad_request, forbidden

ROUTES = []


def route(method, pattern, auth="user"):
    """auth: 'none', 'user' (any signed-in account) or 'admin'."""
    def register(fn):
        ROUTES.append((method, re.compile(f"^{pattern}$"), auth, fn, pattern))
        return fn
    return register


# --- public -------------------------------------------------------------------

@route("GET", "/health", auth="none")
def health(req):
    import boto3
    return 200, {"status": "ok", "service": "campusslot-api", "boto3": boto3.__version__}


@route("POST", "/auth/sign-in", auth="none")
def sign_in(req):
    body = req["json"] or {}
    try:
        return 200, accounts.sign_in(body.get("email"), body.get("password"))
    except ApiError as err:
        if err.status == 401:
            obs.metric("SignInFailures")
        raise


# --- signed-in users ------------------------------------------------------------

@route("GET", "/me")
def me(req):
    u = req["user"]
    return 200, {"userId": u["sub"], "email": u["email"], "name": u["name"], "role": u["role"]}


@route("GET", "/facilities")
def list_facilities(req):
    include_hidden = req["user"]["role"] == "admin" and req["query"].get("includeHidden") == "1"
    return 200, {"facilities": facilities.list_all(include_hidden)}


@route("GET", "/facilities/(?P<fid>[^/]+)")
def get_facility(req, fid):
    return 200, facilities.get(fid, include_hidden=req["user"]["role"] == "admin")[0]


@route("GET", "/facilities/(?P<fid>[^/]+)/availability")
def availability(req, fid):
    return 200, bookings.availability(req["user"], fid, req["query"].get("date"))


@route("POST", "/bookings")
def create_booking(req):
    return 201, bookings.create(req["user"], req["json"])


@route("GET", "/bookings/mine")
def my_bookings(req):
    return 200, bookings.mine(req["user"])


@route("GET", "/bookings/(?P<bid>[^/]+)")
def get_booking(req, bid):
    return 200, bookings.get_for(req["user"], bid)


@route("POST", "/bookings/(?P<bid>[^/]+)/cancel")
def cancel_booking(req, bid):
    return 200, bookings.cancel(req["user"], bid)


@route("POST", "/bookings/(?P<bid>[^/]+)/check-in")
def check_in(req, bid):
    return 200, bookings.check_in(req["user"], bid)


# --- admin --------------------------------------------------------------------

@route("GET", "/admin/approvals", auth="admin")
def approvals(req):
    return 200, {"bookings": bookings.approvals()}


@route("POST", "/admin/bookings/(?P<bid>[^/]+)/approve", auth="admin")
def approve(req, bid):
    return 200, bookings.approve(req["user"], bid)


@route("POST", "/admin/bookings/(?P<bid>[^/]+)/reject", auth="admin")
def reject(req, bid):
    return 200, bookings.reject(req["user"], bid, req["json"])


@route("GET", "/admin/bookings", auth="admin")
def search(req):
    return 200, {"bookings": bookings.search(req["query"])}


@route("POST", "/admin/facilities", auth="admin")
def create_facility(req):
    return 201, facilities.create(req["json"])


@route("PUT", "/admin/facilities/(?P<fid>[^/]+)", auth="admin")
def update_facility(req, fid):
    return 200, facilities.update(fid, req["json"] if isinstance(req["json"], dict) else {})


@route("GET", "/admin/reports/utilization", auth="admin")
def utilization(req):
    return 200, bookings.utilization(req["query"])


@route("POST", "/admin/sweep", auth="admin")
def run_sweep(req):
    return 200, lifecycle.sweep(actor=f"admin:{req['user']['email']}")


# --- plumbing -------------------------------------------------------------------

def _match(method, path):
    path_matched = False
    for m, rx, auth, fn, pattern in ROUTES:
        found = rx.match(path)
        if found:
            path_matched = True
            if m == method:
                return fn, auth, found.groupdict(), pattern
    raise ApiError(405 if path_matched else 404, "METHOD_NOT_ALLOWED" if path_matched else "NOT_FOUND",
                   "Method not allowed" if path_matched else "No such route")


def _parse(event):
    body = event.get("body")
    if body and event.get("isBase64Encoded"):
        body = base64.b64decode(body).decode()
    data = None
    if body:
        try:
            data = json.loads(body)
        except ValueError:
            raise bad_request("Body is not valid JSON") from None
    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
    return headers, data


def _authenticate(headers):
    raw = headers.get("authorization", "")
    token = raw[7:].strip() if raw.lower().startswith("bearer ") else ""
    claims = accounts.verify_token(token) if token else None
    if not claims:
        raise ApiError(401, "UNAUTHORIZED", "Please sign in again" if token else "Sign-in required")
    return claims


def _response(status, payload, request_id):
    return {
        "statusCode": status,
        "headers": {
            "content-type": "application/json",
            "cache-control": "no-store",
            "x-request-id": request_id,
        },
        "body": json.dumps(payload, separators=(",", ":"), default=str),
    }


def handler(event, context):
    started = time.perf_counter()
    http = (event.get("requestContext") or {}).get("http") or {}
    method = http.get("method", event.get("httpMethod", "GET")).upper()
    path = event.get("rawPath") or http.get("path") or "/"
    if len(path) > 1:
        path = path.rstrip("/")
    request_id = (event.get("requestContext") or {}).get("requestId") or getattr(context, "aws_request_id", None) or uuid.uuid4().hex
    route_name, user_id, status = None, None, 500

    try:
        if method == "OPTIONS":  # preflight normally answered by the function URL's CORS
            status, payload = 204, {}
        else:
            fn, auth, args, route_name = _match(method, path)
            headers, data = _parse(event)
            user = None
            if auth != "none":
                user = _authenticate(headers)
                user_id = user["sub"]
                if auth == "admin" and user["role"] != "admin":
                    raise forbidden("Admins only")
            req = {"json": data, "query": event.get("queryStringParameters") or {}, "headers": headers, "user": user}
            status, payload = fn(req, **args)
    except ApiError as err:
        status = err.status
        payload = {"error": {"code": err.code, "message": err.message, "requestId": request_id, **err.details}}
    except Exception as err:  # noqa: BLE001 - answer 500 with the request id, log the detail
        status = 500
        obs.log("unhandled_error", requestId=request_id, error=repr(err))
        obs.metric("ApiErrors")
        payload = {"error": {"code": "INTERNAL", "message": "Something went wrong on our side",
                             "requestId": request_id}}

    obs.log("request", method=method, route=route_name or path, status=status,
            latencyMs=round((time.perf_counter() - started) * 1000, 1),
            requestId=request_id, userId=user_id)
    return _response(status, payload, request_id)
