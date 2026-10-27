"""Sign-in built from the standard library (the lab blocks Cognito).

Passwords: salted PBKDF2-HMAC-SHA256, 310,000 rounds; only the hash is stored in
users/<email>.json. Tokens: JSON Web Tokens signed with HS256, valid for 60 minutes."""
import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import time
import uuid

import storage
import timeutil
from errors import ApiError, bad_request

ITERATIONS = 310_000
TOKEN_TTL_SECONDS = 60 * 60
ROLES = ("student", "admin")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# Used when the email is unknown, so both failure paths do the same work.
_DUMMY = {"salt": "00" * 16, "hash": "00" * 32, "iterations": ITERATIONS}


def user_key(email):
    return f"users/{email.strip().lower()}.json"


def hash_password(password, iterations=None, salt=None):
    iterations = iterations or ITERATIONS
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
    return {"salt": salt.hex(), "hash": digest.hex(), "iterations": iterations}


def verify_password(password, record):
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode(), bytes.fromhex(record["salt"]), int(record["iterations"])
    )
    return hmac.compare_digest(digest.hex(), record["hash"])


def make_user(email, name, role, password, iterations=None):
    email = email.strip().lower()
    if not EMAIL_RE.match(email):
        raise ValueError("invalid email")
    if role not in ROLES:
        raise ValueError("role must be student or admin")
    if len(password) < 8:
        raise ValueError("password must be at least 8 characters")
    return {
        "userId": uuid.uuid4().hex[:16],
        "email": email,
        "name": name.strip() or email.split("@")[0],
        "role": role,
        "password": hash_password(password, iterations),
        "createdAt": timeutil.iso_now(),
    }


def save_new_user(user):
    """Create the account; refuses to overwrite an existing one."""
    storage.put_json(user_key(user["email"]), user, if_none_match=True)


def sign_in(email, password):
    if not isinstance(email, str) or not isinstance(password, str) or not email or not password:
        raise bad_request("Email and password are required")
    user, _ = storage.try_get_json(user_key(email))
    ok = verify_password(password, user["password"] if user else _DUMMY)
    if not user or not ok:
        raise ApiError(401, "INVALID_CREDENTIALS", "Email or password is incorrect")
    return {"token": issue_token(user), "user": public_user(user), "expiresIn": TOKEN_TTL_SECONDS}


def public_user(user):
    return {"userId": user["userId"], "email": user["email"], "name": user["name"], "role": user["role"]}


# --- tokens -------------------------------------------------------------------

def _b64(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(text):
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _key():
    key = os.environ.get("AUTH_SIGNING_KEY", "")
    if len(key) < 32:
        raise RuntimeError("AUTH_SIGNING_KEY is missing or too short")
    return key.encode()


def issue_token(user, ttl=TOKEN_TTL_SECONDS):
    issued = int(time.time())
    header = _b64(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    payload = _b64(json.dumps({
        "sub": user["userId"], "email": user["email"], "name": user["name"],
        "role": user["role"], "iat": issued, "exp": issued + ttl,
    }).encode())
    sig = _b64(hmac.new(_key(), f"{header}.{payload}".encode(), hashlib.sha256).digest())
    return f"{header}.{payload}.{sig}"


def verify_token(token):
    """Return the claims of a valid token, or None."""
    try:
        header, payload, sig = token.split(".")
        expected = _b64(hmac.new(_key(), f"{header}.{payload}".encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(sig, expected):
            return None
        if json.loads(_unb64(header)).get("alg") != "HS256":
            return None
        claims = json.loads(_unb64(payload))
        if int(claims.get("exp", 0)) <= time.time():
            return None
        if claims.get("role") not in ROLES or not claims.get("sub"):
            return None
        return claims
    except (ValueError, KeyError, TypeError, AttributeError):
        return None
