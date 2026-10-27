"""Run the real API code locally on emulated AWS (moto), with demo accounts and a
fictional booking history, for trying the frontend without an AWS account.

    python backend/local_server.py            # API on http://localhost:8787
    cd frontend && npm run dev                # site on http://localhost:5173

Everything lives in memory and is gone when the server stops."""
import json
import os
import random
import sys
from datetime import timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend" / "src"))

os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "local")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "local")
os.environ["DATA_BUCKET"] = "campusslot-data-local"
os.environ["AUTH_SIGNING_KEY"] = "local-development-signing-key-not-for-production-use-0000"
os.environ.pop("TOPIC_ARN", None)  # notifications are logged instead of emailed

from moto import mock_aws  # noqa: E402

PORT = int(os.environ.get("PORT", "8787"))
DEMO_PASSWORD = "campusslot-demo"
DEMO_USERS = [
    ("office@campusslot.local", "Facility Office", "admin"),
    ("asha@campusslot.local", "Asha Rao", "student"),
    ("rohan@campusslot.local", "Rohan Mehta", "student"),
]
PURPOSES = ["DBMS project meeting", "Badminton practice", "Mock interview prep", "Circuit lab assignment",
            "Study group: Operating Systems", "Club rehearsal", "Hackathon planning", "Guest lecture"]


def seed():
    import boto3

    import accounts
    import facilities
    import lifecycle as lc
    import storage
    import timeutil

    boto3.client("s3").create_bucket(Bucket=os.environ["DATA_BUCKET"])
    for f in json.loads((ROOT / "scripts" / "facilities.json").read_text()):
        storage.put_json(facilities.key(f["id"]), f)
    users = []
    for email, name, role in DEMO_USERS:
        u = accounts.make_user(email, name, role, DEMO_PASSWORD, iterations=50_000)
        accounts.save_new_user(u)
        users.append(u)

    # Fictional history: the last 10 days, with a realistic mix of outcomes.
    rnd = random.Random(7)
    today = timeutil.today()
    outcomes = [lc.COMPLETED] * 6 + [lc.NO_SHOW] * 2 + [lc.CANCELLED, lc.REJECTED]
    for back in range(10, 0, -1):
        day = today - timedelta(days=back)
        for f in rnd.sample(json.loads((ROOT / "scripts" / "facilities.json").read_text()), 4):
            grid = facilities.slot_times(f)
            n = rnd.randint(1, 2)
            i = rnd.randrange(0, len(grid) - n)
            slots = grid[i:i + n]
            user = rnd.choice(users[1:])
            status = rnd.choice(outcomes)
            if status == lc.REJECTED and not f["requiresApproval"]:
                status = lc.COMPLETED
            bid = f"{day.strftime('%Y%m%d')}-{rnd.getrandbits(48):012x}"
            at = timeutil.at(day, slots[0]).isoformat()
            first = lc.PENDING if f["requiresApproval"] else lc.CONFIRMED
            history = [{"at": at, "by": user["email"], "from": None, "to": first}]
            if status != first:
                history.append({"at": at, "by": "system:sweeper", "from": first, "to": status})
            booking = {
                "bookingId": bid, "userId": user["userId"], "userEmail": user["email"], "userName": user["name"],
                "facilityId": f["id"], "facilityName": f["name"], "date": day.isoformat(), "slots": slots,
                "startTime": slots[0], "endTime": facilities.slot_end(f, slots[-1]),
                "purpose": rnd.choice(PURPOSES), "people": min(f["capacity"], rnd.randint(2, 30)),
                "status": status, "createdAt": at, "updatedAt": at, "history": history,
            }
            if status == lc.REJECTED:
                booking["rejectReason"] = "Hall reserved for examinations"
            storage.put_json(lc.booking_key(bid), booking)
            storage.put_marker(lc.index_key(user["userId"], bid))


class Handler(BaseHTTPRequestHandler):
    def _cors(self):
        self.send_header("access-control-allow-origin", self.headers.get("origin") or "*")
        self.send_header("access-control-allow-headers", "authorization, content-type")
        self.send_header("access-control-allow-methods", "GET, POST, PUT, OPTIONS")
        self.send_header("access-control-expose-headers", "x-request-id")

    def _handle(self):
        import app

        url = urlsplit(self.path)
        length = int(self.headers.get("content-length") or 0)
        body = self.rfile.read(length).decode() if length else None
        event = {
            "rawPath": url.path,
            "rawQueryString": url.query,
            "queryStringParameters": dict(parse_qsl(url.query)) or None,
            "headers": {k.lower(): v for k, v in self.headers.items()},
            "body": body,
            "isBase64Encoded": False,
            "requestContext": {"requestId": os.urandom(8).hex(), "http": {"method": self.command, "path": url.path}},
        }
        resp = app.handler(event, None)
        self.send_response(resp["statusCode"])
        for k, v in resp["headers"].items():
            self.send_header(k, v)
        self._cors()
        self.end_headers()
        self.wfile.write(resp["body"].encode())

    do_GET = do_POST = do_PUT = do_DELETE = _handle

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def log_message(self, fmt, *args):
        pass  # the API already prints one JSON line per request


def main():
    with mock_aws():
        seed()
        print(f"CampusSlot local API on http://localhost:{PORT}")
        print(f"Demo accounts (password '{DEMO_PASSWORD}'):")
        for email, _, role in DEMO_USERS:
            print(f"  {role:8} {email}")
        ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
