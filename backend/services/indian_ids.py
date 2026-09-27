"""India document validators for SIH26194 Module 1 (OCR extract) + Module 2 (validation).

Sources (public documentation, no DB lookup in prototype):
- Passport: ICAO Doc 9303 TD3 (already in mrz.py) — 2x44 chars, 7-3-1 check digits.
- Aadhaar: UIDAI — 12-digit random number, Verhoeff checksum, never starts with 0/1.
  https://uidai.gov.in, Verhoeff algorithm (public domain checksum).
- Driving Licence: Parivahan / MoRTH Sarathi format SS-RR-YYYY-NNNNNNN (15 chars,
  16 with space/hyphen), SS = state code, RR = RTO, YYYY = year of issue.
  https://parivahan.gov.in/rcdlstatus
- PAN: Income Tax Dept — 10 chars AAAAA9999A, 4th char = holder type
  (P/F/C/H/A/T/B/L/J/G), 5th = surname initial.
  https://www.incometaxindia.gov.in
- Voter ID (EPIC): ECI — 10 chars ABC1234567 = 3 letters + 7 digits.
- Visa / Permit: generic border-doc checks — number present, issue < expiry,
  stay/entries present. No central public format, so structural only.
"""

import re
from datetime import date, datetime

# ---- Verhoeff (Aadhaar checksum, UIDAI) ----
_VERHOEFF_D = (
    (0, 1, 2, 3, 4, 5, 6, 7, 8, 9),
    (1, 2, 3, 4, 0, 6, 7, 8, 9, 5),
    (2, 3, 4, 0, 1, 7, 8, 9, 5, 6),
    (3, 4, 0, 1, 2, 8, 9, 5, 6, 7),
    (4, 0, 1, 2, 3, 9, 5, 6, 7, 8),
    (5, 9, 8, 7, 6, 0, 4, 3, 2, 1),
    (6, 5, 9, 8, 7, 1, 0, 4, 3, 2),
    (7, 6, 5, 9, 8, 2, 1, 0, 4, 3),
    (8, 7, 6, 5, 9, 3, 2, 1, 0, 4),
    (9, 8, 7, 6, 5, 4, 3, 2, 1, 0),
)
_VERHOEFF_P = (
    (0, 1, 2, 3, 4, 5, 6, 7, 8, 9),
    (1, 5, 7, 6, 2, 8, 3, 0, 9, 4),
    (5, 8, 0, 3, 7, 9, 6, 1, 4, 2),
    (8, 9, 1, 6, 0, 4, 3, 7, 2, 5),
    (9, 4, 5, 3, 1, 2, 6, 8, 7, 0),
    (4, 2, 8, 6, 5, 7, 3, 9, 0, 1),
    (2, 7, 9, 3, 8, 0, 6, 4, 1, 5),
    (7, 0, 4, 6, 9, 1, 3, 2, 5, 8),
)


def verhoeff_valid(number: str) -> bool:
    """Standard Verhoeff checksum — Aadhaar uses this for its last digit."""
    if not number.isdigit():
        return False
    checksum = 0
    for pos, ch in enumerate(reversed(number)):
        checksum = _VERHOEFF_D[checksum][_VERHOEFF_P[pos % 8][int(ch)]]
    return checksum == 0


def valid_aadhaar_number(number: str) -> bool:
    digits = re.sub(r"\D", "", number)
    if not re.fullmatch(r"[2-9][0-9]{11}", digits):
        return False  # UIDAI never issues 0/1-leading numbers
    return verhoeff_valid(digits)


PAN_HOLDER_TYPES = {
    "P": "Individual",
    "F": "Firm/LLP",
    "C": "Company",
    "H": "HUF",
    "A": "AOP",
    "T": "Trust",
    "B": "BOI",
    "L": "Local Authority",
    "J": "Artificial Juridical Person",
    "G": "Government",
}

# Parivahan state codes (2-letter). OR kept as legacy alias of OD.
DL_STATE_CODES = {
    "AN", "AP", "AR", "AS", "BR", "CG", "CH", "DD", "DL", "DN",
    "GA", "GJ", "HR", "HP", "JK", "JH", "KA", "KL", "LA", "LD",
    "MH", "ML", "MN", "MP", "MZ", "NL", "OD", "OR", "PB", "PY",
    "RJ", "SK", "TN", "TR", "TS", "UK", "UP", "WB",
}


def valid_pan_number(value: str) -> tuple[bool, str]:
    clean = value.strip().upper()
    if not re.fullmatch(r"[A-Z]{5}[0-9]{4}[A-Z]", clean):
        return False, "Format must be AAAAA9999A"
    holder = PAN_HOLDER_TYPES.get(clean[3])
    if not holder:
        return False, "Invalid 4th-char holder type"
    return True, holder


