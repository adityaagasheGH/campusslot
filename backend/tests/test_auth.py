import time

import accounts
from conftest import call


def test_password_is_stored_only_as_pbkdf2_hash(users):
    import storage
    record, _ = storage.get_json("users/alice@campus.test.json")
    assert "correct-horse-1" not in str(record)
    assert set(record["password"]) == {"salt", "hash", "iterations"}


def test_production_hash_uses_310k_rounds(monkeypatch):
    monkeypatch.undo()  # restore the real ITERATIONS
    rec = accounts.hash_password("s3cret-pass")
    assert rec["iterations"] == 310_000
    assert accounts.verify_password("s3cret-pass", rec)
    assert not accounts.verify_password("wrong-pass", rec)


def test_sign_in_returns_token_valid_60_minutes(users, api):
    status, body = api("POST", "/auth/sign-in", body={"email": "Alice@Campus.test", "password": "correct-horse-1"})
    assert status == 200
    assert body["user"]["role"] == "student"
    claims = accounts.verify_token(body["token"])
    assert claims["exp"] - claims["iat"] == 3600


def test_wrong_password_and_unknown_email_get_same_answer(users, api):
    s1, b1 = api("POST", "/auth/sign-in", body={"email": "alice@campus.test", "password": "nope-nope"})
    s2, b2 = api("POST", "/auth/sign-in", body={"email": "nobody@campus.test", "password": "nope-nope"})
    assert s1 == s2 == 401
    assert b1["error"]["message"] == b2["error"]["message"]


def test_missing_forged_and_expired_tokens_get_401(users, api):
    assert api("GET", "/facilities")[0] == 401
    good = accounts.issue_token(users["alice"])
    head, payload, _ = good.split(".")
    assert api("GET", "/facilities", f"{head}.{payload}.forged")[0] == 401
    expired = accounts.issue_token(users["alice"], ttl=-1)
    assert api("GET", "/facilities", expired)[0] == 401


def test_token_signed_with_other_key_rejected(users, api, monkeypatch):
    monkeypatch.setenv("AUTH_SIGNING_KEY", "z" * 64)
    other = accounts.issue_token(users["alice"])
    monkeypatch.setenv("AUTH_SIGNING_KEY", "k" * 64)
    assert api("GET", "/me", other)[0] == 401


def test_health_needs_no_token(aws, api):
    status, body = api("GET", "/health")
    assert status == 200 and body["status"] == "ok"


def test_student_cannot_use_admin_routes(tokens, api):
    for method, path in [("GET", "/admin/approvals"), ("POST", "/admin/sweep"), ("GET", "/admin/bookings")]:
        assert api(method, path, tokens["alice"])[0] == 403


def test_unknown_route_404_and_wrong_method_405(tokens, api):
    assert api("GET", "/nope", tokens["alice"])[0] == 404
    assert api("DELETE", "/facilities", tokens["alice"])[0] == 405


def test_errors_carry_request_id(tokens, api):
    _, body = api("GET", "/nope", tokens["alice"])
    assert body["error"]["requestId"] == "req-test"


def test_me_returns_identity(tokens, api):
    status, body = api("GET", "/me", tokens["admin"])
    assert status == 200 and body["role"] == "admin" and body["email"] == "office@campus.test"


def test_duplicate_account_refused(users):
    import pytest
    import storage
    with pytest.raises(storage.PreconditionFailed):
        accounts.save_new_user(accounts.make_user("alice@campus.test", "A2", "student", "another-pass", 1000))
    assert time.time()  # account untouched
    rec, _ = storage.get_json("users/alice@campus.test.json")
    assert rec["name"] == "Alice"
