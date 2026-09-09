"""Small, dependency-free validator for ICAO TD3 passport MRZs."""

import re
from datetime import date, datetime

MRZ_WEIGHTS = (7, 3, 1)
MRZ_CHARACTERS = re.compile(r"[^A-Z0-9<]")


def clean_mrz_text(text: str) -> str:
    return MRZ_CHARACTERS.sub("", text.upper())


def check_digit(value: str) -> str:
    total = 0
    for index, char in enumerate(value):
        if char.isdigit():
            char_value = int(char)
        elif "A" <= char <= "Z":
            char_value = ord(char) - ord("A") + 10
        elif char == "<":
            char_value = 0
        else:
            raise ValueError(f"Unsupported MRZ character: {char!r}")
        total += char_value * MRZ_WEIGHTS[index % len(MRZ_WEIGHTS)]
    return str(total % 10)


def format_mrz_date(value: str, *, birth_date: bool) -> str:
    if not re.fullmatch(r"\d{6}", value):
        return value
    year = int(value[:2])
    year += 1900 if birth_date and year > date.today().year % 100 else 2000
    return f"{value[4:6]} {value[2:4]} {year}"


def valid_mrz_date(value: str, *, birth_date: bool) -> bool:
    if not re.fullmatch(r"\d{6}", value):
        return False
    year = int(value[:2])
    year += 1900 if birth_date and year > date.today().year % 100 else 2000
    try:
        parsed = datetime.strptime(f"{year:04d}{value[2:]}", "%Y%m%d").date()
    except ValueError:
        return False
    return parsed <= date.today() if birth_date else parsed >= date.today()


def find_td3_mrz(ocr_lines: list[str]) -> tuple[str, str] | None:
    # Some OCR engines split one MRZ line into two text fragments. Consider
    # adjacent fragments as well as individual lines, then remove whitespace.
    source_lines = [line for line in ocr_lines if line.strip()]
    raw_candidates = source_lines + [first + second for first, second in zip(source_lines, source_lines[1:])]
    candidates = [clean_mrz_text(line) for line in raw_candidates]
    candidates = list(dict.fromkeys(line for line in candidates if 40 <= len(line) <= 46))
    for first, second in zip(candidates, candidates[1:]):
        if first.startswith("P<") and len(first) == 44 and len(second) == 44:
            return first, _normalise_numeric_positions(second)
    return None


def _normalise_numeric_positions(line: str) -> str:
    """Repair only safe OCR confusions in TD3 numeric/date/check-digit positions."""
    characters = list(line)
    numeric_positions = {9, 13, 14, 15, 16, 17, 18, 19, 21, 22, 23, 24, 25, 26, 27, 42, 43}
    substitutions = {"O": "0", "I": "1", "L": "1", "S": "5", "B": "8"}
    for index in numeric_positions:
        characters[index] = substitutions.get(characters[index], characters[index])
    return "".join(characters)


def parse_td3_mrz(first_line: str, second_line: str) -> dict:
    checks = {
        "TD3 document structure": first_line.startswith("P<") and len(first_line) == 44 and len(second_line) == 44,
        "Passport number check digit": check_digit(second_line[0:9]) == second_line[9],
        "Date of birth check digit": check_digit(second_line[13:19]) == second_line[19],
        "Date of birth is valid": valid_mrz_date(second_line[13:19], birth_date=True),
        "Expiry date check digit": check_digit(second_line[21:27]) == second_line[27],
        "Passport is not expired": valid_mrz_date(second_line[21:27], birth_date=False),
        "Personal number check digit": check_digit(second_line[28:42]) == second_line[42],
        "Composite check digit": check_digit(second_line[0:10] + second_line[13:20] + second_line[21:43]) == second_line[43],
    }
    name_parts = first_line[5:].rstrip("<").split("<<", maxsplit=1)
    surname = name_parts[0].replace("<", " ").strip()
    given_names = name_parts[1].replace("<", " ").strip() if len(name_parts) == 2 else ""
    return {
        "fields": {
            "Document type": "Passport (TD3)",
            "Issuing state": first_line[2:5],
            "Name": " ".join(part for part in (given_names, surname) if part),
            "Passport no.": f"{second_line[:2]}•••••{second_line[7:9]}",
            "Date of birth": format_mrz_date(second_line[13:19], birth_date=True),
            "Expiry date": format_mrz_date(second_line[21:27], birth_date=False),
        },
        "checks": checks,
    }
