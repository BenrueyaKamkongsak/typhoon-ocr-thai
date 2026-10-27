"""Daily: OCR new procurement documents, clean the fields, load what passes, queue the rest for review.

Variables (Airflow Admin > Variables):
  thai_ocr_inbox      folder where scanned files land          e.g. /data/procurement/inbox
  thai_ocr_out_root   where each run writes its outputs        e.g. /data/procurement/ocr_runs
  thai_ocr_cache      shared OCR cache (re-runs cost nothing)  e.g. /data/procurement/ocr_cache
  thai_ocr_master     company register CSV (id,name), optional
Connection/secret: TYPHOON_API_KEY in the worker environment (or a secrets backend).

The package must be importable on the workers: pip install -r pipeline/requirements.txt and put
pipeline/ on PYTHONPATH (or build it into the image).
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from pathlib import Path

from airflow.decorators import dag, task
from airflow.models import Variable


@dag(
    schedule="0 2 * * *",
    start_date=datetime(2026, 11, 1),
    catchup=False,
    max_active_runs=1,
    default_args={"retries": 2, "retry_delay": timedelta(minutes=10)},
    tags=["ocr", "procurement"],
)
def thai_ocr_procurement():

    @task
    def ocr_and_clean(ds: str | None = None) -> str:
        from thai_ocr_pipeline.ocr import TyphoonOCR
        from thai_ocr_pipeline.pipeline import run

        out = Path(Variable.get("thai_ocr_out_root")) / ds
        master = Variable.get("thai_ocr_master", default_var="") or None
        report = run(
            input_dir=Path(Variable.get("thai_ocr_inbox")),
            out_dir=out,
            backend=TyphoonOCR(os.environ["TYPHOON_API_KEY"]),
            cache_dir=Path(Variable.get("thai_ocr_cache")),
            workers=4,
            master_csv=Path(master) if master else None,
        )
        if report["ocr_calls"] and report["ocr_failures"] == report["ocr_calls"]:
            raise RuntimeError(f"every OCR call failed: {report}")  # e.g. API down: let Airflow retry
        return str(out)

    @task
    def load_ok_documents(out_dir: str) -> int:
        """Replace with your loader (BigQuery / Postgres). Only status == ok rows are loaded."""
        import csv
        rows = [r for r in csv.DictReader(open(Path(out_dir) / "documents.csv", encoding="utf-8-sig"))
                if r["status"] == "ok"]
        # e.g. bigquery.Client().load_table_from_json(rows, "project.procurement.winner_announcements")
        return len(rows)

    @task
    def notify_review_queue(out_dir: str) -> None:
        import csv
        review = list(csv.DictReader(open(Path(out_dir) / "review_queue.csv", encoding="utf-8-sig")))
        report = json.loads((Path(out_dir) / "run_report.json").read_text(encoding="utf-8"))
        print(f"{report['documents_ok']} loaded, {len(review)} waiting for review")
        # e.g. post to Slack / create ClickUp tasks for each row in review

    out = ocr_and_clean()
    load_ok_documents(out)
    notify_review_queue(out)


thai_ocr_procurement()
