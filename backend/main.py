"""FastAPI entry point for the GARUDA-ID prototype."""

from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from dotenv import load_dotenv

from backend.services.audit import get_blockchain_status, record_audit
from backend.services.mrz import find_td3_mrz, parse_td3_mrz
from backend.services.ocr import extract_text
from backend.services.quality import assess_quality

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIR = PROJECT_ROOT / "frontend"
# Reload blockchain connection settings whenever the development API restarts.
load_dotenv(PROJECT_ROOT / ".env")
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
ALLOWED_MEDIA_TYPES = {"image/jpeg", "image/png", "image/webp"}

app = FastAPI(title="GARUDA-ID API", version="0.1.0")


class AuditRequest(BaseModel):
    report_id: str
    status: str
    checks: list[list[object]]


def validation_score(
    quality_checks: list[list[object]],
    mrz_detected: bool | None = None,
    mrz_checks: list[list[object]] | None = None,
) -> int:
    """Score quality (40), MRZ detection (20), and MRZ validation (40)."""
    quality_points = round(40 * sum(bool(passed) for _, passed in quality_checks) / len(quality_checks))
    if mrz_detected is None or not mrz_detected:
        return quality_points
    mrz_checks = mrz_checks or []
    validation_points = round(40 * sum(bool(passed) for _, passed in mrz_checks) / len(mrz_checks)) if mrz_checks else 0
    return quality_points + 20 + validation_points


@app.post("/api/analyze-document")
async def analyze_document(file: UploadFile = File(...)) -> dict:
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
            "summary": "Capture is clear, but MRZ validation is not available on this backend.",
            "report_id": f"GARUDA-{uuid4().hex[:8].upper()}",
            "fields": {"Image size": f"{quality['metrics']['width']} × {quality['metrics']['height']}px"},
            "checks": quality_checks + [["MRZ OCR service available", False]],
            "reasons": [[str(error), "high"]],
        }

    mrz_lines = find_td3_mrz(ocr_lines)
    if mrz_lines is None:
        return {
            "risk": "RECAPTURE",
            "score": validation_score(quality_checks, False),
            "summary": "Capture is clear, but a valid passport MRZ was not found.",
            "report_id": f"GARUDA-{uuid4().hex[:8].upper()}",
            "fields": {"Image size": f"{quality['metrics']['width']} × {quality['metrics']['height']}px"},
            "checks": quality_checks + [["TD3 passport MRZ detected", False]],
            "reasons": [["Open the passport biodata page and keep both 44-character MRZ lines fully visible.", "high"]],
        }

    mrz = parse_td3_mrz(*mrz_lines)
    mrz_checks = [[label, passed] for label, passed in mrz["checks"].items()]
    failed_checks = [label for label, passed in mrz_checks if not passed]
    if failed_checks:
        return {
            "risk": "RECAPTURE",
            "score": validation_score(quality_checks, True, mrz_checks),
            "summary": "The MRZ was detected, but one or more validation checks failed.",
            "report_id": f"GARUDA-{uuid4().hex[:8].upper()}",
            "fields": {**mrz["fields"], "Image size": f"{quality['metrics']['width']} × {quality['metrics']['height']}px"},
            "checks": quality_checks + [["TD3 passport MRZ detected", True]] + mrz_checks,
            "reasons": [[f"{label} failed. Recapture the biodata page without glare, cropping, or blur.", "high"] for label in failed_checks],
        }

    return {
        "risk": "READY",
        "score": validation_score(quality_checks, True, mrz_checks),
        "summary": "Capture quality and MRZ validation passed. Ready for officer review.",
        "report_id": f"GARUDA-{uuid4().hex[:8].upper()}",
        "fields": {**mrz["fields"], "Image size": f"{quality['metrics']['width']} × {quality['metrics']['height']}px"},
        "checks": quality_checks + [["TD3 passport MRZ detected", True]] + mrz_checks,
        "reasons": [["Capture quality and all ICAO MRZ check digits passed. An officer must still review the document.", ""]],
    }


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