def valid_epic_number(value: str) -> bool:
    return bool(re.fullmatch(r"[A-Z]{3}[0-9]{7}", value.strip().upper()))


def parse_dl_number(value: str) -> dict | None:
    """Parse Sarathi DL SS-RR-YYYY-NNNNNNN. Returns None if structure wrong."""
    clean = re.sub(r"[\s\-/]", "", value.strip().upper())
    match = re.fullmatch(r"([A-Z]{2})(\d{2})(\d{4})(\d{7})", clean)
    if not match:
        return None
    state, rto, year_s, serial = match.groups()
    year = int(year_s)
    current_year = date.today().year
    return {
        "normalized": f"{state}-{rto}{year_s}{serial}",
        "state": state,
        "state_valid": state in DL_STATE_CODES,
        "rto": rto,
        "rto_valid": rto != "00",
        "year": year,
        "year_valid": 1980 <= year <= current_year + 1,
        "serial_valid": serial != "0000000",
    }


def _all_text(lines: list[str]) -> str:
    return "\n".join(lines).upper()


def find_aadhaar(lines: list[str]) -> str | None:
    """First 12-digit UIDAI candidate (Verhoeff-passing preferred)."""
    text = _all_text(lines)
    candidates = re.findall(r"(?<![0-9])[2-9][0-9]{3}\s?[0-9]{4}\s?[0-9]{4}(?![0-9])", text)
    for raw in candidates:
        digits = re.sub(r"\D", "", raw)
        if verhoeff_valid(digits):
            return digits
    for raw in candidates:  # fallback: structural hit even if checksum fails
        return re.sub(r"\D", "", raw)
    return None


def has_masked_aadhaar(lines: list[str]) -> bool:
    return bool(re.search(r"X{4}\s?X{4}\s?\d{4}", _all_text(lines)))


def find_pan(lines: list[str]) -> str | None:
    for line in lines:
        match = re.search(r"\b([A-Z]{5}[0-9]{4}[A-Z])\b", line.upper())
        if match:
            return match.group(1)
    return None


def find_epic(lines: list[str]) -> str | None:
    for line in lines:
        match = re.search(r"\b([A-Z]{3}[0-9]{7})\b", line.upper())
        if match:
            return match.group(1)
    return None


def find_dl(lines: list[str]) -> str | None:
    text = _all_text(lines)
    match = re.search(r"\b([A-Z]{2})[\s\-]?(\d{2})[\s\-]?(\d{4})[\s\-]?(\d{7})\b", text)
    if match:
        return re.sub(r"\s+", "", match.group(0).upper())
    return None


def find_pincode(lines: list[str]) -> str | None:
    """6-digit PIN only when a PIN/postal keyword is nearby — bare 6-digit
    numbers (order IDs, timestamps) are NOT pincodes."""
    text = _all_text(lines)
    match = re.search(
        r"(?:PIN|PINCODE|POSTAL(?:\s*CODE)?|ZIP)[^\d]{0,12}([1-9][0-9]{5})(?![0-9])", text
    )
    return match.group(1) if match else None


def find_gender(lines: list[str]) -> str | None:
    text = _all_text(lines)
    if "FEMALE" in text:
        return "Female"
    if "MALE" in text:
        return "Male"
    match = re.search(r"\b(?:SEX|GENDER)\s*[:/]?\s*([MF])\b", text)
    if match:
        return "Female" if match.group(1) == "F" else "Male"
    return None


def find_dates(lines: list[str]) -> list[date]:
    """Collect DD/MM/YYYY style dates from OCR text."""
    text = _all_text(lines)
    found: list[date] = []
    for day, month, year in re.findall(r"\b(\d{2})[/\-.](\d{2})[/\-.](\d{4})\b", text):
        try:
            found.append(date(int(year), int(month), int(day)))
        except ValueError:
            continue
    # Deduplicate, chronological
    return sorted(set(found))


def find_keyword_date(lines: list[str], keywords: tuple[str, ...]) -> date | None:
    """A date that appears right after one of the keywords (DOB, EXPIRY…).

    Random screenshots contain dates (timestamps, notifications) — only a
    date labelled as birth/issue/expiry counts as that field.
    """
    text = _all_text(lines)
    pattern = r"(?:%s)[^\d]{0,20}(\d{2})[/\-.](\d{2})[/\-.](\d{4})" % "|".join(keywords)
    match = re.search(pattern, text)
    if not match:
        return None
    try:
        return date(int(match.group(3)), int(match.group(2)), int(match.group(1)))
    except ValueError:
        return None


DOB_KEYWORDS = ("DOB", "DATE OF BIRTH", "BIRTH DATE", "BORN")
EXPIRY_KEYWORDS = ("EXPIRY", "EXPIRES", "VALID TILL", "VALID UPTO", "VALID UP TO", "DATE OF EXPIRY")
ISSUE_KEYWORDS = ("ISSUE DATE", "DATE OF ISSUE", "ISSUED")


