"""Clean the extracted fields and decide whether a document can be loaded or needs a person to check it."""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

from .extract import Extracted
from .thai import baht_words_to_amount, normalise_company, parse_amount, parse_thai_date


@dataclass
class CompanyMaster:
    """Optional register of known companies (CSV with columns id,name) for fuzzy matching."""
    ids: list[str]
    names: list[str]
    cores: list[str]

    @classmethod
    def load(cls, path: Path) -> "CompanyMaster":
        with path.open(encoding="utf-8-sig", newline="") as f:
            rows = [r for r in csv.DictReader(f) if r.get("name")]
        return cls([r.get("id", "") for r in rows], [r["name"] for r in rows],
                   [normalise_company(r["name"])[0] for r in rows])

    def match(self, name: str, threshold: float = 88) -> tuple[str, str, float]:
        from rapidfuzz import fuzz, process
        core = normalise_company(name)[0]
        if not core or not self.cores:
            return "", "", 0.0
        hit = process.extractOne(core, self.cores, scorer=fuzz.ratio)
        if not hit or hit[1] < threshold:
            return "", "", float(hit[1]) if hit else 0.0
        return self.ids[hit[2]], self.names[hit[2]], float(hit[1])


@dataclass
class Clean:
    agency: str
    project: str
    method: str
    winner_name: str
    winner_core: str
    winner_type: str
    winner_master_id: str
    winner_master_name: str
    winner_match_score: float | None
    amount: Decimal | None
    amount_words: str
    amount_words_value: Decimal | None
    announce_date: str
    status: str = "ok"
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


REQUIRED = {"agency": "หน่วยงาน", "project": "ชื่อโครงการ", "winner": "ผู้ชนะ", "amount": "วงเงิน",
            "announce_date": "วันที่ประกาศ"}


def clean_and_check(e: Extracted, master: CompanyMaster | None = None) -> Clean:
    amount = parse_amount(e.amount)
    words_value = baht_words_to_amount(e.amount_words)
    d = parse_thai_date(e.announce_date)
    core, kind = normalise_company(e.winner)
    mid, mname, score = master.match(e.winner) if (master and e.winner) else ("", "", None)
    c = Clean(
        agency=e.agency, project=e.project, method=e.method,
        winner_name=e.winner, winner_core=core, winner_type=kind,
        winner_master_id=mid, winner_master_name=mname, winner_match_score=score,
        amount=amount, amount_words=e.amount_words, amount_words_value=words_value,
        announce_date=d.isoformat() if d else "",
    )

    for f, label in REQUIRED.items():
        if not getattr(e, f):
            c.errors.append(f"ไม่พบ{label}")
    if e.announce_date and not d:
        c.errors.append(f"อ่านวันที่ไม่ได้: {e.announce_date}")
    if e.amount and amount is None:
        c.errors.append(f"อ่านวงเงินไม่ได้: {e.amount}")

    # Digits vs words: the strongest check against misread numbers.
    if amount is not None and e.amount_words:
        if words_value is None:
            c.warnings.append(f"อ่านจำนวนเงินตัวหนังสือไม่ได้: {e.amount_words}")
        elif words_value != amount:
            c.errors.append(f"วงเงินตัวเลข {amount:,.2f} ไม่ตรงกับตัวหนังสือ {words_value:,.2f}")
    elif amount is not None:
        c.warnings.append("ไม่มีจำนวนเงินตัวหนังสือให้ตรวจไขว้")

    # Winner must be one of the bidders, and the winning price must be the announced amount.
    if e.bidders:
        from rapidfuzz import fuzz
        # Fuzzy, so one misread letter in the table doesn't break the link to the winner.
        winner_rows = [b for b in e.bidders
                       if core and fuzz.ratio(normalise_company(b.name)[0], core) >= 90]
        if core and not winner_rows:
            c.errors.append("ชื่อผู้ชนะไม่อยู่ในตารางผู้เสนอราคา")
        for b in winner_rows:
            final = parse_amount(b.final_price) or parse_amount(b.first_price)
            if amount is not None and final is not None and final != amount:
                c.errors.append(f"ราคาของผู้ชนะในตาราง {final:,.2f} ไม่ตรงกับวงเงินที่ประกาศ {amount:,.2f}")
        for b in e.bidders:
            first, final = parse_amount(b.first_price), parse_amount(b.final_price)
            if first is not None and final is not None and final > first:
                c.warnings.append(f"ราคาต่อรองของ {b.name} สูงกว่าราคาเสนอครั้งแรก")
    else:
        c.warnings.append("ไม่พบตารางผู้เสนอราคา")

    if master and e.winner and not mid:
        c.warnings.append(f"ไม่พบผู้ชนะในทะเบียนบริษัท (คะแนนใกล้สุด {score:.0f})")

    c.status = "review" if c.errors else "ok"
    return c
