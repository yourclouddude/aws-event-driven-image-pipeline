from __future__ import annotations

import json
import logging
import os
from io import BytesIO
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import unquote_plus

import boto3
from botocore.exceptions import ClientError
from PIL import Image

LOGGER = logging.getLogger()
LOGGER.setLevel(logging.INFO)

OUTPUT_BUCKET = os.environ.get("OUTPUT_BUCKET", "")
MAX_DIMENSION = int(os.environ.get("MAX_DIMENSION", "1024"))
MAX_IMAGE_BYTES = int(os.environ.get("MAX_IMAGE_BYTES", str(10 * 1024 * 1024)))
SUPPORTED_SUFFIXES = {".jpg", ".jpeg", ".png"}

_s3_client: Any | None = None


def get_s3_client() -> Any:
    global _s3_client
    if _s3_client is None:
        _s3_client = boto3.client("s3")
    return _s3_client


def log_event(action: str, **fields: Any) -> None:
    LOGGER.info(json.dumps({"action": action, **fields}, sort_keys=True, default=str))


def normalize_etag(value: str | None) -> str:
    return (value or "").strip('"')


def is_supported_key(key: str) -> bool:
    return PurePosixPath(key).suffix.lower() in SUPPORTED_SUFFIXES


def output_key_for(source_key: str) -> str:
    safe_key = source_key.lstrip("/")
    path = PurePosixPath(safe_key)
    without_suffix = str(path.with_suffix(""))
    return f"processed/{without_suffix}.jpg"


def is_already_processed(s3: Any, output_key: str, source_etag: str) -> bool:
    if not source_etag:
        return False

    try:
        response = s3.head_object(Bucket=OUTPUT_BUCKET, Key=output_key)
    except ClientError as exc:
        code = str(exc.response.get("Error", {}).get("Code", ""))
        if code in {"404", "NoSuchKey", "NotFound"}:
            return False
        raise

    existing_etag = response.get("Metadata", {}).get("source-etag", "")
    return existing_etag == source_etag


def resize_to_jpeg(payload: bytes) -> tuple[bytes, int, int]:
    with Image.open(BytesIO(payload)) as source:
        source.load()
        source.thumbnail((MAX_DIMENSION, MAX_DIMENSION), Image.Resampling.LANCZOS)
        converted = source.convert("RGB")
        try:
            output = BytesIO()
            converted.save(output, format="JPEG", quality=85, optimize=True)
            return output.getvalue(), converted.width, converted.height
        finally:
            converted.close()


def process_s3_record(record: dict[str, Any]) -> dict[str, Any]:
    bucket = record["s3"]["bucket"]["name"]
    source_key = unquote_plus(record["s3"]["object"]["key"])
    event_etag = normalize_etag(record["s3"]["object"].get("eTag"))

    if not is_supported_key(source_key):
        log_event("skip_unsupported", bucket=bucket, key=source_key)
        return {"status": "skipped", "source_key": source_key}

    if not OUTPUT_BUCKET:
        raise RuntimeError("OUTPUT_BUCKET is not configured")

    s3 = get_s3_client()
    output_key = output_key_for(source_key)

    if is_already_processed(s3, output_key, event_etag):
        log_event("skip_duplicate", bucket=bucket, key=source_key, output_key=output_key)
        return {"status": "duplicate", "source_key": source_key, "output_key": output_key}

    source = s3.get_object(Bucket=bucket, Key=source_key)
    content_length = int(source.get("ContentLength", 0))
    if content_length > MAX_IMAGE_BYTES:
        raise ValueError(f"image exceeds {MAX_IMAGE_BYTES} byte limit")

    payload = source["Body"].read(MAX_IMAGE_BYTES + 1)
    if len(payload) > MAX_IMAGE_BYTES:
        raise ValueError(f"image exceeds {MAX_IMAGE_BYTES} byte limit")

    source_etag = event_etag or normalize_etag(source.get("ETag"))
    jpeg, width, height = resize_to_jpeg(payload)

    s3.put_object(
        Bucket=OUTPUT_BUCKET,
        Key=output_key,
        Body=jpeg,
        ContentType="image/jpeg",
        Metadata={
            "source-etag": source_etag or "unknown",
            "source-bucket": bucket,
            "source-key": source_key,
            "width": str(width),
            "height": str(height),
        },
    )

    log_event(
        "processed",
        source_bucket=bucket,
        source_key=source_key,
        output_bucket=OUTPUT_BUCKET,
        output_key=output_key,
        width=width,
        height=height,
    )
    return {
        "status": "processed",
        "source_key": source_key,
        "output_key": output_key,
        "width": width,
        "height": height,
    }


def process_sqs_message(record: dict[str, Any]) -> list[dict[str, Any]]:
    body = json.loads(record["body"])

    if body.get("Event") == "s3:TestEvent":
        log_event("skip_s3_test_event")
        return []

    s3_records = body.get("Records")
    if not isinstance(s3_records, list) or not s3_records:
        raise ValueError("SQS message does not contain S3 event records")

    return [process_s3_record(s3_record) for s3_record in s3_records]


def handler(event: dict[str, Any], _context: Any) -> dict[str, list[dict[str, str]]]:
    failures: list[dict[str, str]] = []

    for record in event.get("Records", []):
        message_id = str(record.get("messageId", "unknown"))
        try:
            process_sqs_message(record)
        except Exception:
            LOGGER.exception("image processing failed for SQS message %s", message_id)
            failures.append({"itemIdentifier": message_id})

    return {"batchItemFailures": failures}
