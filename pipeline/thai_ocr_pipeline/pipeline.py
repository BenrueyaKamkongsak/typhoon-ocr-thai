"""Run the whole thing: files -> pages -> OCR (cached, in parallel) -> fields -> checks -> CSV/JSON."""
from __future__ import annotations

import csv
import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path

from .extract import extract
from .ingest import SourceFile, discover, load_pages
from .ocr import OcrBackend, OcrError, PageCache
from .validate import CompanyMaster, clean_and_check

log = logging.getLogger(__name__)

DOC_COLUMNS = [
    "file", "sha256", "pages", "page_sources", "status", "agency", "project", "method",
    "winner_name", "winner_core", "winner_type", "winner_master_id", "winner_master_name",
    "winner_match_score", "amount", "amount_words", "amount_words_value", "announce_date",
    "errors", "warnings",
]
BIDDER_COLUMNS = ["file", "sha256", "no", "name", "name_core", "entity_type", "first_price", "final_price", "note", "is_winner"]


def _write_csv(path: Path, columns: list[str], rows: list[dict]) -> None:
    # utf-8-sig so Excel opens Thai text correctly
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: ("" if v is None else v) for k, v in r.items()})


def _num(v: Decimal | None) -> str:
    return "" if v is None else f"{v:.2f}"


def run(input_dir: Path, out_dir: Path, backend: OcrBackend, cache_dir: Path | None = None,
        workers: int = 4, master_csv: Path | None = None, force_ocr: bool = False) -> dict:
    from rapidfuzz import fuzz

    from .thai import normalise_company, parse_amount, to_arabic_digits

    t0 = time.monotonic()
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "markdown").mkdir(exist_ok=True)
    cache = PageCache(cache_dir or out_dir / ".cache")
    master = CompanyMaster.load(master_csv) if master_csv else None
    stats = {"files": 0, "pages": 0, "text_layer_pages": 0, "cache_hits": 0, "ocr_calls": 0, "ocr_failures": 0}

    files: list[SourceFile] = discover(input_dir)
    stats["files"] = len(files)
    log.info("found %d files in %s", len(files), input_dir)

    # 1) Pages. A file that can't be opened is reported, not fatal.
    broken: dict[str, str] = {}
    for src in files:
        try:
            src.pages = load_pages(src, force_ocr=force_ocr)
        except Exception as e:  # corrupt PDF, unreadable image...
            broken[src.sha256] = f"เปิดไฟล์ไม่ได้: {e}"
            src.pages = []
        stats["pages"] += len(src.pages)

    # 2) OCR, page by page, in parallel; cached pages and text-layer pages skip the model.
    page_md: dict[tuple[str, int], str] = {}
    page_src: dict[tuple[str, int], str] = {}
    page_err: dict[tuple[str, int], str] = {}
    todo = []
    for src in files:
        for p in src.pages:
            key = (src.sha256, p.number)
            if p.text is not None:
                page_md[key], page_src[key] = p.text, "text"
                stats["text_layer_pages"] += 1
            elif (hit := cache.get(src.sha256, p.number)) is not None:
                page_md[key], page_src[key] = hit, "cache"
                stats["cache_hits"] += 1
            else:
                todo.append((src, p))

    def _one(src: SourceFile, p):
        md = backend.ocr(p.image_jpeg, src.name, p.number)
        cache.put(src.sha256, p.number, md)
        return md

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = {pool.submit(_one, s, p): (s, p) for s, p in todo}
        for fut in as_completed(futures):
            s, p = futures[fut]
            key = (s.sha256, p.number)
            stats["ocr_calls"] += 1
            try:
                page_md[key], page_src[key] = fut.result(), backend.name
            except OcrError as e:
                stats["ocr_failures"] += 1
                page_err[key] = str(e)
                log.error("%s p%d: %s", s.name, p.number, e)

    # 3) Fields, cleaning, checks, outputs.
    docs, bidders, review = [], [], []
    for src in files:
        keys = [(src.sha256, p.number) for p in src.pages]
        md = "\n\n".join(page_md.get(k, "") for k in keys)
        (out_dir / "markdown" / f"{src.path.stem}.md").write_text(md, encoding="utf-8")
        e = extract(md)
        c = clean_and_check(e, master)
        if src.sha256 in broken:
            c.errors.insert(0, broken[src.sha256])
        failed = [f"OCR หน้า {k[1]} ไม่สำเร็จ: {page_err[k]}" for k in keys if k in page_err]
        c.errors[:0] = failed
        c.status = "review" if c.errors else "ok"

        row = {
            "file": str(src.path.relative_to(input_dir)), "sha256": src.sha256, "pages": len(keys),
            "page_sources": ",".join(page_src.get(k, "failed") for k in keys),
            **{k: v for k, v in asdict(c).items() if k not in ("errors", "warnings")},
            "amount": _num(c.amount), "amount_words_value": _num(c.amount_words_value),
            "winner_match_score": "" if c.winner_match_score is None else f"{c.winner_match_score:.0f}",
            "errors": " | ".join(c.errors), "warnings": " | ".join(c.warnings),
        }
        docs.append(row)
        if c.status == "review":
            review.append(row)
        for b in e.bidders:
            core, kind = normalise_company(b.name)
            bidders.append({
                "file": row["file"], "sha256": src.sha256, "no": to_arabic_digits(b.no), "name": b.name, "name_core": core,
                "entity_type": kind, "first_price": _num(parse_amount(b.first_price)),
                "final_price": _num(parse_amount(b.final_price)), "note": b.note,
                "is_winner": "Y" if core and c.winner_core and fuzz.ratio(core, c.winner_core) >= 90 else "",
            })

    _write_csv(out_dir / "documents.csv", DOC_COLUMNS, docs)
    _write_csv(out_dir / "bidders.csv", BIDDER_COLUMNS, bidders)
    _write_csv(out_dir / "review_queue.csv", DOC_COLUMNS, review)
    report = {
        **stats,
        "documents_ok": sum(d["status"] == "ok" for d in docs),
        "documents_review": len(review),
        "seconds": round(time.monotonic() - t0, 2),
        "backend": backend.name,
    }
    (out_dir / "run_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report
