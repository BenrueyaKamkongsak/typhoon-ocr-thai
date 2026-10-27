from datetime import date
from decimal import Decimal

import pytest

from thai_ocr_pipeline.thai import (
    baht_words_to_amount, normalise_company, normalise_thai_text, parse_amount, parse_thai_date, to_arabic_digits,
)


def test_thai_digits():
    assert to_arabic_digits("๔๘๙,๐๐๐.๐๐") == "489,000.00"


@pytest.mark.parametrize("text,expected", [
    ("489,000.00 บาท", Decimal("489000.00")),
    ("๔๘๙,๐๐๐", Decimal("489000")),
    ("วงเงิน 1,250,000 บาท", Decimal("1250000")),
    ("-", None),
    (None, None),
])
def test_parse_amount(text, expected):
    assert parse_amount(text) == expected


@pytest.mark.parametrize("words,expected", [
    ("สี่แสนแปดหมื่นเก้าพันบาทถ้วน", "489000.00"),
    ("(สี่แสนแปดหมื่นเก้าพันบาทถ้วน)", "489000.00"),
    ("หนึ่งล้านสองแสนห้าหมื่นบาทถ้วน", "1250000.00"),
    ("สิบเอ็ดบาท", "11.00"),
    ("ยี่สิบเอ็ดบาทห้าสิบสตางค์", "21.50"),
    ("หนึ่งร้อยบาทถ้วน", "100.00"),
    ("ร้อยบาท", "100.00"),
    ("สองร้อยล้านห้าแสนบาท", "200500000.00"),
    ("หนึ่งล้านล้านบาท", "1000000000000.00"),
    ("เก้าสิบเก้าล้านเก้าแสนเก้าหมื่นเก้าพันเก้าร้อยเก้าสิบเก้าบาทเก้าสิบเก้าสตางค์", "99999999.99"),
    ("ห้าสิบสตางค์", "0.50"),
])
def test_baht_words(words, expected):
    assert baht_words_to_amount(words) == Decimal(expected)


@pytest.mark.parametrize("words", ["สวัสดีบาท", "ไม่มีจำนวนเงิน", ""])
def test_baht_words_rejects_non_amounts(words):
    assert baht_words_to_amount(words) is None


@pytest.mark.parametrize("text,expected", [
    ("ประกาศ ณ วันที่ 14 ตุลาคม พ.ศ. 2569", date(2026, 10, 14)),
    ("๑๔ ต.ค. ๖๙", date(2026, 10, 14)),
    ("1 มกราคม 2568", date(2025, 1, 1)),
    ("31 กุมภาพันธ์ 2569", None),
    ("ไม่มีวันที่", None),
])
def test_thai_date(text, expected):
    assert parse_thai_date(text) == expected


@pytest.mark.parametrize("name,core,kind", [
    ("ห้างหุ้นส่วนจำกัด ทดลองก่อสร้าง", "ทดลองก่อสร้าง", "ห้างหุ้นส่วนจำกัด"),
    ("หจก. ทดลองก่อสร้าง", "ทดลองก่อสร้าง", "ห้างหุ้นส่วนจำกัด"),
    ("บริษัท ตัวอย่างวิศวกรรม จำกัด", "ตัวอย่างวิศวกรรม", "บริษัทจำกัด"),
    ("บจก.ตัวอย่างวิศวกรรม", "ตัวอย่างวิศวกรรม", "บริษัทจำกัด"),
    ("บริษัท ตัวอย่าง จำกัด (มหาชน)", "ตัวอย่าง", "บริษัทมหาชนจำกัด"),
    ("ร้าน สมมติการช่าง", "สมมติการช่าง", "ร้าน"),
    ("นายสมชาย ใจดี", "นายสมชายใจดี", ""),
])
def test_normalise_company(name, core, kind):
    assert normalise_company(name) == (core, kind)


@pytest.mark.parametrize("raw,fixed", [
    ("ห้างหุ้นส่วนจ\u0e4d\u0e32กัด", "ห้างหุ้นส่วนจำกัด"),
    ("น\u0e49\u0e4d\u0e32", "น้ำ"),          # tone mark before nikhahit
    ("น\u0e4d\u0e49\u0e32", "น้ำ"),          # tone mark after nikhahit
    ("จำกัด", "จำกัด"),                      # already correct: unchanged
])
def test_split_sara_am_is_joined(raw, fixed):
    assert normalise_thai_text(raw) == fixed
