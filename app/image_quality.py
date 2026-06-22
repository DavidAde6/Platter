from __future__ import annotations

import io
from typing import Any

import cv2
import numpy as np
from PIL import Image

try:
    import pillow_heif

    pillow_heif.register_heif_opener()
except ImportError:
    pass


# Thresholds are intentionally lenient: we want to flag genuinely bad photos
# (smeared, near-black, blown-out, tiny) while letting normal phone snaps --
# including dim restaurant lighting -- pass without complaint.

# Laplacian variance below this reads as out-of-focus / motion blur.
BLUR_LAPLACIAN_MIN = 60.0

# Mean grayscale intensity (0-255) outside this band is too dark / too bright.
BRIGHTNESS_DARK_MAX = 35.0
BRIGHTNESS_BRIGHT_MIN = 225.0

# A pixel at/above NEAR_WHITE is "blown out"; at/below NEAR_BLACK is "crushed".
NEAR_WHITE_LEVEL = 250
NEAR_BLACK_LEVEL = 5

# Flag only when a large share of the frame is clipped.
OVEREXPOSURE_PCT_MAX = 50.0
UNDEREXPOSURE_PCT_MAX = 50.0

# Shortest side (px) below this is too low-resolution to analyze reliably.
RESOLUTION_MIN_SIDE = 200


def _grayscale_array(content: bytes) -> tuple[np.ndarray, int, int]:
    """Decode image bytes to a grayscale uint8 array plus its (width, height).

    Uses PIL for decoding so HEIC/HEIF and other Pillow-supported formats work,
    then hands the array to OpenCV. The first frame is used for animated images.
    """
    with Image.open(io.BytesIO(content)) as img:
        width, height = img.size
        gray = np.asarray(img.convert("L"), dtype=np.uint8)
    return gray, width, height


def analyze_image_quality(content: bytes) -> dict[str, Any]:
    """Compute per-check image-quality signals for the detected_issues JSONB.

    Returns a dict shaped like:
        {
          "blur":          {"laplacian_variance": float, "issue": bool},
          "brightness":    {"mean_intensity": float, "issue": bool},
          "overexposure":  {"near_white_pct": float, "issue": bool},
          "underexposure": {"near_black_pct": float, "issue": bool},
          "resolution":    {"width": int, "height": int, "issue": bool},
          "has_issues":    bool,
        }

    Analysis failures are reported in the payload rather than raised, so a bad
    decode never aborts the surrounding upload transaction.
    """
    try:
        gray, width, height = _grayscale_array(content)
    except Exception as exc:
        return {"analysis_error": str(exc), "has_issues": False}

    laplacian_variance = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    mean_intensity = float(gray.mean())
    total = gray.size or 1
    near_white_pct = float(np.count_nonzero(gray >= NEAR_WHITE_LEVEL) / total * 100.0)
    near_black_pct = float(np.count_nonzero(gray <= NEAR_BLACK_LEVEL) / total * 100.0)

    checks = {
        "blur": {
            "laplacian_variance": round(laplacian_variance, 2),
            "issue": laplacian_variance < BLUR_LAPLACIAN_MIN,
        },
        "brightness": {
            "mean_intensity": round(mean_intensity, 2),
            "issue": mean_intensity < BRIGHTNESS_DARK_MAX
            or mean_intensity > BRIGHTNESS_BRIGHT_MIN,
        },
        "overexposure": {
            "near_white_pct": round(near_white_pct, 2),
            "issue": near_white_pct > OVEREXPOSURE_PCT_MAX,
        },
        "underexposure": {
            "near_black_pct": round(near_black_pct, 2),
            "issue": near_black_pct > UNDEREXPOSURE_PCT_MAX,
        },
        "resolution": {
            "width": int(width),
            "height": int(height),
            "issue": min(width, height) < RESOLUTION_MIN_SIDE,
        },
    }

    checks["has_issues"] = any(c["issue"] for c in checks.values())
    return checks
