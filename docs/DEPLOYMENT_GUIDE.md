# Deploying CampusSlot to the AWS Academy lab

Everything runs from **AWS CloudShell** (a terminal inside the AWS console). No access
keys are created and nothing is installed on your laptop. A first deploy takes about
10–15 minutes, most of it CloudFront.

## 0. What you need

- `campusslot.zip` (the project, built by `python scripts/make_bundle.py` on your laptop).
- An AWS Academy Learner Lab session that is **started** (green dot). Sessions last
  3 hours; the stack survives between sessions, CloudShell's home folder does too.
- Access to the facility office mailbox (kherakartik17@gmail.com) to confirm alerts.

## 1. Open CloudShell in us-east-1

1. In the lab, click **AWS** (green dot) to open the console.
2. Check the region selector (top right) says **N. Virginia (us-east-1)**.
3. Click the CloudShell icon (`>_`) in the top bar. Wait for the prompt.

## 2. Upload and unpack the project

1. In CloudShell: **Actions → Upload file** → choose `campusslot.zip`.
2. Run:

```bash
cd ~ && rm -rf campusslot && unzip -q campusslot.zip -d campusslot && cd campusslot
```

## 3. (Optional) check what the lab allows

```bash
bash scripts/probe_permissions.sh
```

Expect ALLOWED for S3, S3 conditional write, Lambda, function URL, SNS, EventBridge
rule, CloudFront OAC, CloudWatch and CloudFormation; DENIED for DynamoDB, API Gateway,
Cognito, IAM role, SQS, SES, Scheduler and Secrets Manager. If S3/Lambda/CloudFront
show DENIED, stop here: the design depends on them.

## 4. Deploy

```bash
bash scripts/deploy.sh
```

It will: upgrade CloudShell's boto3 if needed, find `LabRole`, generate a signing key
once (kept in `~/.campusslot/signing-key`), zip and upload the backend (~20 KB), create
the `campusslot` stack (20 resources), build the React app, upload it, and call
`/health`. It ends by printing the **website URL** and **API URL** — note them.

To send alerts somewhere else: `ALERT_EMAIL=someone@example.com bash scripts/deploy.sh`.

## 5. Confirm the alert email

AWS sends "AWS Notification - Subscription Confirmation" to the alert address. Click
**Confirm subscription** in it. Until then approval requests, sweep summaries and
alarms are not delivered (bookings still work).

## 6. Load facilities and create accounts

```bash
python3 scripts/seed_facilities.py
bash scripts/create_users.sh
```

`create_users.sh` asks for email, name, role and a hidden password (8+ characters),
one account at a time; press Enter on an empty email to finish. For the demo create
1 admin (the facility office) and 2 students. To add one account later:

```bash
bash scripts/create_users.sh student3@example.com "Student Three" student
```

## 7. Smoke test

```bash
SMOKE_EMAIL=<a student email> bash scripts/smoke_test.sh
```

15 checks: HTTPS, redirect, security headers, config, SPA fallback, private bucket,
health, 401s, CORS, request IDs, sign-in and the admin-route 403. If the website
checks fail right after the first deploy, CloudFront is still spreading — wait 5
minutes and run it again.

## 8. Try it

Open the website URL, sign in as a student, book a slot; book Seminar Hall A to see a
Pending request (and the approval email); sign in as the admin → **Manage** to approve,
see utilization, and run the sweep.

## Updating after a code change

Upload the new zip, unpack it the same way (step 2), and run `bash scripts/deploy.sh`
again. Only what changed is updated; data and accounts are kept.

## Where to look when something is wrong

| Symptom | Where |
| --- | --- |
| Error shown in the app with a Request ID | CloudWatch → Log groups → `/aws/lambda/campusslot-api` → search the ID |
| Requests per route / status | CloudWatch Logs Insights on that group: `filter event="request" \| stats count() by route, status` |
| Overall health | CloudWatch → Dashboards → `campusslot-operations` |
| Sweeper | `/aws/lambda/campusslot-sweeper`, lines with `"event":"sweep_done"` |
| Deploy failed | `deploy.sh` prints the failing resources; full list in CloudFormation → `campusslot` → Events |

Common deploy problems:

- **`ROLLBACK_COMPLETE`** from an earlier failed attempt — `deploy.sh` deletes the empty
  stack and retries automatically.
- **Function URL answers 403** — both `lambda:InvokeFunctionUrl` and
  `lambda:InvokeFunction` permissions must exist (they are in the template).
- **`Unknown parameter IfNoneMatch`** in the seed/user scripts — CloudShell's boto3 is too
  old: `python3 -m pip install --user --upgrade 'boto3>=1.35.60'`.
- **Website shows the old version** — `deploy.sh` invalidates `index.html` and
  `config.json`; hard-refresh the browser.

## Removing everything

```bash
bash scripts/cleanup.sh
```

Type `campusslot` to confirm. It empties both buckets, deletes the stack and the
artifacts bucket. All bookings and accounts are lost.