def find_visa_number(lines: list[str]) -> str | None:
    text = _all_text(lines)
    # Space-tolerant: OCR often splits "AB123456" into "ABI 23456" (1/I confusion).
    match = re.search(r"VISA\s*(?:NO|NUMBER|N0)?\s*[:.]?\s*([A-Z0-9][A-Z0-9 ]{5,14})", text)
    if match:
        candidate = re.sub(r"\s+", "", match.group(1))
        candidate = candidate[:12]
        if re.fullmatch(r"[A-Z0-9]{6,12}", candidate):
            return candidate
    match = re.search(r"\b([A-Z]{1,2}[0-9]{6,10})\b", text)
    return match.group(1) if match else None


def find_permit_number(lines: list[str]) -> str | None:
    """Permit number ONLY with a PERMIT keyword — bare AB-12345 codes in
    screenshots (order IDs, versions) are not permits."""
    text = _all_text(lines)
    match = re.search(r"PERMIT\s*(?:NO|NUMBER)?\s*[:.]?\s*([A-Z0-9\-\/]{6,18})", text)
    if match:
        return match.group(1).strip("-/ ")
    return None


def _dob_checks(dates: list[date]) -> tuple[str | None, bool]:
    past = [d for d in dates if d <= date.today()]
    if not past:
        return None, False
    dob = min(past)  # oldest past date = likely DOB
    return dob.strftime("%d %m %Y"), True


# ---- Per-document parsers: each returns {"fields", "checks"} ----

def parse_national_id(ocr_lines: list[str]) -> dict:
    """National ID = Aadhaar first, then PAN, then EPIC (Voter).

    Aux fields (gender/PIN/DOB) are only read when a core ID number exists —
    otherwise random screenshots with dates/numbers would score falsely.
    """
    aadhaar = find_aadhaar(ocr_lines)
    pan = find_pan(ocr_lines)
    epic = find_epic(ocr_lines)
    id_found = bool(aadhaar or pan or epic)

    fields: dict[str, str] = {}
    checks: dict[str, bool] = {}
    if aadhaar:
        masked = f"XXXXXXXX{aadhaar[-4:]}"
        fields["Aadhaar no."] = masked
        checks["Aadhaar 12-digit UIDAI format"] = bool(re.fullmatch(r"[2-9][0-9]{11}", aadhaar))
        checks["Aadhaar Verhoeff checksum"] = verhoeff_valid(aadhaar)
    elif has_masked_aadhaar(ocr_lines):
        fields["Aadhaar no."] = "Masked (XXXX XXXX ____)"
        checks["Aadhaar 12-digit UIDAI format"] = True
        checks["Aadhaar Verhoeff checksum"] = False
    else:
        checks["Aadhaar 12-digit UIDAI format"] = False
        checks["Aadhaar Verhoeff checksum"] = False
    if pan:
        ok, holder = valid_pan_number(pan)
        fields["PAN"] = f"{pan[:3]}•••{pan[-2:]} ({holder if ok else 'invalid'})"
        checks["PAN format AAAAA9999A + holder type"] = ok
    if epic:
        fields["Voter ID (EPIC)"] = epic
        checks["EPIC format AAA9999999"] = valid_epic_number(epic)
    if id_found:
        gender = find_gender(ocr_lines)
        pincode = find_pincode(ocr_lines)
        dob = find_keyword_date(ocr_lines, DOB_KEYWORDS)
        if gender:
            fields["Gender"] = gender
        if pincode:
            fields["Pincode"] = pincode
            checks["Pincode with PIN keyword"] = True
        if dob and dob <= date.today():
            fields["Date of birth"] = dob.strftime("%d %m %Y")
            checks["Date of birth (labelled, past)"] = True
        else:
            checks["Date of birth (labelled DOB) found"] = False
    checks["At least one ID number found (Aadhaar/PAN/EPIC)"] = id_found
    return {"fields": fields, "checks": checks, "id_found": id_found}


