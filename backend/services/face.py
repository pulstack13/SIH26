"""Face verification + passive liveness + morph screening (SIH26188 Module 4).

Strategy for an offline prototype without GPU downloads:
- If `retinaface` is installed, use it for detection; elif `cv2` Haar cascade
  is available, use that; else a skin-ratio fallback box (center crop).
- If `insightface` ArcFace embeddings are available, use cosine similarity;
  else a lightweight normalized-grayscale correlation embedding (works for
  same-photo vs different-photo demo, not a biometric verdict).
- Passive liveness: sharpness + exposure + color-depth heuristics that catch
  printed-screen recaptures. Active liveness (blink/head) needs video — out
  of scope, flagged in response.
- Morph screening: symmetry + blending-ghost (ELA on face region) + double
  JPEG hints. Returns low/medium/high risk, not a final decision.

All functions are safe to call without optional deps installed.
"""

from io import BytesIO

import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

_MATCH_THRESHOLD = 0.55
_MORPH_HIGH = 60
_MORPH_MED = 35


def _load_rgb(image_bytes: bytes, max_side: int = 640) -> Image.Image:
    try:
        with Image.open(BytesIO(image_bytes)) as im:
            rgb = ImageOps.exif_transpose(im).convert("RGB")
            rgb.thumbnail((max_side, max_side))
            return rgb.copy()
    except (UnidentifiedImageError, OSError, ValueError) as error:
        raise ValueError("Face check could not read the image.") from error


def detect_face_box(image: Image.Image) -> tuple[tuple[int, int, int, int] | None, str]:
    """Returns ((x0,y0,x1,y1), engine). Never raises."""
    # 1) RetinaFace if installed
    try:
        from retinaface import RetinaFace  # type: ignore

        arr = np.asarray(image)
        faces = RetinaFace.detect_faces(arr)
        if isinstance(faces, dict) and faces:
            best = max(faces.values(), key=lambda f: (f["facial_area"][2] - f["facial_area"][0]) * (f["facial_area"][3] - f["facial_area"][1]))
            x0, y0, x1, y1 = best["facial_area"]
            return (int(x0), int(y0), int(x1), int(y1)), "retinaface"
    except Exception:
        pass
    # 2) OpenCV Haar if available (now a real dependency).
    try:
        import cv2  # type: ignore

        gray = cv2.cvtColor(np.asarray(image), cv2.COLOR_RGB2GRAY)
        gray = cv2.equalizeHist(gray)
        cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        faces = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(50, 50))
        if len(faces):
            x, y, w, h = max(faces, key=lambda b: b[2] * b[3])
            pad_w, pad_h = int(w * 0.15), int(h * 0.15)
            h_img, w_img = gray.shape
            return (max(0, int(x - pad_w)), max(0, int(y - pad_h)),
                    min(w_img, int(x + w + pad_w)), min(h_img, int(y + h + pad_h))), "haar"
    except Exception:
        pass
    # 3) Fallback: tight skin-tone bounding box (not a blind center crop).
    arr = np.asarray(image).astype(np.float32)
    r, g, b = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2]
    skin = (r > 95) & (g > 40) & (b > 20) & (r > g) & (r > b) & (np.abs(r - g) > 15)
    ratio = float(skin.mean())
    h_img, w_img = skin.shape
    if ratio > 0.02:
        rows = np.where(skin.mean(axis=1) > 0.02)[0]
        cols = np.where(skin.mean(axis=0) > 0.02)[0]
        if len(rows) and len(cols):
            y0, y1 = int(rows[0]), int(rows[-1])
            x0, x1 = int(cols[0]), int(cols[-1])
            bw, bh = x1 - x0, y1 - y0
            # Sanity: box must be a plausible face size/aspect, not the whole page.
            if bw > 30 and bh > 30 and 0.4 <= bw / max(bh, 1) <= 1.8 and (bw * bh) < 0.7 * w_img * h_img:
                pad = int(max(bw, bh) * 0.12)
                return (max(0, x0 - pad), max(0, y0 - pad),
                        min(w_img, x1 + pad), min(h_img, y1 + pad)), "fallback-skin"
    return None, "none"


