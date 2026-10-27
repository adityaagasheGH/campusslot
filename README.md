# CampusSlot

A serverless web app for booking campus facilities in time slots. No slot is ever booked
twice, slots nobody uses are released automatically, and the facility office sees how much
each space is really used. Runs on AWS in the AWS Academy lab (us-east-1).

```
Browser ──HTTPS──> CloudFront ──OAC──> S3 website bucket (private, React build + config.json)
   │
   └──HTTPS──> Lambda function URL ──> campusslot-api ───┐
                                                          ├──> S3 data bucket (bookings, slot locks,
EventBridge rate(15 min) ──> campusslot-sweeper ──────────┘     facilities, accounts)
                                         │
                       SNS campusslot-admin-alerts ──> facility office email
                       CloudWatch: logs, EMF metrics, dashboard, 3 alarms
```

No double booking: each slot is an S3 object `locks/<facility>/<date>/<HHMM>` created with
`If-None-Match: *`; S3 lets exactly one request create it. Status changes use
`If-Match: <ETag>` so concurrent updates can't overwrite each other.

## Layout

| Path | What |
| --- | --- |
| `backend/src/` | Python 3.13, standard library + boto3 only. `app.py` (API, 19 routes), `sweeper.py`, `accounts.py` (PBKDF2 + HS256 tokens), `facilities.py`, `bookings.py`, `lifecycle.py`, `storage.py`, `obs.py`, `notify.py` |
| `backend/tests/` | pytest + moto: rules, permissions, tokens, approvals, check-in window, sweeper, utilization, the 9-thread race |
| `backend/local_server.py` | The real API on emulated AWS with demo accounts and sample history |
| `frontend/` | React 18 + Vite 6, plain CSS, self-hosted Public Sans |
| `infrastructure/template.yaml` | One CloudFormation template (20 resources in the lab) |
| `scripts/` | `deploy.sh`, `seed_facilities.py`, `create_users.sh`, `smoke_test.sh`, `cleanup.sh`, `probe_permissions.sh`, `make_bundle.py` |
| `docs/DEPLOYMENT_GUIDE.md` | Step-by-step deployment from CloudShell |

## Run it locally

```bash
python -m venv .venv
.venv/Scripts/pip install -r backend/requirements-dev.txt     # .venv/bin/pip on macOS/Linux
.venv/Scripts/python -m pytest backend/tests -q
.venv/Scripts/python backend/local_server.py                   # API on :8787, prints demo accounts
cd frontend && npm install && npm run dev                      # site on :5173
```

## Deploy

```bash
python scripts/make_bundle.py        # on your laptop -> campusslot.zip
```

Then follow [docs/DEPLOYMENT_GUIDE.md](docs/DEPLOYMENT_GUIDE.md) in CloudShell.

## Limitations

Lab: us-east-1 only; the shared LabRole is broader than the least-privilege roles in the
template; no self-service sign-up or password reset; no request throttling (no API
Gateway); the signing key is a Lambda environment variable. Design: check-in is
honour-based; only admins get emails; one fixed time zone (IST).
