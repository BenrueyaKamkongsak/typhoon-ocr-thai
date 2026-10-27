import csv
import shutil
from pathlib import Path

import pytest

from thai_ocr_pipeline.extract import extract, html_tables
from thai_ocr_pipeline.ingest import text_layer_is_usable
from thai_ocr_pipeline.ocr import FixtureOCR
from thai_ocr_pipeline.pipeline import run
from thai_ocr_pipeline.validate import CompanyMaster, clean_and_check

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"
FIX = EXAMPLES / "fixtures"


def md(name):
    return (FIX / f"{name}.p1.md").read_text(encoding="utf-8")


def test_merged_header_cells_expand():
    grid, header_rows = html_tables(md("01-ถนน-คสล-บ้านทดลอง.jpg"))[0]
    assert header_rows == 2
    assert grid[0][2] == grid[0][3] == "ราคาที่เสนอ (บาท)"
    assert grid[1][:4] == ["ลำดับ", "ชื่อผู้เสนอราคา", "ครั้งแรก", "ต่อรองแล้ว"]


def test_extract_clean_announcement():
    e = extract(md("01-ถนน-คสล-บ้านทดลอง.jpg"))
    assert e.agency == "องค์การบริหารส่วนตำบลบ้านทดลอง"
    assert e.method == "เฉพาะเจาะจง"
    assert e.winner == "ห้างหุ้นส่วนจำกัด ทดลองก่อสร้าง"
    assert e.amount == "489,000.00"
    assert [b.final_price for b in e.bidders] == ["489,000.00", "-", "-"]
    c = clean_and_check(e)
    assert c.status == "ok" and str(c.amount) == "489000.00" and c.announce_date == "2026-10-14"


def test_words_mismatch_goes_to_review():
    c = clean_and_check(extract(md("02-ครุภัณฑ์คอมพิวเตอร์-ทต-ตัวอย่าง.jpg")))
    assert c.status == "review"
    assert any("ไม่ตรงกับตัวหนังสือ" in x for x in c.errors)


def test_short_company_form_and_thai_digits_match_register():
    master = CompanyMaster.load(EXAMPLES / "company_register.csv")
    c = clean_and_check(extract(md("03-ฝายน้ำล้น-บ้านทดลอง.jpg")), master)
    assert c.status == "ok", c.errors
    assert c.winner_master_id == "0103569000001"
    assert c.announce_date == "2026-10-28"


def test_winner_price_must_match_table():
    text = md("01-ถนน-คสล-บ้านทดลอง.jpg").replace("<td>489,000.00</td>", "<td>480,000.00</td>")
    c = clean_and_check(extract(text))
    assert any("ไม่ตรงกับวงเงินที่ประกาศ" in x for x in c.errors)


def test_detached_thai_marks_mean_unusable_text_layer():
    garbled = "ประกาศส นักงานสาธารณส ำ ขอุ ำ เภอสมมติ เร่อง ประกาศผ ื ชนะการเ ู้ สนอราคา " * 3
    assert not text_layer_is_usable(garbled)
    assert text_layer_is_usable(md("01-ถนน-คสล-บ้านทดลอง.jpg"))


def test_end_to_end_with_cache(tmp_path):
    out = tmp_path / "out"
    rep = run(EXAMPLES / "inbox", out, FixtureOCR(FIX), workers=3,
              master_csv=EXAMPLES / "company_register.csv")
    assert rep["files"] == 5 and rep["documents_ok"] == 3 and rep["documents_review"] == 2
    assert rep["ocr_failures"] == 1
    rows = {r["file"]: r for r in csv.DictReader((out / "documents.csv").open(encoding="utf-8-sig"))}
    assert rows["02-ครุภัณฑ์คอมพิวเตอร์-ทต-ตัวอย่าง.jpg"]["status"] == "review"
    assert rows["05-วัสดุการแพทย์-ไฟล์ดิจิทัล.pdf"]["amount"] == "86400.00"
    review = list(csv.DictReader((out / "review_queue.csv").open(encoding="utf-8-sig")))
    assert len(review) == 2
    # Second run: everything that succeeded comes from the cache; only the failed page is retried.
    rep2 = run(EXAMPLES / "inbox", out, FixtureOCR(FIX), master_csv=EXAMPLES / "company_register.csv")
    assert rep2["cache_hits"] == 4 and rep2["ocr_calls"] == 1


def test_unreadable_file_is_reported_not_fatal(tmp_path):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    shutil.copy(EXAMPLES / "inbox" / "01-ถนน-คสล-บ้านทดลอง.jpg", inbox)
    (inbox / "broken.pdf").write_bytes(b"%PDF-1.4 not really")
    rep = run(inbox, tmp_path / "out", FixtureOCR(FIX))
    assert rep["documents_ok"] == 1 and rep["documents_review"] == 1