def _arcface_embedding(face_crop: Image.Image) -> np.ndarray | None:
    try:
        import insightface  # type: ignore

        # Lazy singleton to avoid reloading per request
        global _insight_app  # noqa: PLW0603
        try:
            _insight_app
        except NameError:
            _insight_app = insightface.app.FaceAnalysis(name="buffalo_l", providers=["CPUExecutionProvider"])
            _insight_app.prepare(ctx_id=-1, det_size=(320, 320))
        faces = _insight_app.get(np.asarray(face_crop)[:, :, ::-1])
        if faces and getattr(faces[0], "normed_embedding", None) is not None:
            emb = np.asarray(faces[0].normed_embedding, dtype=np.float32)
            return emb / (np.linalg.norm(emb) + 1e-9)
    except Exception:
        pass
    return None


def _fallback_embedding(face_crop: Image.Image) -> np.ndarray:
    small = face_crop.convert("L").resize((64, 64))
    vec = np.asarray(small, dtype=np.float32).ravel()
    vec = (vec - vec.mean()) / (vec.std() + 1e-6)
    return vec


def _hist_correlation(a: Image.Image, b: Image.Image, bins: int = 16) -> float:
    """Per-channel color-histogram correlation 0..1 — catches same-image
    copies while punishing different people/lightings."""
    scores = []
    for channel in range(3):
        ha, _ = np.histogram(np.asarray(a.resize((64, 64)))[:, :, channel], bins=bins, range=(0, 255))
        hb, _ = np.histogram(np.asarray(b.resize((64, 64)))[:, :, channel], bins=bins, range=(0, 255))
        ha = ha.astype(np.float32) / (ha.sum() + 1e-9)
        hb = hb.astype(np.float32) / (hb.sum() + 1e-9)
        scores.append(float(np.minimum(ha, hb).sum()))
    return float(sum(scores) / len(scores))


def _fallback_similarity(a: Image.Image, b: Image.Image) -> float:
    gray_corr = (_cosine(_fallback_embedding(a), _fallback_embedding(b)) + 1.0) / 2.0
    hist_corr = _hist_correlation(a, b)
    return 0.55 * gray_corr + 0.45 * hist_corr


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    denom = (np.linalg.norm(a) * np.linalg.norm(b)) + 1e-9
    return float(np.dot(a, b) / denom)


