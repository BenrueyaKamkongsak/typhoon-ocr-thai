"""Pull the fields of a Thai procurement winner announcement (ประกาศผู้ชนะการเสนอราคา) out of OCR Markdown.

Rule-based on purpose: every value can be traced back to the text it came from, and it runs without
a second model call. Fields it can't find stay empty and the validator sends the document to review.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from html.parser import HTMLParser

from .thai import to_arabic_digits


@dataclass
class Bidder:
    no: str = ""
    name: str = ""
    first_price: str = ""
    final_price: str = ""
    note: str = ""


@dataclass
class Extracted:
    agency: str = ""
    subject: str = ""
    project: str = ""
    method: str = ""
    winner: str = ""
    amount: str = ""
    amount_words: str = ""
    announce_date: str = ""
    bidders: list[Bidder] = field(default_factory=list)


# ---------------------------------------------------------------- HTML tables (Typhoon emits <table>)
class _TableParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables: list[list[list[tuple[str, int, int, bool]]]] = []
        self._row: list | None = None
        self._cell: list[str] | None = None
        self._attrs: dict = {}
        self._is_th = False

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self.tables.append([])
        elif tag == "tr" and self.tables:
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell, self._attrs, self._is_th = [], dict(attrs), tag == "th"
        elif tag == "br" and self._cell is not None:
            self._cell.append(" ")

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._cell is not None and self._row is not None:
            def span(k):
                try:
                    return max(1, min(50, int(self._attrs.get(k) or 1)))
                except ValueError:
                    return 1
            text = re.sub(r"\s+", " ", "".join(self._cell)).strip()
            self._row.append((text, span("rowspan"), span("colspan"), self._is_th))
            self._cell = None
        elif tag == "tr" and self._row is not None and self.tables:
            self.tables[-1].append(self._row)
            self._row = None

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)


def html_tables(markdown: str) -> list[tuple[list[list[str]], int]]:
    """Every <table> as a full grid (merged cells repeated), plus how many leading rows are headers."""
    p = _TableParser()
    p.feed(markdown)
    out = []
    for rows in p.tables:
        grid: list[list[str | None]] = []
        header_rows = 0
        for r, row in enumerate(rows):
            while len(grid) <= r:
                grid.append([])
            c = 0
            for text, rs, cs, is_th in row:
                while c < len(grid[r]) and grid[r][c] is not None:
                    c += 1
                for dr in range(rs):
                    while len(grid) <= r + dr:
                        grid.append([])
                    line = grid[r + dr]
                    while len(line) < c + cs:
                        line.append(None)
                    for dc in range(cs):
                        line[c + dc] = text
                c += cs
            if row and all(cell[3] for cell in row) and header_rows == r:
                header_rows = r + 1
        width = max((len(r) for r in grid), default=0)
        full = [[(v or "") for v in r] + [""] * (width - len(r)) for r in grid]
        if header_rows == 0 and full:
            header_rows = 1  # no <th>: assume the first row is the header
        out.append((full, header_rows))
    return out


_COLS = [  # (field, keywords in the header, checked in order)
    ("final_price", ("ต่อรอง", "ราคาที่ตกลง", "ราคาที่ตกลงซื้อ", "ราคาสุดท้าย")),
    ("first_price", ("ครั้งแรก", "ราคาที่เสนอ", "ราคาเสนอ", "วงเงินที่เสนอ")),
    ("name", ("ชื่อผู้", "ผู้เสนอราคา", "ผู้ยื่นข้อเสนอ", "ชื่อ")),
    ("no", ("ลำดับ", "ที่")),
    ("note", ("หมายเหตุ", "ผลการพิจารณา")),
]


def bidders_from_tables(markdown: str) -> list[Bidder]:
    for grid, header_rows in html_tables(markdown):
        if not grid or header_rows >= len(grid):
            continue
        labels = [" ".join(dict.fromkeys(grid[r][c] for r in range(header_rows) if grid[r][c]))
                  for c in range(len(grid[0]))]
        mapping: dict[str, int] = {}
        for c, label in enumerate(labels):
            for fld, keys in _COLS:
                if fld not in mapping and any(k in label for k in keys):
                    mapping[fld] = c
                    break
        if "name" not in mapping or not ({"first_price", "final_price"} & mapping.keys()):
            continue  # not a bidder table
        bidders = []
        for row in grid[header_rows:]:
            b = Bidder(**{f: row[c].strip() for f, c in mapping.items() if c < len(row)})
            if b.name:
                bidders.append(b)
        if bidders:
            return bidders
    return []


# ---------------------------------------------------------------- free text
def _plain(markdown: str) -> str:
    text = re.sub(r"<table.*?</table>", "\n", markdown, flags=re.S)
    text = re.sub(r"<figure.*?</figure>", "\n", text, flags=re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"^[#>*\-\s]+", "", text, flags=re.M)
    return to_arabic_digits(text)


def _first(pattern: str, text: str, flags=0) -> str:
    m = re.search(pattern, text, flags)
    return re.sub(r"\s+", " ", m.group(1)).strip(" .,:") if m else ""


METHODS = {
    "เฉพาะเจาะจง": "เฉพาะเจาะจง",
    "คัดเลือก": "คัดเลือก",
    "ประกวดราคาอิเล็กทรอนิกส์": "e-bidding",
    "e-bidding": "e-bidding",
    "ตลาดอิเล็กทรอนิกส์": "e-market",
    "e-market": "e-market",
    "ประกาศเชิญชวนทั่วไป": "ประกาศเชิญชวนทั่วไป",
}


def extract(markdown: str) -> Extracted:
    text = _plain(markdown)
    flat = re.sub(r"\s+", " ", text)
    e = Extracted()
    e.agency = _first(r"^\s*ประกาศ(?!ผู้ชนะ|\s*ณ)\s*(.+?)\s*$", text, re.M)
    e.subject = _first(r"เรื่อง\s*(.+?)(?:\n|$)", text)
    e.project = _first(r"โครงการ\s*(.+?)\s*(?:โดยวิธี|ด้วยวิธี|\n|$)", text)
    said = _first(r"(?:โดย|ด้วย)วิธี\s*(.{0,40})", flat)
    for key, canon in METHODS.items():
        if key.lower() in said.lower():
            e.method = canon
            break
    e.winner = _first(r"ผู้(?:ได้รับการคัดเลือก|ชนะการเสนอราคา|ชนะ)\s*(?:ได้แก่|คือ)\s*(.+?)\s*(?:โดยเสนอราคา|เสนอราคา|ราคาที่|ซึ่ง|$)", flat)
    e.amount = _first(r"(?:เป็นเงินทั้งสิ้น|เป็นจำนวนเงิน|ในวงเงิน|รวมเป็นเงิน)\s*([\d,]+(?:\.\d+)?)\s*บาท", flat)
    e.amount_words = _first(r"[\d,]+(?:\.\d+)?\s*บาท\s*\(([^)]*บาท[^)]*)\)", flat)
    e.announce_date = _first(r"(?:ประกาศ\s*ณ\s*วันที่|ลงวันที่)\s*(.+?(?:\d{4}|\d{2}))(?:\s|$)", flat)
    e.bidders = bidders_from_tables(markdown)
    return e
