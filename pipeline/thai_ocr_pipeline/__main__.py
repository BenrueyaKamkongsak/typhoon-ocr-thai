"""python -m thai_ocr_pipeline --input inbox/ --out out/ [--backend typhoon|fixtures]"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

from .ocr import FixtureOCR, OcrError, TyphoonOCR
from .pipeline import run


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="thai_ocr_pipeline", description="Thai document OCR -> clean CSV")
    ap.add_argument("--input", required=True, type=Path, help="folder of PDFs / images")
    ap.add_argument("--out", required=True, type=Path, help="output folder")
    ap.add_argument("--backend", choices=["typhoon", "fixtures"], default="typhoon")
    ap.add_argument("--fixtures", type=Path, help="folder of saved OCR Markdown (backend=fixtures)")
    ap.add_argument("--cache", type=Path, help="OCR cache folder (default: <out>/.cache)")
    ap.add_argument("--workers", type=int, default=4, help="pages sent to the model at the same time")
    ap.add_argument("--master", type=Path, help="CSV of known companies (id,name) for matching")
    ap.add_argument("--force-ocr", action="store_true", help="OCR PDFs even when they have a text layer")
    ap.add_argument("--model", default=os.getenv("TYPHOON_OCR_MODEL", "typhoon-ocr"))
    ap.add_argument("--base-url", default=os.getenv("TYPHOON_BASE_URL", "https://api.opentyphoon.ai/v1"))
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO if a.verbose else logging.WARNING, format="%(levelname)s %(message)s")

    if not a.input.is_dir():
        print(f"input folder not found: {a.input}", file=sys.stderr)
        return 2
    try:
        if a.backend == "fixtures":
            if not a.fixtures:
                ap.error("--fixtures is required with --backend fixtures")
            backend = FixtureOCR(a.fixtures)
        else:
            backend = TyphoonOCR(os.getenv("TYPHOON_API_KEY", ""), base_url=a.base_url, model=a.model)
    except OcrError as e:
        print(e, file=sys.stderr)
        return 2

    report = run(a.input, a.out, backend, cache_dir=a.cache, workers=a.workers,
                 master_csv=a.master, force_ocr=a.force_ocr)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
