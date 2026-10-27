"""Thai-specific normalisation: digits, Buddhist-era dates, baht amounts in words, company names."""
from __future__ import annotations

import re
from datetime import date
from decimal import Decimal, InvalidOperation

THAI_DIGITS = str.maketrans("๐๑๒๓๔๕๖๗๘๙", "0123456789")


def to_arabic_digits(text: str) -> str:
    """'๔๘๙,๐๐๐' -> '489,000'."""
    return text.translate(THAI_DIGITS)


def parse_amount(text: str | None) -> Decimal | None:
    """'489,000.00 บาท' / '๔๘๙,๐๐๐' -> Decimal('489000.00'). None when no number is found."""
    if not text:
        return None
    m = re.search(r"\d[\d,]*(?:\.\d+)?", to_arabic_digits(text))
    if not m:
        return None
    try:
        return Decimal(m.group(0).replace(",", ""))
    except InvalidOperation:
        return None


# ---------------------------------------------------------------- baht amounts written in words
_DIGIT_WORDS = {
    "ศูนย์": 0, "หนึ่ง": 1, "เอ็ด": 1, "สอง": 2, "ยี่": 2, "สาม": 3, "สี่": 4,
    "ห้า": 5, "หก": 6, "เจ็ด": 7, "แปด": 8, "เก้า": 9,
}
_PLACE_WORDS = {"สิบ": 10, "ร้อย": 100, "พัน": 1_000, "หมื่น": 10_000, "แสน": 100_000}
_TOKEN = re.compile("|".join(sorted(map(re.escape, [*_DIGIT_WORDS, *_PLACE_WORDS]), key=len, reverse=True)))


def _words_below_million(words: str) -> int:
    total, pending = 0, None
    pos = 0
    for m in _TOKEN.finditer(words):
        if words[pos:m.start()].strip():
            raise ValueError(f"unknown word: {words[pos:m.start()]!r}")
        pos = m.end()
        tok = m.group(0)
        if tok in _DIGIT_WORDS:
            pending = _DIGIT_WORDS[tok]
        else:
            # 'สิบ' alone means 10; 'ยี่สิบ' 20; other places need a digit before them.
            total += (1 if pending is None else pending) * _PLACE_WORDS[tok]
            pending = None
    if words[pos:].strip():
        raise ValueError(f"unknown word: {words[pos:]!r}")
    return total + (pending or 0)


def _words_to_int(words: str) -> int:
    """Handles 'ล้าน' at any depth: 'หนึ่งล้านล้าน', 'สองร้อยล้านห้าแสน'."""
    if "ล้าน" not in words:
        return _words_below_million(words)
    head, _, tail = words.rpartition("ล้าน")
    return (_words_to_int(head) if head else 1) * 1_000_000 + (_words_below_million(tail) if tail else 0)


def baht_words_to_amount(text: str) -> Decimal | None:
    """'สี่แสนแปดหมื่นเก้าพันบาทถ้วน' -> Decimal('489000.00'). None if it isn't a baht amount in words."""
    if not text:
        return None
    s = re.sub(r"[\s()\[\]]", "", text)
    s = s.replace("ถ้วน", "").replace("ตรง", "")
    if "บาท" not in s and "สตางค์" not in s:
        return None
    baht_part, _, satang_part = s.partition("บาท")
    if "บาท" not in s:  # only satang
        baht_part, satang_part = "", s
    satang_part = satang_part.replace("สตางค์", "")
    try:
        baht = _words_to_int(baht_part) if baht_part else 0
        satang = _words_to_int(satang_part) if satang_part else 0
    except ValueError:
        return None
    if satang >= 100:
        return None
    return Decimal(baht) + (Decimal(satang) / 100).quantize(Decimal("0.01"))


# ---------------------------------------------------------------- dates
MONTHS = {
    "มกราคม": 1, "กุมภาพันธ์": 2, "มีนาคม": 3, "เมษายน": 4, "พฤษภาคม": 5, "มิถุนายน": 6,
    "กรกฎาคม": 7, "สิงหาคม": 8, "กันยายน": 9, "ตุลาคม": 10, "พฤศจิกายน": 11, "ธันวาคม": 12,
    "ม.ค.": 1, "ก.พ.": 2, "มี.ค.": 3, "เม.ย.": 4, "พ.ค.": 5, "มิ.ย.": 6,
    "ก.ค.": 7, "ส.ค.": 8, "ก.ย.": 9, "ต.ค.": 10, "พ.ย.": 11, "ธ.ค.": 12,
}
_MONTH_RE = "|".join(sorted(map(re.escape, MONTHS), key=len, reverse=True))
_DATE_RE = re.compile(rf"(\d{{1,2}})\s*({_MONTH_RE})\s*(?:พ\.\s?ศ\.|พศ\.?)?\s*(\d{{2,4}})")


def parse_thai_date(text: str | None) -> date | None:
    """'14 ตุลาคม พ.ศ. 2569' / '๑๔ ต.ค. ๖๙' -> date(2026, 10, 14)."""
    if not text:
        return None
    m = _DATE_RE.search(to_arabic_digits(text))
    if not m:
        return None
    day, month, year = int(m.group(1)), MONTHS[m.group(2)], int(m.group(3))
    if year < 100:          # two-digit BE year: 69 -> 2569
        year += 2500
    if year > 2400:         # Buddhist era -> CE
        year -= 543
    try:
        return date(year, month, day)
    except ValueError:
        return None


# ---------------------------------------------------------------- company names
_ENTITY_PATTERNS = [
    # (regex on the start / end of the name, entity type)
    (re.compile(r"^(?:บริษัท|บมจ\.?)\s*(.+?)\s*จำกัด\s*\(มหาชน\)$"), "บริษัทมหาชนจำกัด"),
    (re.compile(r"^บมจ\.?\s*(.+)$"), "บริษัทมหาชนจำกัด"),
    (re.compile(r"^(?:บริษัท|บจก\.?)\s*(.+?)\s*(?:จำกัด)?$"), "บริษัทจำกัด"),
    (re.compile(r"^(?:ห้างหุ้นส่วนจำกัด|หจก\.?)\s*(.+)$"), "ห้างหุ้นส่วนจำกัด"),
    (re.compile(r"^(?:ห้างหุ้นส่วนสามัญ|หสน\.?)\s*(.+)$"), "ห้างหุ้นส่วนสามัญ"),
    (re.compile(r"^(?:ร้าน)\s*(.+)$"), "ร้าน"),
]


def normalise_company(name: str | None) -> tuple[str, str]:
    """'หจก. ทดลองก่อสร้าง' and 'ห้างหุ้นส่วนจำกัด ทดลองก่อสร้าง' -> ('ทดลองก่อสร้าง', 'ห้างหุ้นส่วนจำกัด').

    Returns (core name used for matching, entity type or '')."""
    if not name:
        return "", ""
    s = re.sub(r"\s+", " ", to_arabic_digits(name)).strip().strip(".,;:")
    for pattern, kind in _ENTITY_PATTERNS:
        m = pattern.match(s)
        if m:
            return re.sub(r"\s+", "", m.group(1)), kind
    return re.sub(r"\s+", "", s), ""
