"""FastAPI entry point for the GARUDA-ID prototype."""

from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from dotenv import load_dotenv

from backend.services.audit import get_blockchain_status, record_audit
from backend.services.face import verify_pair
from backend.services.tampering import assess_tampering
from backend.services.indian_ids import (
    parse_driving_licence,
    parse_national_id,
    parse_permit,
    parse_visa,
)
from backend.services.mrz import find_td3_mrz, parse_td3_mrz
from backend.services.ocr import extract_text
from backend.services.quality import assess_quality
from backend.services.watchlist import check_watchlist, extract_identifiers, record_seen, watchlist_stats

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIR = PROJECT_ROOT / "frontend"
# Reload blockchain connection settings whenever the development API restarts.
load_dotenv(PROJECT_ROOT / ".env")
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
ALLOWED_MEDIA_TYPES = {"image/jpeg", "image/png", "image/webp"}

app = FastAPI(title="GARUDA-ID API", version="0.1.0")
# Split hosting (e.g. frontend on Netlify, API on Render) needs CORS.
# Prototype allows all origins; restrict ALLOWED_ORIGINS in production.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class AuditRequest(BaseModel):
    report_id: str
    status: str
    checks: list[list[object]]


def validation_score(
    quality_checks: list[list[object]],
    doc_detected: bool | None = None,
    doc_checks: list[list[object]] | None = None,
) -> int:
    """Score quality (40), ID detection (20), and format validation (40)."""
    quality_points = round(40 * sum(bool(passed) for _, passed in quality_checks) / len(quality_checks))
    if doc_detected is None or not doc_detected:
        return quality_points
    doc_checks = doc_checks or []
    validation_points = round(40 * sum(bool(passed) for _, passed in doc_checks) / len(doc_checks)) if doc_checks else 0
    return quality_points + 20 + validation_points


DOC_LABELS = {
    "passport": "Passport (TD3, ICAO 9303)",
    "visa": "Visa",
    "national_id": "National ID (Aadhaar / PAN / EPIC)",
    "driving_licence": "Driving Licence (Parivahan)",
    "permit": "Permit",
}

DOC_PARSERS = {
    "visa": parse_visa,
    "national_id": parse_national_id,
    "driving_licence": parse_driving_licence,
    "permit": parse_permit,
}


def _with_watchlist(response: dict, identifiers: dict[str, str], name: str = "", dob: str = "") -> dict:
    """Merge blacklist/expired/duplicate checks; blacklist hit forces RECAPTURE."""
    if not identifiers:
        response["watchlist"] = {"hit": False, "checks": {}, "matched": []}
        return response
    verdict = check_watchlist(identifiers, name=name, dob=dob)
    watch_checks = [[label, passed] for label, passed in verdict["checks"].items()]
    response["checks"] = response.get("checks", []) + watch_checks
    response["reasons"] = response.get("reasons", []) + verdict["reasons"]
    response["watchlist"] = {"hit": verdict["hit"], "checks": verdict["checks"], "matched": verdict["matched"]}
    record_seen(identifiers, name=name, dob=dob, report_id=response.get("report_id", ""))
    if verdict["hit"] and response.get("risk") == "READY":
        response["risk"] = "RECAPTURE"
        response["summary"] = "ID matches blacklist / expired / duplicate-identity list. Escalate to officer."
    return response


def _generic_doc_response(quality: dict, quality_checks: list, parsed: dict, doc_key: str, tampering: dict | None = None, ocr_lines: list[str] | None = None) -> dict:
    doc_label = DOC_LABELS.get(doc_key, doc_key)
    doc_checks = [[label, passed] for label, passed in parsed["checks"].items()]
    tamper_checks = [[label, passed] for label, passed in (tampering or {}).get("checks", {}).items()]
    failed = [label for label, passed in doc_checks if not passed]
    size_field = f"{quality['metrics']['width']} × {quality['metrics']['height']}px"
    fields = {**parsed["fields"], "Document type": doc_label, "Image size": size_field}
    # Core gate: a real ID number must exist. Aux fields alone (dates, pincodes
    # from random screenshots) must NOT count as detection.
    detected = bool(parsed.get("id_found", bool(parsed["fields"])))
    tampering_block = tampering or {}
    if not detected:
        return {
            "risk": "RECAPTURE",
            "score": validation_score(quality_checks, False),
            "summary": f"Capture is clear, but no {doc_label} number was found.",
            "report_id": f"GARUDA-{uuid4().hex[:8].upper()}",
            "fields": {"Document type": doc_label, "Image size": size_field},
            "checks": quality_checks + [[f"{doc_label} number detected", False]] + tamper_checks,
            "reasons": [[f"Keep the {doc_label} number fully visible without glare or cropping.", "high"]],
            "tampering": tampering_block,
        }
    # Tampering veto: suspicious tampering forces RECAPTURE even if format passes.
    tamper_veto = bool(tampering_block.get("suspicious")) and int(tampering_block.get("tamper_score", 0)) >= 45
    if failed or tamper_veto:
        reasons = [[f"{label} failed. Recapture without glare/crop/blur.", "high"] for label in failed]
        reasons += tampering_block.get("reasons", [])
        return _with_watchlist({
            "risk": "RECAPTURE",
            "score": validation_score(quality_checks, True, doc_checks + tamper_checks),
            "summary": f"{doc_label} {'shows tampering signals' if tamper_veto else 'found, but one or more format checks failed'}.",
            "report_id": f"GARUDA-{uuid4().hex[:8].upper()}",
            "fields": fields,
            "checks": quality_checks + [[f"{doc_label} number detected", True]] + doc_checks + tamper_checks,
            "reasons": reasons,
            "tampering": tampering_block,
        }, extract_identifiers(doc_key, ocr_lines or []), name=str(parsed["fields"].get("Name", "")), dob=str(parsed["fields"].get("Date of birth", "")))
    return _with_watchlist({
        "risk": "READY",
        "score": validation_score(quality_checks, True, doc_checks + tamper_checks),
        "summary": f"{doc_label} format checks passed. Ready for officer review.",
        "report_id": f"GARUDA-{uuid4().hex[:8].upper()}",
        "fields": fields,
        "checks": quality_checks + [[f"{doc_label} number detected", True]] + doc_checks + tamper_checks,
        "reasons": [[f"{doc_label} passed UIDAI/Parivahan/ITD/ECI structural checks. Officer review still required.", ""]] + tampering_block.get("reasons", []),
        "tampering": tampering_block,
    }, extract_identifiers(doc_key, ocr_lines or []), name=str(parsed["fields"].get("Name", "")), dob=str(parsed["fields"].get("Date of birth", "")))


