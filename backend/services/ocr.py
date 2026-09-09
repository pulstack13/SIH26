"""PaddleOCR adapter. OCR models load once, on the first request."""

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

_ocr_engine: Any | None = None


def _get_ocr_engine() -> Any:
    global _ocr_engine
    if _ocr_engine is not None:
        return _ocr_engine
    try:
        from paddleocr import PaddleOCR
    except ImportError as error:
        raise RuntimeError(
            "MRZ OCR is not installed on this backend. Install PaddleOCR and PaddlePaddle, then restart the API."
        ) from error
    _ocr_engine = PaddleOCR(
        lang="en",
        device="cpu",
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False,
    )
    return _ocr_engine


def _result_data(result: Any) -> dict[str, Any]:
    payload = getattr(result, "json", result)
    if callable(payload):
        payload = payload()
    if isinstance(payload, str):
        payload = json.loads(payload)
    return payload.get("res", payload) if isinstance(payload, dict) else {}


def _extract_with_windows_ocr(image_path: Path) -> list[str]:
    script_path = Path(__file__).with_name("windows_ocr.ps1")
    startup_info = None
    creation_flags = 0
    if os.name == "nt":
        startup_info = subprocess.STARTUPINFO()
        startup_info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        creation_flags = subprocess.CREATE_NO_WINDOW
    result = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script_path),
            "-ImagePath",
            str(image_path),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=45,
        startupinfo=startup_info,
        creationflags=creation_flags,
        check=False,
    )
    if result.returncode != 0:
        message = result.stderr.strip().splitlines()[0] if result.stderr.strip() else "Windows OCR failed."
        raise RuntimeError(message)
    try:
        payload = json.loads(result.stdout.strip())
    except json.JSONDecodeError as error:
        raise RuntimeError("Windows OCR returned an unreadable response.") from error
    if isinstance(payload, str):
        return [payload]
    return [str(line) for line in payload if line]


def extract_text(image_bytes: bytes, suffix: str) -> list[str]:
    """Extract text locally and delete the temporary image immediately."""
    with tempfile.TemporaryDirectory(prefix="garuda-id-") as temporary_directory:
        image_path = Path(temporary_directory) / f"upload{suffix}"
        image_path.write_bytes(image_bytes)
        try:
            engine = _get_ocr_engine()
        except RuntimeError as paddle_error:
            if os.name != "nt":
                raise paddle_error
            try:
                return _extract_with_windows_ocr(image_path)
            except (OSError, subprocess.SubprocessError, RuntimeError) as windows_error:
                raise RuntimeError(
                    "No local MRZ OCR engine is available. Install PaddleOCR and PaddlePaddle, then restart the API."
                ) from windows_error

        lines: list[str] = []
        for result in engine.predict(str(image_path)):
            lines.extend(str(text) for text in _result_data(result).get("rec_texts", []) if text)
        return lines
