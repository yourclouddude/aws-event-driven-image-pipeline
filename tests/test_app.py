from __future__ import annotations

import json
from io import BytesIO
from typing import Any

import pytest
from botocore.exceptions import ClientError
from PIL import Image

import app


class FakeS3:
    def __init__(
        self,
        payload: bytes | None = None,
        *,
        existing_metadata: dict[str, str] | None = None,
        content_length: int | None = None,
    ) -> None:
        self.payload = payload or b""
        self.existing_metadata = existing_metadata
        self.content_length = content_length if content_length is not None else len(self.payload)
        self.get_calls: list[dict[str, Any]] = []
        self.put_calls: list[dict[str, Any]] = []

    def head_object(self, **kwargs: Any) -> dict[str, Any]:
        if self.existing_metadata is None:
            raise ClientError(
                {"Error": {"Code": "404", "Message": "Not Found"}},
                "HeadObject",
            )
        return {"Metadata": self.existing_metadata}

    def get_object(self, **kwargs: Any) -> dict[str, Any]:
        self.get_calls.append(kwargs)
        return {
            "Body": BytesIO(self.payload),
            "ContentLength": self.content_length,
            "ETag": '"etag-from-object"',
        }

    def put_object(self, **kwargs: Any) -> dict[str, Any]:
        self.put_calls.append(kwargs)
        return {"ETag": '"output-etag"'}


def image_bytes(width: int = 1600, height: int = 900) -> bytes:
    output = BytesIO()
    image = Image.new("RGB", (width, height), "white")
    try:
        image.save(output, format="PNG")
    finally:
        image.close()
    return output.getvalue()


def sqs_record(
    *,
    message_id: str = "message-1",
    key: str = "photos/demo.png",
    etag: str = "etag-1",
    body: str | None = None,
) -> dict[str, Any]:
    if body is None:
        s3_event = {
            "Records": [
                {
                    "eventName": "ObjectCreated:Put",
                    "s3": {
                        "bucket": {"name": "upload-bucket"},
                        "object": {"key": key, "eTag": etag},
                    },
                }
            ]
        }
        body = json.dumps(s3_event)
    return {"messageId": message_id, "body": body}


@pytest.fixture(autouse=True)
def configured_output_bucket(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(app, "OUTPUT_BUCKET", "processed-bucket")


def test_processes_image_and_writes_deterministic_output(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeS3(image_bytes())
    monkeypatch.setattr(app, "get_s3_client", lambda: fake)

    result = app.handler({"Records": [sqs_record()]}, None)

    assert result == {"batchItemFailures": []}
    assert len(fake.get_calls) == 1
    assert len(fake.put_calls) == 1
    written = fake.put_calls[0]
    assert written["Bucket"] == "processed-bucket"
    assert written["Key"] == "processed/photos/demo.jpg"
    assert written["ContentType"] == "image/jpeg"
    assert written["Metadata"]["source-etag"] == "etag-1"

    with Image.open(BytesIO(written["Body"])) as processed:
        assert processed.format == "JPEG"
        assert max(processed.size) <= app.MAX_DIMENSION


def test_skips_duplicate_when_output_has_same_source_etag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeS3(existing_metadata={"source-etag": "etag-1"})
    monkeypatch.setattr(app, "get_s3_client", lambda: fake)

    result = app.handler({"Records": [sqs_record()]}, None)

    assert result == {"batchItemFailures": []}
    assert fake.get_calls == []
    assert fake.put_calls == []


def test_unsupported_extension_is_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeS3()
    monkeypatch.setattr(app, "get_s3_client", lambda: fake)

    result = app.handler({"Records": [sqs_record(key="notes/readme.txt")]}, None)

    assert result == {"batchItemFailures": []}
    assert fake.get_calls == []
    assert fake.put_calls == []


def test_oversized_image_is_reported_as_batch_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeS3(b"small", content_length=app.MAX_IMAGE_BYTES + 1)
    monkeypatch.setattr(app, "get_s3_client", lambda: fake)

    result = app.handler({"Records": [sqs_record(message_id="too-large")]}, None)

    assert result == {"batchItemFailures": [{"itemIdentifier": "too-large"}]}
    assert fake.put_calls == []


def test_excessive_pixel_count_is_reported_as_batch_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(app, "MAX_IMAGE_PIXELS", 10_000)
    fake = FakeS3(image_bytes(101, 101))
    monkeypatch.setattr(app, "get_s3_client", lambda: fake)

    result = app.handler({"Records": [sqs_record(message_id="too-many-pixels")]}, None)

    assert result == {"batchItemFailures": [{"itemIdentifier": "too-many-pixels"}]}
    assert fake.put_calls == []


def test_malformed_message_is_reported_as_batch_failure() -> None:
    result = app.handler(
        {"Records": [sqs_record(message_id="bad-json", body="not-json")]},
        None,
    )

    assert result == {"batchItemFailures": [{"itemIdentifier": "bad-json"}]}


def test_partial_batch_response_retries_only_failed_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeS3(image_bytes(400, 300))
    monkeypatch.setattr(app, "get_s3_client", lambda: fake)
    event = {
        "Records": [
            sqs_record(message_id="good"),
            sqs_record(message_id="bad", body="{}"),
        ]
    }

    result = app.handler(event, None)

    assert result == {"batchItemFailures": [{"itemIdentifier": "bad"}]}
    assert len(fake.put_calls) == 1


def test_s3_test_event_is_acknowledged() -> None:
    body = json.dumps({"Event": "s3:TestEvent"})

    result = app.handler({"Records": [sqs_record(body=body)]}, None)

    assert result == {"batchItemFailures": []}