@app.post("/api/analyze-document")
async def analyze_document(
    file: UploadFile = File(...),
    document_type: str = Form("passport"),
) -> dict:
    doc_key = (document_type or "passport").strip().lower()
    if doc_key not in DOC_LABELS:
        doc_key = "passport"
    if file.content_type not in ALLOWED_MEDIA_TYPES:
        raise HTTPException(status_code=415, detail="Upload a PNG, JPG, or WEBP image.")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Images must be 10 MB or smaller.")

    try:
        quality = await run_in_threadpool(assess_quality, content)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    quality_checks = [[label, passed] for label, passed in quality["checks"].items()]
    if not quality["acceptable"]:
        return {
            "risk": "RECAPTURE",
            "score": validation_score(quality_checks),
            "summary": "Capture quality is insufficient for reliable document screening.",
            "report_id": f"GARUDA-{uuid4().hex[:8].upper()}",
            "fields": {"Image size": f"{quality['metrics']['width']} × {quality['metrics']['height']}px"},
            "checks": quality_checks,
            "reasons": [[reason, "high"] for reason in quality["reasons"]],
        }

    try:
        ocr_lines = await run_in_threadpool(extract_text, content, Path(file.filename or "upload.png").suffix or ".png")
    except RuntimeError as error:
        return {
            "risk": "RECAPTURE",
            "score": validation_score(quality_checks, False),
            "summary": "Capture is clear, but OCR validation is not available on this backend.",
            "report_id": f"GARUDA-{uuid4().hex[:8].upper()}",
            "fields": {"Document type": DOC_LABELS.get(doc_key, doc_key), "Image size": f"{quality['metrics']['width']} × {quality['metrics']['height']}px"},
            "checks": quality_checks + [["OCR service available", False]],
            "reasons": [[str(error), "high"]],
        }

    # Module 3: tampering signals run for every document (numpy+Pillow only).
    try:
        tampering = await run_in_threadpool(assess_tampering, content)
    except ValueError:
        tampering = {"tamper_score": 0, "suspicious": False, "checks": {}, "reasons": [], "heatmap": ""}

    # Non-passport docs: India validators (Module 1+2).
    if doc_key in DOC_PARSERS:
        parsed = DOC_PARSERS[doc_key](ocr_lines)
        return _generic_doc_response(quality, quality_checks, parsed, doc_key, tampering, ocr_lines)

    mrz_lines = find_td3_mrz(ocr_lines)
    if mrz_lines is None:
        tamper_checks = [[l, p] for l, p in tampering.get("checks", {}).items()]
        return {
            "risk": "RECAPTURE",
            "score": validation_score(quality_checks, False),
            "summary": "Capture is clear, but a valid passport MRZ was not found.",
            "report_id": f"GARUDA-{uuid4().hex[:8].upper()}",
            "fields": {"Image size": f"{quality['metrics']['width']} × {quality['metrics']['height']}px"},
            "checks": quality_checks + [["TD3 passport MRZ detected", False]] + tamper_checks,
            "reasons": [["Open the passport biodata page and keep both 44-character MRZ lines fully visible.", "high"]] + tampering.get("reasons", []),
            "tampering": tampering,
            "watchlist": {"hit": False, "checks": {}, "matched": []},
        }


    mrz = parse_td3_mrz(*mrz_lines)
    mrz_checks = [[label, passed] for label, passed in mrz["checks"].items()]
    tamper_checks = [[label, passed] for label, passed in tampering.get("checks", {}).items()]
    failed_checks = [label for label, passed in mrz_checks if not passed]
    tamper_veto = bool(tampering.get("suspicious")) and int(tampering.get("tamper_score", 0)) >= 45
    passport_ids = extract_identifiers("passport", ocr_lines, mrz_second=mrz_lines[1])
    passport_name = str(mrz["fields"].get("Name", ""))
    passport_dob = str(mrz["fields"].get("Date of birth", ""))
    if failed_checks or tamper_veto:
        return _with_watchlist({
            "risk": "RECAPTURE",
            "score": validation_score(quality_checks, True, mrz_checks + tamper_checks),
            "summary": "Passport shows tampering signals." if tamper_veto else "The MRZ was detected, but one or more validation checks failed.",
            "report_id": f"GARUDA-{uuid4().hex[:8].upper()}",
            "fields": {**mrz["fields"], "Image size": f"{quality['metrics']['width']} × {quality['metrics']['height']}px"},
            "checks": quality_checks + [["TD3 passport MRZ detected", True]] + mrz_checks + tamper_checks,
            "reasons": [[f"{label} failed. Recapture the biodata page without glare, cropping, or blur.", "high"] for label in failed_checks] + tampering.get("reasons", []),
            "tampering": tampering,
        }, passport_ids, name=passport_name, dob=passport_dob)

    return _with_watchlist({
        "risk": "READY",
        "score": validation_score(quality_checks, True, mrz_checks + tamper_checks),
        "summary": "Capture quality and MRZ validation passed. Ready for officer review.",
        "report_id": f"GARUDA-{uuid4().hex[:8].upper()}",
        "fields": {**mrz["fields"], "Image size": f"{quality['metrics']['width']} × {quality['metrics']['height']}px"},
        "checks": quality_checks + [["TD3 passport MRZ detected", True]] + mrz_checks + tamper_checks,
        "reasons": [["Capture quality and all ICAO MRZ check digits passed. An officer must still review the document.", ""]] + tampering.get("reasons", []),
        "tampering": tampering,
    }, passport_ids, name=passport_name, dob=passport_dob)


