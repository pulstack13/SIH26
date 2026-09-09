"""Fast, explainable image-quality checks for the capture gate."""

from io import BytesIO

import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

MIN_SHORT_EDGE = 500
MIN_SHARPNESS = 55.0
MIN_BRIGHTNESS = 45.0
MAX_BRIGHTNESS = 220.0
MIN_CONTRAST = 20.0


def assess_quality(image_bytes: bytes) -> dict:
    """Return explainable capture checks without storing the uploaded image."""
    try:
        with Image.open(BytesIO(image_bytes)) as uploaded:
            image = ImageOps.exif_transpose(uploaded).convert("L")
            width, height = image.size
            grayscale = np.asarray(image, dtype=np.float32)
    except (UnidentifiedImageError, OSError, ValueError) as error:
        raise ValueError("The uploaded image could not be read.") from error

    # Variance of the four-neighbour Laplacian is a lightweight focus measure.
    # Ignore the outermost pixels so edge padding does not inflate the score.
    center = grayscale[1:-1, 1:-1]
    if center.size:
        laplacian = (
            4 * center
            - grayscale[:-2, 1:-1]
            - grayscale[2:, 1:-1]
            - grayscale[1:-1, :-2]
            - grayscale[1:-1, 2:]
        )
        sharpness = float(laplacian.var())
    else:
        sharpness = 0.0
    brightness = float(grayscale.mean())
    contrast = float(grayscale.std())

    checks = {
        "Minimum capture resolution": min(width, height) >= MIN_SHORT_EDGE,
        "Image sharpness": sharpness >= MIN_SHARPNESS,
        "Image exposure": MIN_BRIGHTNESS <= brightness <= MAX_BRIGHTNESS,
        "Image contrast": contrast >= MIN_CONTRAST,
    }
    reasons: list[str] = []
    if not checks["Minimum capture resolution"]:
        reasons.append(f"Image is too small ({width} × {height}px). Use an image with a shortest side of at least {MIN_SHORT_EDGE}px.")
    if not checks["Image sharpness"]:
        reasons.append("Image appears blurry. Hold the document steady and capture it again.")
    if brightness < MIN_BRIGHTNESS:
        reasons.append("Image is too dark. Improve lighting and capture it again.")
    elif brightness > MAX_BRIGHTNESS:
        reasons.append("Image is overexposed or has strong glare. Avoid reflections and capture it again.")
    if not checks["Image contrast"]:
        reasons.append("Image contrast is too low for reliable screening. Use a clearer, evenly lit capture.")

    return {
        "acceptable": all(checks.values()),
        "checks": checks,
        "reasons": reasons,
        "metrics": {"width": width, "height": height, "sharpness": round(sharpness, 1)},
    }
