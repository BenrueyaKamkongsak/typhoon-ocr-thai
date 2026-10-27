"""Make the example inbox: made-up Thai winner announcements that look scanned, the Markdown a perfect
OCR would return for each (fixtures), one born-digital PDF with a text layer, and a company register.

All agencies, people and companies are fictional.

    python examples/make_examples.py --fonts path/to/NotoSansThai-*.ttf folder
"""
from __future__ import annotations

import argparse
import csv
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

DOCS = [
    {   # clean case: everything agrees
        "file": "01-ถนน-คสล-บ้านทดลอง.jpg",
        "agency": "องค์การบริหารส่วนตำบลบ้านทดลอง",
        "subject": "ประกาศผู้ชนะการเสนอราคา โครงการก่อสร้างถนนคอนกรีตเสริมเหล็ก หมู่ที่ 4",
        "method_line": "โดยวิธีเฉพาะเจาะจง",
        "body": ["ตามที่ องค์การบริหารส่วนตำบลบ้านทดลอง ได้มีโครงการก่อสร้างถนนคอนกรีตเสริมเหล็ก",
                 "สายบ้านนายสมชาย - ฝายน้ำล้น หมู่ที่ 4 โดยวิธีเฉพาะเจาะจง นั้น",
                 "ผู้ได้รับการคัดเลือกและราคาที่เสนอ มีรายละเอียดดังนี้"],
        "bidders": [["1", "ห้างหุ้นส่วนจำกัด ทดลองก่อสร้าง", "489,500.00", "489,000.00", "ผู้ชนะ"],
                    ["2", "บริษัท ตัวอย่างวิศวกรรม จำกัด", "495,800.00", "-", "-"],
                    ["3", "ร้าน สมมติการช่าง", "498,000.00", "-", "-"]],
        "winner_line": "ผู้ได้รับการคัดเลือก ได้แก่ ห้างหุ้นส่วนจำกัด ทดลองก่อสร้าง โดยเสนอราคาเป็นเงินทั้งสิ้น",
        "amount_line": "489,000.00 บาท (สี่แสนแปดหมื่นเก้าพันบาทถ้วน) ซึ่งเป็นราคารวมภาษีมูลค่าเพิ่มแล้ว",
        "date": "ประกาศ ณ วันที่ 14 ตุลาคม พ.ศ. 2569",
        "signer": ["(นายทดสอบ ใจดี)", "นายกองค์การบริหารส่วนตำบลบ้านทดลอง"], "stamp": ["อบต.", "บ้านทดลอง"],
    },
    {   # amount in digits and in words disagree -> review queue
        "file": "02-ครุภัณฑ์คอมพิวเตอร์-ทต-ตัวอย่าง.jpg",
        "agency": "เทศบาลตำบลตัวอย่าง",
        "subject": "ประกาศผู้ชนะการเสนอราคา โครงการจัดซื้อครุภัณฑ์คอมพิวเตอร์ จำนวน 25 ชุด",
        "method_line": "โดยวิธีประกวดราคาอิเล็กทรอนิกส์ (e-bidding)",
        "body": ["ตามที่ เทศบาลตำบลตัวอย่าง ได้มีโครงการจัดซื้อครุภัณฑ์คอมพิวเตอร์ จำนวน 25 ชุด",
                 "โดยวิธีประกวดราคาอิเล็กทรอนิกส์ (e-bidding) นั้น",
                 "ผู้ยื่นข้อเสนอและราคาที่เสนอ มีรายละเอียดดังนี้"],
        "bidders": [["1", "บริษัท ตัวอย่างวิศวกรรม จำกัด", "1,268,000.00", "1,250,000.00", "ผู้ชนะ"],
                    ["2", "บริษัท สมมติไอที จำกัด", "1,290,000.00", "-", "-"]],
        "winner_line": "ผู้ชนะการเสนอราคา ได้แก่ บริษัท ตัวอย่างวิศวกรรม จำกัด โดยเสนอราคาเป็นเงินทั้งสิ้น",
        "amount_line": "1,250,000.00 บาท (หนึ่งล้านสองแสนบาทถ้วน) ซึ่งเป็นราคารวมภาษีมูลค่าเพิ่มแล้ว",
        "date": "ประกาศ ณ วันที่ 21 ตุลาคม พ.ศ. 2569",
        "signer": ["(นางสาวสมมติ ตั้งใจ)", "นายกเทศมนตรีตำบลตัวอย่าง"], "stamp": ["ทต.", "ตัวอย่าง"],
    },
    {   # short company form + Thai numerals; should still pass and link to the register
        "file": "03-ฝายน้ำล้น-บ้านทดลอง.jpg",
        "agency": "องค์การบริหารส่วนตำบลบ้านทดลอง",
        "subject": "ประกาศผู้ชนะการเสนอราคา โครงการก่อสร้างฝายน้ำล้น หมู่ที่ ๗",
        "method_line": "โดยวิธีเฉพาะเจาะจง",
        "body": ["ตามที่ องค์การบริหารส่วนตำบลบ้านทดลอง ได้มีโครงการก่อสร้างฝายน้ำล้น หมู่ที่ ๗",
                 "โดยวิธีเฉพาะเจาะจง นั้น ผู้ได้รับการคัดเลือกและราคาที่เสนอ มีรายละเอียดดังนี้", ""],
        "bidders": [["๑", "ห้างหุ้นส่วนจำกัด ทดลองก่อสร้าง", "๓๑๒,๐๐๐.๐๐", "๓๐๙,๕๐๐.๐๐", "ผู้ชนะ"],
                    ["๒", "ร้าน สมมติการช่าง", "๓๑๕,๐๐๐.๐๐", "-", "-"]],
        "winner_line": "ผู้ได้รับการคัดเลือก ได้แก่ หจก. ทดลองก่อสร้าง โดยเสนอราคาเป็นเงินทั้งสิ้น",
        "amount_line": "๓๐๙,๕๐๐.๐๐ บาท (สามแสนเก้าพันห้าร้อยบาทถ้วน) ซึ่งเป็นราคารวมภาษีมูลค่าเพิ่มแล้ว",
        "date": "ประกาศ ณ วันที่ ๒๘ ต.ค. ๖๙",
        "signer": ["(นายทดสอบ ใจดี)", "นายกองค์การบริหารส่วนตำบลบ้านทดลอง"], "stamp": ["อบต.", "บ้านทดลอง"],
    },
]