@app.get("/api/watchlist-status")
async def watchlist_status() -> dict:
    """Demo DB health: counts only, never full ID numbers."""
    return await run_in_threadpool(watchlist_stats)


@app.get("/api/face-status")
async def face_status() -> dict:
    """Which face engines are installed (no images involved)."""
    def _check() -> dict:
        engines = {"retinaface": False, "insightface_arcface": False, "opencv_haar": False}
        try:
            import retinaface  # noqa: F401
            engines["retinaface"] = True
        except Exception:
            pass
        try:
            import insightface  # noqa: F401
            engines["insightface_arcface"] = True
        except Exception:
            pass
        try:
            import cv2  # noqa: F401
            engines["opencv_haar"] = True
        except Exception:
            pass
        active = "arcface" if engines["insightface_arcface"] else "fallback-correlation"
        detector = "retinaface" if engines["retinaface"] else ("haar" if engines["opencv_haar"] else "fallback-skin")
        return {"engines": engines, "active_matcher": active, "active_detector": detector,
                "note": "Install retinaface + insightface + onnxruntime for production biometrics."}
    return await run_in_threadpool(_check)


@app.post("/api/verify-face")
async def verify_face(
    id_image: UploadFile = File(...),
    selfie: UploadFile = File(...),
) -> dict:
    """Module 4: document portrait vs live selfie + passive liveness + morph screen."""
    for upload in (id_image, selfie):
        if upload.content_type not in ALLOWED_MEDIA_TYPES:
            raise HTTPException(status_code=415, detail="Upload PNG, JPG, or WEBP for both ID and selfie.")
    id_bytes = await id_image.read()
    selfie_bytes = await selfie.read()
    if not id_bytes or not selfie_bytes:
        raise HTTPException(status_code=400, detail="Both ID portrait and selfie are required.")
    if len(id_bytes) > MAX_UPLOAD_BYTES or len(selfie_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Images must be 10 MB or smaller.")
    try:
        return await run_in_threadpool(verify_pair, id_bytes, selfie_bytes)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.post("/api/record-audit")
async def create_audit_record(request: AuditRequest) -> dict:
    if request.status not in {"READY", "RECAPTURE"}:
        raise HTTPException(status_code=400, detail="Only READY or RECAPTURE quality reports can be audited.")
    return await run_in_threadpool(record_audit, request.report_id, request.status, request.checks)


@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/blockchain-status")
async def blockchain_status() -> dict:
    return await run_in_threadpool(get_blockchain_status)


@app.get("/")
async def frontend() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/favicon.ico", include_in_schema=False)
async def legacy_favicon() -> RedirectResponse:
    return RedirectResponse(url="/favicon.svg")


app.mount("/", StaticFiles(directory=FRONTEND_DIR), name="frontend")
