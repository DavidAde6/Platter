from __future__ import annotations

import hashlib
import io
import os
from dataclasses import dataclass
from functools import lru_cache

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


@dataclass(frozen=True)
class ImageAsset:
    """A variant that is now in R2, described by what was actually stored.

    Everything here is measured from the bytes rather than inferred later.
    The object key in particular cannot be reconstructed from ids, because
    the extension comes from the content type or, failing that, the client's
    filename -- so it has to be carried, not recomputed.
    """

    role: str
    object_key: str
    content_type: str
    byte_size: int
    sha256: str
    image_format: str | None = None
    width: int | None = None
    height: int | None = None


@dataclass(frozen=True)
class UploadedAssets:
    """The result of one upload.

    ``thumbnail`` is None when thumbnail generation failed. It is never the
    original: the previous code aliased the two keys on failure, which made
    the database claim a thumbnail existed and then serve a multi-megabyte
    original to a list view.
    """

    original: ImageAsset
    thumbnail: ImageAsset | None


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


def _build_thumbnail(content: bytes) -> tuple[bytes, int, int]:
    """Downscaled JPEG plus its real dimensions."""
    with Image.open(io.BytesIO(content)) as img:
        if getattr(img, "is_animated", False) and getattr(img, "n_frames", 1) > 1:
            img.seek(0)
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        img.thumbnail((THUMBNAIL_MAX_SIZE, THUMBNAIL_MAX_SIZE))
        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=85, optimize=True)
        return buffer.getvalue(), img.width, img.height


def _describe(content: bytes) -> tuple[str | None, int | None, int | None]:
    """Pillow format and dimensions, or Nones if it will not decode.

    Best-effort by design: a file we cannot decode can still be stored, and
    the quality gate is what decides whether it was usable.
    """
    try:
        with Image.open(io.BytesIO(content)) as img:
            return img.format, img.width, img.height
    except Exception:
        return None, None, None


def upload_meal_images(
    user_id: int,
    meal_id: int,
    content: bytes,
    content_type: str,
    filename: str | None,
) -> UploadedAssets:
    """Put the original and a thumbnail in R2 and describe what was stored.

    A thumbnail failure is not an upload failure -- the original is what
    matters -- but it is reported as an absent variant rather than papered
    over by pointing the thumbnail at the original.
    """
    if not is_r2_configured():
        raise RuntimeError("Cloudflare R2 is not configured")

    extension = _extension(content_type, filename)
    original_key = _object_key(user_id, meal_id, "original", extension)

    _upload_object(original_key, content, content_type)

    image_format, width, height = _describe(content)
    original = ImageAsset(
        role="original",
        object_key=original_key,
        content_type=content_type,
        byte_size=len(content),
        sha256=hashlib.sha256(content).hexdigest(),
        image_format=image_format,
        width=width,
        height=height,
    )

    thumbnail: ImageAsset | None = None
    try:
        thumbnail_bytes, thumb_w, thumb_h = _build_thumbnail(content)
        thumbnail_key = _object_key(user_id, meal_id, "thumbnail", "jpg")
        _upload_object(thumbnail_key, thumbnail_bytes, "image/jpeg")
        thumbnail = ImageAsset(
            role="thumbnail",
            object_key=thumbnail_key,
            content_type="image/jpeg",
            byte_size=len(thumbnail_bytes),
            sha256=hashlib.sha256(thumbnail_bytes).hexdigest(),
            image_format="JPEG",
            width=thumb_w,
            height=thumb_h,
        )
    except Exception:
        thumbnail = None

    return UploadedAssets(original=original, thumbnail=thumbnail)


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


def _image_proxy_path(meal_id: int, role: str) -> str:
    return f"/api/meals/{meal_id}/image?variant={role}"


def meal_image_paths(
    meal_id: int, *, has_original: bool, has_thumbnail: bool
) -> tuple[str | None, str | None]:
    """Authenticated proxy paths for a meal's variants, as (original, thumbnail).

    The client never receives an object key or a presigned R2 URL -- only a
    path served by this API, which checks auth and ownership before streaming
    bytes. The paths are derived from (meal_id, role), so nothing about the
    storage layout leaks.

    Takes explicit booleans rather than probing a row dict. The previous
    version read ``meal.get("image_url")``, which meant a renamed or missing
    projection column produced None for both paths -- images silently vanished
    from the UI with no error raised anywhere.
    """
    original = _image_proxy_path(meal_id, "original") if has_original else None
    thumbnail = _image_proxy_path(meal_id, "thumbnail") if has_thumbnail else None
    return original, thumbnail