REGISTER = [
    ("0103569000001", "ห้างหุ้นส่วนจำกัด ทดลองก่อสร้าง"),
    ("0105569000002", "บริษัท ตัวอย่างวิศวกรรม จำกัด"),
    ("0105569000003", "บริษัท สมมติไอที จำกัด"),
]


def markdown_for(d: dict) -> str:
    rows = "\n".join("<tr>" + "".join(f"<td>{c}</td>" for c in b) + "</tr>" for b in d["bidders"])
    body = " ".join(x for x in d["body"] if x)
    return f"""# ประกาศ{d['agency']}

เรื่อง {d['subject']}
{d['method_line']}

{body}

<table>
<tr><th rowspan="2">ลำดับ</th><th rowspan="2">ชื่อผู้เสนอราคา</th><th colspan="2">ราคาที่เสนอ (บาท)</th><th rowspan="2">หมายเหตุ</th></tr>
<tr><th>ครั้งแรก</th><th>ต่อรองแล้ว</th></tr>
{rows}
</table>

{d['winner_line']} {d['amount_line']}

{d['date']}

<figure>ตราประทับสีแดง "{' '.join(d['stamp'])}" ทับลายเซ็นผู้ลงนาม</figure>

{d['signer'][0]}
{d['signer'][1]}
"""


