from __future__ import annotations

import io
import os
from functools import lru_cache
from typing import Any

import boto3
from botocore.client import BaseClient
from botocore.config import Config
from botocore.exceptions import ClientError
from PIL import Image

CONTENT_TYPE_EXTENSIONS = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/heic": "heic",
    "image/heif": "heif",
}

THUMBNAIL_MAX_SIZE = 256


def is_r2_configured() -> bool:
    required = (
        "R2_ACCOUNT_ID",
        "R2_ACCESS_KEY_ID",
        "R2_SECRET_ACCESS_KEY",
        "R2_BUCKET_NAME",
    )
    return all(os.environ.get(key) for key in required)


def _extension(content_type: str, filename: str | None) -> str:
    ext = CONTENT_TYPE_EXTENSIONS.get(content_type)
    if ext:
        return ext
    if filename and "." in filename:
        return filename.rsplit(".", 1)[-1].lower()
    return "jpg"


def _object_key(user_id: int, meal_id: int, suffix: str, extension: str) -> str:
    return f"users/{user_id}/meals/{meal_id}/{suffix}.{extension}"


@lru_cache(maxsize=1)
def _get_client() -> BaseClient:
    account_id = os.environ["R2_ACCOUNT_ID"]
    return boto3.client(
        "s3",
        endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        config=Config(signature_version="s3v4"),
        region_name="auto",
    )


def _upload_object(key: str, content: bytes, content_type: str) -> None:
    client = _get_client()
    bucket = os.environ["R2_BUCKET_NAME"]
    try:
        client.put_object(
            Bucket=bucket,
            Key=key,
            Body=content,
            ContentType=content_type,
        )
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "Unknown")
        message = exc.response.get("Error", {}).get("Message", str(exc))
        raise RuntimeError(f"R2 upload failed ({code}): {message}") from exc


def _build_thumbnail(content: bytes) -> bytes:
    with Image.open(io.BytesIO(content)) as img:
        if getattr(img, "is_animated", False) and getattr(img, "n_frames", 1) > 1:
            img.seek(0)
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        img.thumbnail((THUMBNAIL_MAX_SIZE, THUMBNAIL_MAX_SIZE))
        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=85, optimize=True)
        return buffer.getvalue()


def upload_meal_images(
    user_id: int,
    meal_id: int,
    content: bytes,
    content_type: str,
    filename: str | None,
) -> tuple[str, str]:
    if not is_r2_configured():
        raise RuntimeError("Cloudflare R2 is not configured")

    extension = _extension(content_type, filename)
    original_key = _object_key(user_id, meal_id, "original", extension)
    thumbnail_key = _object_key(user_id, meal_id, "thumbnail", "jpg")

    _upload_object(original_key, content, content_type)

    try:
        thumbnail_bytes = _build_thumbnail(content)
        _upload_object(thumbnail_key, thumbnail_bytes, "image/jpeg")
    except Exception:
        thumbnail_key = original_key

    return original_key, thumbnail_key


def fetch_meal_image(object_key: str) -> tuple[bytes, str]:
    """Download an image's raw bytes straight from R2.

    No URL is ever generated, so the image never becomes reachable from
    outside the server. Use this for backend processing (e.g. AI analysis)
    and for the authenticated image proxy endpoint.

    Returns (content, content_type).
    """
    if not is_r2_configured():
        raise RuntimeError("Cloudflare R2 is not configured")

    client = _get_client()
    bucket = os.environ["R2_BUCKET_NAME"]
    try:
        response = client.get_object(Bucket=bucket, Key=object_key)
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "Unknown")
        message = exc.response.get("Error", {}).get("Message", str(exc))
        raise RuntimeError(f"R2 fetch failed ({code}): {message}") from exc

    content_type = response.get("ContentType") or "application/octet-stream"
    return response["Body"].read(), content_type


def _image_proxy_path(meal_id: int, variant: str) -> str:
    return f"/api/meals/{meal_id}/image?variant={variant}"


def resolve_meal_urls(meal: dict[str, Any]) -> dict[str, Any]:
    """Replace stored R2 object keys with authenticated proxy paths.

    The frontend never receives a public or presigned R2 URL; instead it
    gets a path served by our own API, which enforces auth and ownership.
    """
    resolved = dict(meal)
    meal_id = meal.get("meal_id")

    resolved["image_url"] = (
        _image_proxy_path(meal_id, "original")
        if meal_id is not None and meal.get("image_url")
        else None
    )
    resolved["thumbnail_url"] = (
        _image_proxy_path(meal_id, "thumbnail")
        if meal_id is not None and meal.get("thumbnail_url")
        else None
    )
    return resolved