def parse_driving_licence(ocr_lines: list[str]) -> dict:
    raw = find_dl(ocr_lines)
    id_found = raw is not None and parse_dl_number(raw) is not None

    fields: dict[str, str] = {}
    checks: dict[str, bool] = {}
    if raw:
        parsed = parse_dl_number(raw)
        if parsed:
            fields["DL no."] = f"{parsed['state']}•••{parsed['normalized'][-5:]}"
            fields["Issuing state"] = parsed["state"]
            fields["Year of issue"] = str(parsed["year"])
            checks["DL structure SS-RR-YYYY-NNNNNNN (Parivahan)"] = True
            checks["DL state code valid"] = parsed["state_valid"]
            checks["DL RTO code valid"] = parsed["rto_valid"]
            checks["DL year of issue valid"] = parsed["year_valid"]
            checks["DL serial valid"] = parsed["serial_valid"]
        else:
            checks["DL structure SS-RR-YYYY-NNNNNNN (Parivahan)"] = False
            checks["DL number detected"] = True
    else:
        checks["DL number detected"] = False
    if id_found:
        gender = find_gender(ocr_lines)
        if gender:
            fields["Gender"] = gender
        dob = find_keyword_date(ocr_lines, DOB_KEYWORDS)
        if dob and dob <= date.today():
            fields["Date of birth"] = dob.strftime("%d %m %Y")
            checks["Date of birth (labelled DOB, past)"] = True
        expiry = find_keyword_date(ocr_lines, EXPIRY_KEYWORDS + ("VALIDITY", "VALID UPTO DATE"))
        if expiry:
            fields["Validity / expiry"] = expiry.strftime("%d %m %Y")
            checks["Licence not expired"] = expiry >= date.today()
        else:
            checks["Licence expiry date (labelled) found"] = False
    return {"fields": fields, "checks": checks, "id_found": id_found}


def parse_visa(ocr_lines: list[str]) -> dict:
    text = _all_text(lines=ocr_lines)
    number = find_visa_number(ocr_lines)
    # Visa counts only when the word VISA is on the document — otherwise a
    # random code in a screenshot is not a visa number.
    id_found = number is not None and "VISA" in text
    issue = find_keyword_date(ocr_lines, ISSUE_KEYWORDS)
    expiry = find_keyword_date(ocr_lines, EXPIRY_KEYWORDS)
    if issue is None or expiry is None:
        dates = find_dates(ocr_lines)
        past = [d for d in dates if d <= date.today()]
        future = [d for d in dates if d >= date.today()]
        issue = issue or (max(past) if past and id_found else None)
        expiry = expiry or (max(future) if future and id_found else None)
    entries = None
    for keyword in ("MULTIPLE", "DOUBLE", "SINGLE", "TRIPLE"):
        if keyword in text:
            entries = keyword.capitalize()
            break
    stay = re.search(r"STAY[^0-9]{0,12}(\d{1,3})", text)
    vtype = re.search(r"\b(TOURIST|BUSINESS|STUDENT|EMPLOYMENT|MEDICAL|TRANSIT|CONFERENCE)\b", text)

    fields: dict[str, str] = {}
    checks: dict[str, bool] = {}
    if id_found:
        fields["Visa no."] = f"{number[:2]}•••{number[-2:]}" if len(number) > 4 else number
        checks["Visa number 6-12 alphanumerics"] = bool(re.fullmatch(r"[A-Z0-9]{6,12}", number))
    else:
        checks["Visa number detected"] = False
    if vtype and id_found:
        fields["Visa type"] = vtype.group(1).capitalize()
        checks["Visa type recognised"] = True
    else:
        checks["Visa type recognised"] = False
    if entries and id_found:
        fields["Entries"] = entries
    if stay and id_found:
        fields["Stay duration"] = f"{stay.group(1)} days"
        checks["Stay duration present"] = True
    if issue and id_found:
        fields["Issue date"] = issue.strftime("%d %m %Y")
        checks["Issue date <= today"] = issue <= date.today()
    if expiry and id_found:
        fields["Expiry date"] = expiry.strftime("%d %m %Y")
        checks["Visa not expired"] = expiry >= date.today()
    else:
        checks["Visa expiry date found"] = False
    if issue and expiry and id_found:
        checks["Issue before expiry"] = issue < expiry
    return {"fields": fields, "checks": checks, "id_found": id_found}


def parse_permit(ocr_lines: list[str]) -> dict:
    number = find_permit_number(ocr_lines)
    id_found = number is not None  # finder already requires PERMIT keyword
    issue = find_keyword_date(ocr_lines, ISSUE_KEYWORDS)
    expiry = find_keyword_date(ocr_lines, EXPIRY_KEYWORDS)

    fields: dict[str, str] = {}
    checks: dict[str, bool] = {}
    if id_found:
        fields["Permit no."] = number
        checks["Permit number detected (6+ chars)"] = len(re.sub(r"[^A-Z0-9]", "", number)) >= 6
    else:
        checks["Permit number detected"] = False
    if issue and id_found:
        fields["Issue date"] = issue.strftime("%d %m %Y")
    if expiry and id_found:
        fields["Expiry date"] = expiry.strftime("%d %m %Y")
        checks["Permit not expired"] = expiry >= date.today()
    else:
        checks["Permit expiry date (labelled) found"] = False
    if issue and expiry and id_found:
        checks["Issue before expiry"] = issue < expiry
    return {"fields": fields, "checks": checks, "id_found": id_found}
