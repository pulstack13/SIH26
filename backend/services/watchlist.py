"""Local watchlist / blacklist + expired + duplicate-identity checks (SIH26188).

Prototype stands in for the SSB/IB database lookup:
- `backend/data/watchlist.json` — demo blacklist + expired IDs. Reloaded on
  every request so officers can edit it without restarting the API.
- `backend/data/seen_ids.json` — auto-created log of previously verified IDs
  used for the "multiple identities, same person" signal. Stores only the
  ID number + name/DOB + report + timestamp (no images).

All lookups are normalized (upper, no spaces/hyphens) and only masked
values ever appear in API responses.
"""

import json
import re
from datetime import datetime, timezone
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
WATCHLIST_PATH = DATA_DIR / "watchlist.json"
SEEN_PATH = DATA_DIR / "seen_ids.json"


def _normalize(value: str) -> str:
    return re.sub(r"[\s\-/]", "", (value or "").strip().upper())


def load_watchlist() -> dict:
    try:
        return json.loads(WATCHLIST_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _load_seen() -> dict:
    try:
        data = json.loads(SEEN_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_seen(data: dict) -> None:
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        SEEN_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception:
        pass


def mask_id(value: str) -> str:
    clean = (value or "").strip()
    if len(clean) <= 4:
        return "••••"
    return f"{clean[:2]}•••••{clean[-2:]}"


def extract_identifiers(doc_key: str, ocr_lines: list[str], mrz_second: str | None = None) -> dict[str, str]:
    """Pull raw ID numbers for lookup (never returned to frontend unmasked)."""
    from backend.services.indian_ids import (
        find_aadhaar,
        find_dl,
        find_epic,
        find_pan,
        find_permit_number,
        find_visa_number,
    )

    ids: dict[str, str] = {}
    if doc_key == "passport" and mrz_second:
        passport_no = mrz_second[:9].replace("<", "")
        if passport_no:
            ids["passport"] = passport_no
    elif doc_key == "national_id":
        for label, finder in (("aadhaar", find_aadhaar), ("pan", find_pan), ("epic", find_epic)):
            try:
                value = finder(ocr_lines)
            except Exception:
                value = None
            if value:
                ids[label] = value
    elif doc_key == "driving_licence":
        try:
            value = find_dl(ocr_lines)
        except Exception:
            value = None
        if value:
            ids["dl"] = value
    elif doc_key == "visa":
        try:
            value = find_visa_number(ocr_lines)
        except Exception:
            value = None
        if value:
            ids["visa"] = value
    elif doc_key == "permit":
        try:
            value = find_permit_number(ocr_lines)
        except Exception:
            value = None
        if value:
            ids["permit"] = value
    return {key: value for key, value in ids.items() if value}


def check_watchlist(identifiers: dict[str, str], name: str = "", dob: str = "") -> dict:
    """Returns {checks, reasons, hit, matched_lists}."""
    watchlist = load_watchlist()
    norm_ids = {key: _normalize(value) for key, value in identifiers.items()}

    blacklist_map = {
        "passport": watchlist.get("blacklisted_passports", []),
        "aadhaar": watchlist.get("blacklisted_aadhaar", []),
        "pan": watchlist.get("blacklisted_pan", []),
        "epic": watchlist.get("blacklisted_epic", []),
        "dl": watchlist.get("blacklisted_dl", []),
        "visa": watchlist.get("blacklisted_visa", []),
        "permit": watchlist.get("blacklisted_permit", []),
    }
    blacklisted_norm = set()
    for values in blacklist_map.values():
        blacklisted_norm.update(_normalize(value) for value in (values or []))
    expired_norm = set(_normalize(value) for value in (watchlist.get("expired_ids", []) or []))

    matched_blacklist = [f"{key}:{mask_id(value)}" for key, value in identifiers.items() if _normalize(value) in blacklisted_norm]
    matched_expired = [f"{key}:{mask_id(value)}" for key, value in identifiers.items() if _normalize(value) in expired_norm]

    # Duplicate identity: same ID seen before with a different name/DOB.
    seen = _load_seen()
    duplicate_hits: list[str] = []
    norm_name = (name or "").strip().upper()
    norm_dob = (dob or "").strip()
    for key, value in identifiers.items():
        record = seen.get(f"{key}:{_normalize(value)}")
        if not record:
            continue
        if norm_name and record.get("name") and record["name"] != norm_name:
            duplicate_hits.append(f"{key}:{mask_id(value)} (name mismatch)")
        elif norm_dob and record.get("dob") and record["dob"] != norm_dob:
            duplicate_hits.append(f"{key}:{mask_id(value)} (DOB mismatch)")

    checks = {
        "Not in blacklist database": not matched_blacklist,
        "Not in expired-ID list": not matched_expired,
        "No duplicate identity (same ID, different person)": not duplicate_hits,
    }
    reasons: list[list[str]] = []
    if matched_blacklist:
        reasons.append([f"BLACKLIST HIT {', '.join(matched_blacklist)} — stop and escalate to officer.", "high"])
    if matched_expired:
        reasons.append([f"Expired-list hit {', '.join(matched_expired)} — document must be renewed.", "high"])
    if duplicate_hits:
        reasons.append([f"Possible multiple identity {', '.join(duplicate_hits)} — same ID seen with different details.", "high"])
    if not reasons:
        reasons.append(["No blacklist / expired / duplicate-identity hits in local demo database.", ""])

    return {
        "checks": checks,
        "reasons": reasons,
        "hit": bool(matched_blacklist or matched_expired or duplicate_hits),
        "matched": matched_blacklist + matched_expired + duplicate_hits,
    }


def record_seen(identifiers: dict[str, str], name: str = "", dob: str = "", report_id: str = "") -> None:
    if not identifiers:
        return
    seen = _load_seen()
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for key, value in identifiers.items():
        seen[f"{key}:{_normalize(value)}"] = {
            "name": (name or "").strip().upper()[:60],
            "dob": (dob or "").strip()[:20],
            "report_id": report_id,
            "at": stamp,
        }
    _save_seen(seen)


def watchlist_stats() -> dict:
    watchlist = load_watchlist()
    counts = {}
    total = 0
    for key, value in watchlist.items():
        if key.startswith("_"):
            continue
        size = len(value) if isinstance(value, list) else 0
        counts[key] = size
        total += size
    seen = _load_seen()
    return {"entries": total, "lists": counts, "seen_ids": len(seen)}
