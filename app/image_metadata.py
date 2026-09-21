from __future__ import annotations

import io
from typing import Any

from fastapi import UploadFile
from PIL import Image, ExifTags, UnidentifiedImageError

try:
    import pillow_heif

    pillow_heif.register_heif_opener()
except ImportError:
    pass

EXIF_TAG_NAMES = ExifTags.TAGS
GPS_TAG_NAMES = ExifTags.GPSTAGS

GPS_TAG_IDS = {name: tag_id for tag_id, name in ExifTags.GPSTAGS.items()}


def _serialize_exif_value(value: Any) -> Any:
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8", errors="replace")
        except Exception:
            return value.hex()
    if isinstance(value, tuple):
        if len(value) == 2 and all(isinstance(part, int) for part in value):
            return value[0] / value[1] if value[1] else None
        return [_serialize_exif_value(part) for part in value]
    if hasattr(value, "numerator") and hasattr(value, "denominator"):
        return float(value) if value.denominator else None
    return value


def _dms_to_decimal(dms: Any, ref: str | None) -> float | None:
    if not dms or len(dms) < 3:
        return None
    try:
        degrees = _serialize_exif_value(dms[0])
        minutes = _serialize_exif_value(dms[1])
        seconds = _serialize_exif_value(dms[2])
        if None in (degrees, minutes, seconds):
            return None
        decimal = float(degrees) + float(minutes) / 60.0 + float(seconds) / 3600.0
        if ref in ("S", "W"):
            decimal = -decimal
        return round(decimal, 7)
    except (TypeError, ValueError):
        return None


def _attach_exif_metadata(metadata: dict[str, Any], img: Image.Image) -> None:
    exif = img.getexif()

    if not exif:
        metadata["has_exif"] = False
        metadata["exif"] = {}
        return

    metadata["has_exif"] = True
    exif_flat: dict[str, Any] = {}

    for tag_id, value in exif.items():
        if tag_id == ExifTags.Base.GPSInfo:
            continue

        name = EXIF_TAG_NAMES.get(tag_id, str(tag_id))

        try:
            exif_flat[name] = _serialize_exif_value(value)
        except Exception as exc:
            exif_flat[name] = {"error": str(exc)}

    metadata["exif"] = exif_flat

    metadata["make"] = exif_flat.get("Make")
    metadata["model"] = exif_flat.get("Model")
    metadata["orientation"] = exif_flat.get("Orientation")

    metadata["datetime"] = exif_flat.get("DateTime")
    metadata["datetime_original"] = (
        exif_flat.get("DateTimeOriginal")
        or exif_flat.get("DateTime")
    )

    metadata["focal_length"] = exif_flat.get("FocalLength")
    metadata["focal_length_35mm"] = exif_flat.get("FocalLengthIn35mmFilm")
    metadata["exposure_time"] = exif_flat.get("ExposureTime")
    metadata["f_number"] = exif_flat.get("FNumber")
    metadata["iso"] = (
        exif_flat.get("ISOSpeedRatings")
        or exif_flat.get("PhotographicSensitivity")
    )
    metadata["flash"] = exif_flat.get("Flash")
    metadata["lens_model"] = exif_flat.get("LensModel")
    metadata["software"] = exif_flat.get("Software")

    try:
        gps_ifd = exif.get_ifd(ExifTags.Base.GPSInfo)
    except Exception as exc:
        metadata["gps_error"] = str(exc)
        return

    if not gps_ifd:
        metadata["gps"] = None
        return

    gps_named = {
        GPS_TAG_NAMES.get(tag_id, str(tag_id)): _serialize_exif_value(value)
        for tag_id, value in gps_ifd.items()
    }

    metadata["gps"] = gps_named

    metadata["gps_latitude"] = _dms_to_decimal(
        gps_ifd.get(GPS_TAG_IDS.get("GPSLatitude")),
        _serialize_exif_value(gps_ifd.get(GPS_TAG_IDS.get("GPSLatitudeRef"))),
    )

    metadata["gps_longitude"] = _dms_to_decimal(
        gps_ifd.get(GPS_TAG_IDS.get("GPSLongitude")),
        _serialize_exif_value(gps_ifd.get(GPS_TAG_IDS.get("GPSLongitudeRef"))),
    )

    metadata["gps_altitude"] = _serialize_exif_value(
        gps_ifd.get(GPS_TAG_IDS.get("GPSAltitude"))
    )


def extract_image_metadata(content: bytes, upload: UploadFile) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "filename": upload.filename,
        "content_type": upload.content_type,
        "file_size_bytes": len(content),
    }

    try:
        img = Image.open(io.BytesIO(content))
    except UnidentifiedImageError as exc:
        suffix = (upload.filename or "").rsplit(".", 1)[-1].lower()
        if suffix in {"heic", "heif"}:
            raise ValueError(
                "HEIC/HEIF images require pillow-heif. Run: pip install pillow-heif"
            ) from exc
        raise ValueError(
            f"Unsupported or unrecognized image format{f' (.{suffix})' if suffix else ''}"
        ) from exc

    with img:
        metadata["image_format"] = img.format
        metadata["image_type"] = upload.content_type or (
            f"image/{img.format.lower()}" if img.format else None
        )
        metadata["width"] = img.width
        metadata["height"] = img.height
        metadata["mode"] = img.mode
        metadata["is_animated"] = getattr(img, "is_animated", False)
        metadata["n_frames"] = getattr(img, "n_frames", 1)

        dpi = img.info.get("dpi")
        if dpi:
            metadata["dpi"] = {
                "x": _serialize_exif_value(dpi[0]),
                "y": _serialize_exif_value(dpi[1]) if len(dpi) > 1 else None,
            }

        try:
            _attach_exif_metadata(metadata, img)
        except Exception as exc:
            metadata["has_exif"] = False
            metadata["exif_error"] = str(exc)

    return metadata
