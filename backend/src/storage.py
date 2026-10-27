"""S3 data bucket used as the database: small JSON objects plus conditional writes."""
import json
import os
from concurrent.futures import ThreadPoolExecutor

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

_client = None


class NotFound(Exception):
    pass


class PreconditionFailed(Exception):
    """The If-None-Match / If-Match condition was not met."""


def client():
    global _client
    if _client is None:
        _client = boto3.client(
            "s3",
            config=Config(max_pool_connections=32, retries={"mode": "standard", "max_attempts": 3}),
        )
    return _client


def reset():
    """Forget the cached client (tests start a fresh mocked AWS each time)."""
    global _client
    _client = None


def bucket():
    return os.environ["DATA_BUCKET"]


def _code(err):
    return err.response.get("Error", {}).get("Code", "")


def get_json(key):
    """Return (object, etag). Raises NotFound."""
    try:
        resp = client().get_object(Bucket=bucket(), Key=key)
    except ClientError as err:
        if _code(err) in ("NoSuchKey", "404", "NotFound"):
            raise NotFound(key) from None
        raise
    return json.loads(resp["Body"].read()), resp["ETag"]


def try_get_json(key):
    try:
        return get_json(key)
    except NotFound:
        return None, None


def put_json(key, obj, if_none_match=False, if_match=None):
    """Write a JSON object. if_none_match=True creates only if absent; if_match=<etag>
    replaces only if unchanged since it was read. Returns the new ETag."""
    kwargs = {
        "Bucket": bucket(),
        "Key": key,
        "Body": json.dumps(obj, separators=(",", ":")).encode(),
        "ContentType": "application/json",
    }
    if if_none_match:
        kwargs["IfNoneMatch"] = "*"
    if if_match:
        kwargs["IfMatch"] = if_match
    try:
        return client().put_object(**kwargs)["ETag"]
    except ClientError as err:
        # 412 PreconditionFailed; 409 ConditionalRequestConflict when two writes race.
        if _code(err) in ("PreconditionFailed", "ConditionalRequestConflict", "412", "409"):
            raise PreconditionFailed(key) from None
        if if_match and _code(err) in ("NoSuchKey", "404"):
            raise PreconditionFailed(key) from None
        raise


def put_marker(key):
    client().put_object(Bucket=bucket(), Key=key, Body=b"")


def delete(key):
    client().delete_object(Bucket=bucket(), Key=key)


def list_objects(prefix):
    """All objects under a prefix: [{'Key', 'LastModified'}]."""
    out = []
    for page in client().get_paginator("list_objects_v2").paginate(Bucket=bucket(), Prefix=prefix):
        out.extend({"Key": o["Key"], "LastModified": o["LastModified"]} for o in page.get("Contents", []))
    return out


def list_keys(prefix):
    return [o["Key"] for o in list_objects(prefix)]


def get_many(keys):
    """Read many JSON objects in parallel. Missing ones are skipped.
    Returns a list of (key, object, etag) in the order given."""
    keys = list(keys)
    if not keys:
        return []
    with ThreadPoolExecutor(max_workers=min(16, len(keys))) as pool:
        results = list(pool.map(try_get_json, keys))
    return [(k, obj, etag) for k, (obj, etag) in zip(keys, results) if obj is not None]