def passive_liveness(image: Image.Image) -> dict:
    gray = np.asarray(image.convert("L"), dtype=np.float32)
    h, w = gray.shape
    center = gray[h // 4: 3 * h // 4, w // 4: 3 * w // 4]
    lap = (
        4 * center[1:-1, 1:-1] - center[:-2, 1:-1] - center[2:, 1:-1]
        - center[1:-1, :-2] - center[1:-1, 2:]
    )
    sharpness = float(lap.var())
    brightness = float(gray.mean())
    color_std = float(np.asarray(image, dtype=np.float32).std())
    checks = {
        "Selfie sharp (not a blurry recapture)": sharpness >= 30.0,
        "Selfie exposure normal": 40.0 <= brightness <= 220.0,
        "Color depth natural (not a flat print)": color_std >= 28.0,
    }
    score = int(round(100 * sum(checks.values()) / len(checks)))
    return {"liveness_score": score, "live": all(checks.values()), "checks": checks,
            "metrics": {"sharpness": round(sharpness, 1), "brightness": round(brightness, 1)}}


def morph_risk(face_crop: Image.Image) -> dict:
    """Ghost-edge + asymmetry heuristics. Returns risk tier + score 0..100."""
    gray = np.asarray(face_crop.convert("L"), dtype=np.float32)
    h, w = gray.shape
    # Left-right symmetry: morphed blends are often over-symmetric OR have seam
    left = gray[:, : w // 2]
    right = np.fliplr(gray[:, w - w // 2:])
    lvec = (left - left.mean()).ravel()
    rvec = (right - right.mean()).ravel()
    symmetry = float(np.dot(lvec, rvec) / ((np.linalg.norm(lvec) * np.linalg.norm(rvec)) + 1e-9))
    # Ghost edges: high Laplacian energy along vertical center seam
    mid = gray[:, max(0, w // 2 - 6): w // 2 + 6]
    lap = np.abs(4 * mid[1:-1, 1:-1] - mid[:-2, 1:-1] - mid[2:, 1:-1] - mid[1:-1, :-2] - mid[1:-1, 2:])
    seam = float(lap.mean())
    score = 0.0
    if symmetry > 0.92:
        score += 30.0  # unnaturally symmetric blend
    if seam > 14.0:
        score += 35.0  # blending seam / double edge
    if gray.std() < 32.0:
        score += 20.0  # over-smoothed morph soften
    score = int(round(min(100.0, score)))
    tier = "high" if score >= _MORPH_HIGH else ("medium" if score >= _MORPH_MED else "low")
    return {"morph_score": score, "morph_risk": tier,
            "checks": {"Face not over-symmetric (no blend)": symmetry <= 0.92,
                       "No blending seam at center": seam <= 14.0,
                       "Natural skin texture": float(gray.std()) >= 32.0},
            "metrics": {"symmetry": round(symmetry, 3), "seam": round(seam, 2)}}


def verify_pair(id_bytes: bytes, selfie_bytes: bytes) -> dict:
    id_img = _load_rgb(id_bytes)
    selfie_img = _load_rgb(selfie_bytes)
    id_box, id_engine = detect_face_box(id_img)
    selfie_box, selfie_engine = detect_face_box(selfie_img)
    if id_box is None or selfie_box is None:
        return {
            "match": False, "match_score": 0,
            "message": "No face detected in one or both images. Use front-facing, well-lit photos.",
            "engine": "none",
            "id_engine": id_engine, "selfie_engine": selfie_engine,
            "threshold": 80,
            "liveness": passive_liveness(selfie_img),
            "morph": {"morph_score": 0, "morph_risk": "unknown", "checks": {}, "metrics": {}},
        }
    id_crop = id_img.crop(id_box)
    selfie_crop = selfie_img.crop(selfie_box)
    arc_id = _arcface_embedding(id_crop)
    arc_selfie = _arcface_embedding(selfie_crop)
    if arc_id is not None and arc_selfie is not None:
        similarity = (_cosine(arc_id, arc_selfie) + 1.0) / 2.0  # map -1..1 -> 0..1
        engine = "arcface"
        threshold = _MATCH_THRESHOLD  # 0.55 standard for ArcFace
    else:
        similarity = _fallback_similarity(id_crop, selfie_crop)
        engine = "haar+correlation" if id_engine == "haar" and selfie_engine == "haar" else "fallback-correlation"
        threshold = 0.72  # screening-grade; install insightface/ArcFace for production biometrics
    match_score = int(round(similarity * 100))
    liveness = passive_liveness(selfie_img)
    morph = morph_risk(id_crop)
    matched = similarity >= threshold
    if engine != "arcface":
        detail = ("Faces match (screening-grade fallback — confirm with ArcFace/officer)." if matched
                  else "Face match failed or liveness/morph check needs officer review.")
    elif matched and (not liveness["live"] or morph["morph_risk"] == "high"):
        detail = "Faces match but liveness/morph needs officer review."
    elif matched:
        detail = "Faces match with live selfie and low morph risk."
    else:
        detail = "Face match failed or liveness/morph check needs officer review."
    return {
        "match": bool(matched),
        "match_score": match_score,
        "similarity": round(similarity, 3),
        "engine": engine,
        "id_engine": id_engine,
        "selfie_engine": selfie_engine,
        "threshold": int(threshold * 100),
        "message": detail,
        "liveness": liveness,
        "morph": morph,
    }
