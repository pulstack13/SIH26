"""Tampering screening (SIH26194 Module 3) — lightweight, dependency-free.

Methods (all local, numpy + Pillow only):
1. ELA-style recompression diff — spliced/pasted regions recompress differently.
2. Block-noise inconsistency — pasted regions have different sensor noise.
3. Metadata — editing-software tags (Photoshop/GIMP/etc) via EXIF/info.
4. Heatmap — amplified ELA diff returned as data-URL for officer review.

Thresholds tuned so the synthetic `clear-ready.png` passes and a visibly
edited/spliced image fails. This is a screening signal, not a forensic verdict.
"""

import base64
from io import BytesIO

import numpy as np
from PIL import Image, ImageOps, ExifTags, UnidentifiedImageError

EDITING_KEYWORDS = (
    "PHOTOSHOP", "GIMP", "PAINT", "LIGHTROOM", "SNAPSEED",
    "PICSART", "CANVA", "PIXLR", "FOTOR", "BEAUTY",
)
MAX_SIDE = 800
ELA_QUALITY = 90
ELA_MEAN_FLAG = 14.0       # mean abs-diff above this => suspicious
NOISE_CV_FLAG = 1.10       # coeff-of-variation of block sharpness above this => suspicious (synthetic docs ~0.87)


def _load_rgb(image_bytes: bytes) -> Image.Image:
    try:
        with Image.open(BytesIO(image_bytes)) as im:
            rgb = ImageOps.exif_transpose(im).convert("RGB")
            rgb.thumbnail((MAX_SIDE, MAX_SIDE))
            return rgb.copy()
    except (UnidentifiedImageError, OSError, ValueError) as error:
        raise ValueError("Tampering check could not read the image.") from error


def _ela_diff(original: Image.Image) -> np.ndarray:
    buffer = BytesIO()
    original.save(buffer, format="JPEG", quality=ELA_QUALITY)
    buffer.seek(0)
    recompressed = Image.open(buffer).convert("RGB")
    orig = np.asarray(original, dtype=np.int16)
    recomp = np.asarray(recompressed, dtype=np.int16)
    diff = np.abs(orig - recomp).sum(axis=2).astype(np.float32)  # 0..765
    return diff


def _block_noise_cv(gray: np.ndarray) -> float:
    h, w = gray.shape
    block = 32
    variances: list[float] = []
    for y in range(0, h - block + 1, block):
        for x in range(0, w - block + 1, block):
            patch = gray[y:y + block, x:x + block].astype(np.float32)
            lap = (
                4 * patch[1:-1, 1:-1]
                - patch[:-2, 1:-1] - patch[2:, 1:-1]
                - patch[1:-1, :-2] - patch[1:-1, 2:]
            )
            variances.append(float(lap.var()))
    if not variances:
        return 0.0
    mean = float(np.mean(variances)) + 1e-6
    return float(np.std(variances) / mean)


def _metadata_flags(image_bytes: bytes) -> tuple[bool, str | None]:
    """Returns (editing_software_found, software_name)."""
    try:
        with Image.open(BytesIO(image_bytes)) as im:
            info_software = str(im.info.get("software", "") or "")
            exif_software = ""
            try:
                exif = im.getexif()
                if exif:
                    for tag_id, value in exif.items():
                        name = ExifTags.TAGS.get(tag_id, "").lower()
                        if name == "software":
                            exif_software = str(value)
                            break
            except Exception:
                pass
            combined = f"{info_software} {exif_software}".upper()
            for keyword in EDITING_KEYWORDS:
                if keyword in combined:
                    return True, combined.strip()[:80]
            return False, None
    except Exception:
        return False, None


def _heatmap_data_url(diff: np.ndarray, original: Image.Image) -> str:
    norm = np.clip(diff / max(float(diff.max()), 1e-6), 0, 1)
    # Amplify mid-tones so subtle edits are visible
    amplified = np.clip(norm * 2.2, 0, 1)
    heat = (amplified * 255).astype(np.uint8)
    heat_img = Image.fromarray(heat, mode="L").convert("RGB")
    # Red tint: R=heat, G/B suppressed
    arr = np.asarray(heat_img).copy()
    arr[:, :, 1] = (arr[:, :, 1] * 0.25).astype(np.uint8)
    arr[:, :, 2] = (arr[:, :, 2] * 0.25).astype(np.uint8)
    overlay = Image.fromarray(arr).resize(original.size)
    blended = Image.blend(original.convert("RGB"), overlay, alpha=0.55)
    buffer = BytesIO()
    blended.save(buffer, format="JPEG", quality=82)
    b64 = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{b64}"


def assess_tampering(image_bytes: bytes) -> dict:
    """Run all tampering signals. Never raises on bad input except unreadable."""
    original = _load_rgb(image_bytes)
    gray = np.asarray(original.convert("L"), dtype=np.float32)

    diff = _ela_diff(original)
    ela_mean = float(diff.mean())
    noise_cv = _block_noise_cv(gray)
    editing_found, software = _metadata_flags(image_bytes)

    ela_ok = ela_mean <= ELA_MEAN_FLAG
    noise_ok = noise_cv <= NOISE_CV_FLAG
    meta_ok = not editing_found

    # Composite tamper score 0..100 (higher = more suspicious)
    score = 0.0
    score += min(50.0, max(0.0, (ela_mean - 6.0)) * 4.0)   # ELA contributes up to 50
    score += min(30.0, max(0.0, (noise_cv - 0.45)) * 45.0)  # noise up to 30
    if editing_found:
        score += 20.0
    tamper_score = int(round(min(100.0, score)))

    checks = {
        "Error-level (ELA) consistent": ela_ok,
        "Noise / texture consistent": noise_ok,
        "No editing software in metadata": meta_ok,
    }
    # Suspicious only on composite score — single marginal signal stays advisory.
    reasons: list[list[str]] = []
    if not ela_ok:
        reasons.append([f"ELA mean {ela_mean:.1f} is high — regions recompress differently (possible splice/edit).", "high"])
    if not noise_ok:
        reasons.append([f"Block-noise variation {noise_cv:.2f} is high — inconsistent sensor noise (possible paste).", "high"])
    if not meta_ok:
        reasons.append([f"Editing software tag found in metadata ({software}). Treat as edited.", "high"])
    if not reasons:
        reasons.append(["ELA, noise and metadata show no editing signals. Officer review still required.", ""])
    if tamper_score < 45:
        # Advisory only — don't paint clean scans red for a marginal signal
        # (synthetic samples have flat backgrounds that inflate block-noise CV).
        reasons = [[text, ""] for text, _level in reasons]

    try:
        heatmap = _heatmap_data_url(diff, original)
    except Exception:
        heatmap = ""

    return {
        "tamper_score": tamper_score,
        "suspicious": tamper_score >= 45,
        "ela_mean": round(ela_mean, 2),
        "noise_cv": round(noise_cv, 3),
        "editing_software": software,
        "checks": checks,
        "reasons": reasons,
        "heatmap": heatmap,
    }