def draw(d: dict, reg: str, bold: str, out: Path, seed: int) -> None:
    W, H = 1240, 1754
    img = Image.new("RGB", (W, H), (250, 249, 245))
    g = ImageDraw.Draw(img)
    f = lambda s, b=False: ImageFont.truetype(bold if b else reg, s)  # noqa: E731

    def center(y, t, font):
        g.text(((W - g.textlength(t, font=font)) / 2, y), t, font=font, fill=(25, 25, 25))

    g.ellipse((W / 2 - 45, 70, W / 2 + 45, 160), outline=(40, 40, 40), width=3)
    g.text((W / 2 - 22, 98), "ตรา", font=f(26, True), fill=(40, 40, 40))
    center(190, "ประกาศ" + d["agency"], f(34, True))
    center(245, "เรื่อง " + d["subject"], f(24))
    center(285, d["method_line"], f(24))
    g.line((480, 335, 760, 335), fill=(60, 60, 60), width=2)
    y = 365
    for line in d["body"]:
        g.text((130, y), line, font=f(25), fill=(30, 30, 30))
        y += 46
    x = [110, 180, 560, 760, 950, 1130]
    top, rh = y + 25, 58
    bottom = top + rh * 2 + rh * len(d["bidders"])
    ink = (40, 40, 40)
    g.rectangle((x[0], top, x[-1], bottom), outline=ink, width=2)
    for xi in x[1:-1]:
        g.line((xi, top + (rh if xi == 760 else 0), xi, bottom), fill=ink, width=2)
    g.line((x[2], top + rh, x[4], top + rh), fill=ink, width=2)
    for i in range(len(d["bidders"]) + 1):
        g.line((x[0], top + rh * (2 + i), x[-1], top + rh * (2 + i)), fill=ink, width=2)

    def cell(c0, c1, r0, r1, t, font, left=False):
        cx = x[c0] + 14 if left else (x[c0] + x[c1]) / 2 - g.textlength(t, font=font) / 2
        g.text((cx, top + rh * r0 + (rh * (r1 - r0) - 34) / 2), t, font=font, fill=(25, 25, 25))

    hf, bf = f(23, True), f(22)
    cell(0, 1, 0, 2, "ลำดับ", hf); cell(1, 2, 0, 2, "ชื่อผู้เสนอราคา", hf)
    cell(2, 4, 0, 1, "ราคาที่เสนอ (บาท)", hf); cell(2, 3, 1, 2, "ครั้งแรก", hf)
    cell(3, 4, 1, 2, "ต่อรองแล้ว", hf); cell(4, 5, 0, 2, "หมายเหตุ", hf)
    for r, row in enumerate(d["bidders"]):
        cell(0, 1, r + 2, r + 3, row[0], bf); cell(1, 2, r + 2, r + 3, row[1], bf, left=True)
        for c in (2, 3, 4):
            cell(c, c + 1, r + 2, r + 3, row[c], bf)
    y = bottom + 45
    for t in (d["winner_line"], d["amount_line"]):
        g.text((130, y), t, font=f(24), fill=(30, 30, 30))
        y += 46
    center(y + 40, d["date"], f(25))
    sy = y + 170
    g.line((720, sy, 980, sy), fill=(60, 60, 60), width=1)
    g.line([(735, sy - 8), (770, sy - 40), (800, sy - 12), (835, sy - 45), (870, sy - 6), (920, sy - 30), (960, sy - 10)],
           fill=(30, 40, 120), width=3, joint="curve")
    for i, t in enumerate(d["signer"]):
        g.text((850 - g.textlength(t, font=f(24)) / 2, sy + 15 + i * 42), t, font=f(24), fill=(30, 30, 30))
    stamp = Image.new("RGBA", (260, 260), (0, 0, 0, 0))
    sg = ImageDraw.Draw(stamp)
    sg.ellipse((10, 10, 250, 250), outline=(200, 30, 40, 170), width=6)
    sg.ellipse((40, 40, 220, 220), outline=(200, 30, 40, 150), width=3)
    for i, t in enumerate(d["stamp"]):
        sg.text((130 - sg.textlength(t, font=f(30, True)) / 2, 90 + i * 44), t, font=f(30, True), fill=(200, 30, 40, 170))
    stamp = stamp.rotate(-18, resample=Image.BICUBIC)
    img.paste(stamp, (590, sy - 160), stamp)

    rnd = random.Random(seed)
    img = img.rotate(rnd.uniform(-1.6, 1.6), resample=Image.BICUBIC, fillcolor=(235, 233, 228))
    img = img.filter(ImageFilter.GaussianBlur(0.7))
    px = img.load()
    for _ in range(9000):
        v = rnd.randint(90, 200)
        px[rnd.randrange(W), rnd.randrange(H)] = (v, v, v)
    img.save(out, quality=72)


def text_pdf(reg: str, bold: str, out: Path) -> None:
    """A born-digital announcement (exported from a word processor): has a text layer, so no OCR."""
    from fpdf import FPDF
    pdf = FPDF(format="A4")
    pdf.add_font("th", "", reg)
    pdf.add_font("th", "B", bold)
    pdf.set_text_shaping(True)
    pdf.add_page()
    pdf.set_font("th", "B", 16)
    pdf.cell(0, 10, "ประกาศสำนักงานสาธารณสุขอำเภอสมมติ", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("th", "", 13)
    for t in ["เรื่อง ประกาศผู้ชนะการเสนอราคา โครงการจัดซื้อวัสดุการแพทย์",
              "โดยวิธีเฉพาะเจาะจง"]:
        pdf.cell(0, 8, t, align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    for t in ["ตามที่ สำนักงานสาธารณสุขอำเภอสมมติ ได้มีโครงการจัดซื้อวัสดุการแพทย์ โดยวิธีเฉพาะเจาะจง นั้น",
              "ผู้ได้รับการคัดเลือก ได้แก่ บริษัท สมมติเมดิคอล จำกัด โดยเสนอราคาเป็นเงินทั้งสิ้น",
              "86,400.00 บาท (แปดหมื่นหกพันสี่ร้อยบาทถ้วน) ซึ่งเป็นราคารวมภาษีมูลค่าเพิ่มแล้ว"]:
        pdf.multi_cell(0, 8, t, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(6)
    pdf.cell(0, 8, "ประกาศ ณ วันที่ 30 ตุลาคม พ.ศ. 2569", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.output(str(out))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--regular", required=True)
    ap.add_argument("--bold", required=True)
    ap.add_argument("--dest", type=Path, default=Path(__file__).parent)
    a = ap.parse_args()
    inbox, fixtures = a.dest / "inbox", a.dest / "fixtures"
    inbox.mkdir(parents=True, exist_ok=True)
    fixtures.mkdir(parents=True, exist_ok=True)
    for i, d in enumerate(DOCS):
        draw(d, a.regular, a.bold, inbox / d["file"], seed=i + 7)
        (fixtures / f"{d['file']}.p1.md").write_text(markdown_for(d), encoding="utf-8")
    # A scan with no fixture: stands in for a page the model fails on.
    draw(DOCS[0], a.regular, a.bold, inbox / "04-สแกนเสีย-ไม่มีผลOCR.jpg", seed=99)
    text_pdf(a.regular, a.bold, inbox / "05-วัสดุการแพทย์-ไฟล์ดิจิทัล.pdf")
    # Its text layer comes out with detached Thai marks, so the pipeline OCRs it; this is what OCR returns.
    (fixtures / "05-วัสดุการแพทย์-ไฟล์ดิจิทัล.pdf.p1.md").write_text(
        "# ประกาศสำนักงานสาธารณสุขอำเภอสมมติ\n\n"
        "เรื่อง ประกาศผู้ชนะการเสนอราคา โครงการจัดซื้อวัสดุการแพทย์\n"
        "โดยวิธีเฉพาะเจาะจง\n\n"
        "ตามที่ สำนักงานสาธารณสุขอำเภอสมมติ ได้มีโครงการจัดซื้อวัสดุการแพทย์ โดยวิธีเฉพาะเจาะจง นั้น\n"
        "ผู้ได้รับการคัดเลือก ได้แก่ บริษัท สมมติเมดิคอล จำกัด โดยเสนอราคาเป็นเงินทั้งสิ้น\n"
        "86,400.00 บาท (แปดหมื่นหกพันสี่ร้อยบาทถ้วน) ซึ่งเป็นราคารวมภาษีมูลค่าเพิ่มแล้ว\n\n"
        "ประกาศ ณ วันที่ 30 ตุลาคม พ.ศ. 2569\n", encoding="utf-8")
    with (a.dest / "company_register.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "name"])
        w.writerows(REGISTER)
    print("examples written to", a.dest)


if __name__ == "__main__":
    main()
