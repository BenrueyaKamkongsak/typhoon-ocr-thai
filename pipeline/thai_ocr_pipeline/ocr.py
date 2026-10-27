"""OCR backends and the page cache.

- TyphoonOCR: the real model through api.opentyphoon.ai (OpenAI-compatible), with retries.
- FixtureOCR: reads saved Markdown, for tests and demos without an API key.
- PageCache: OCR output stored by file hash + page, so a file is never sent twice.
"""
from __future__ import annotations

import base64
import logging
import random
import time
from pathlib import Path
from typing import Protocol

import requests

log = logging.getLogger(__name__)

# Prompt of the official typhoon-ocr client (task_type "v1.5", figure_language "Thai").
PROMPT_V15 = """Extract all text from the image.


Instructions:
- Only return the clean Markdown.
- Do not include any explanation or extra text.
- You must include all information on the page.


Formatting Rules:
- Tables: Render tables using <table>...</table> in clean HTML format.
- Equations: Render equations using LaTeX syntax with inline ($...$) and block ($$...$$).
- Images/Charts/Diagrams: Wrap any clearly defined visual areas (e.g. charts, diagrams, pictures) in:


<figure>
Describe the image's main elements (people, objects, text), note any contextual clues (place, event, culture), mention visible text and its meaning, provide deeper analysis when relevant (especially for financial charts, graphs, or documents), comment on style or architecture if relevant, then give a concise overall summary. Describe in Thai.
</figure>


- Page Numbers: Wrap page numbers in <page_number>...</page_number> (e.g., <page_number>14</page_number>).
- Checkboxes: Use ☐ for unchecked and ☑ for checked boxes.
    """


class OcrError(RuntimeError):
    pass


class OcrBackend(Protocol):
    name: str

    def ocr(self, image_jpeg: bytes, file_name: str, page: int) -> str: ...


class TyphoonOCR:
    name = "typhoon"

    def __init__(self, api_key: str, base_url: str = "https://api.opentyphoon.ai/v1",
                 model: str = "typhoon-ocr", timeout: float = 180, max_retries: int = 5):
        if not api_key:
            raise OcrError("TYPHOON_API_KEY is not set")
        self.url = base_url.rstrip("/") + "/chat/completions"
        self.model = model
        self.timeout = timeout
        self.max_retries = max_retries
        self.session = requests.Session()
        self.session.headers.update({"Authorization": f"Bearer {api_key}"})

    def ocr(self, image_jpeg: bytes, file_name: str, page: int) -> str:
        b64 = base64.b64encode(image_jpeg).decode()
        body = {
            "model": self.model,
            "messages": [{"role": "user", "content": [
                {"type": "text", "text": PROMPT_V15},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
            ]}],
            "max_tokens": 16384, "temperature": 0.1, "top_p": 0.6, "repetition_penalty": 1.1,
        }
        for attempt in range(1, self.max_retries + 1):
            try:
                r = self.session.post(self.url, json=body, timeout=self.timeout)
            except requests.RequestException as e:
                err, retry_after = f"network error: {e}", None
            else:
                if r.status_code == 200:
                    try:
                        return r.json()["choices"][0]["message"]["content"].strip()
                    except (KeyError, IndexError, ValueError) as e:
                        raise OcrError(f"unexpected response: {r.text[:300]}") from e
                if r.status_code in (401, 403):
                    raise OcrError(f"API key rejected ({r.status_code})")
                if r.status_code not in (408, 409, 429) and r.status_code < 500:
                    raise OcrError(f"HTTP {r.status_code}: {r.text[:300]}")
                err, retry_after = f"HTTP {r.status_code}", r.headers.get("Retry-After")
            if attempt == self.max_retries:
                raise OcrError(f"{file_name} p{page}: gave up after {attempt} attempts ({err})")
            wait = float(retry_after) if retry_after and retry_after.isdigit() else min(60, 2 ** attempt) + random.random()
            log.warning("%s p%d: %s, retrying in %.1fs", file_name, page, err, wait)
            time.sleep(wait)
        raise OcrError("unreachable")


class FixtureOCR:
    """Returns <fixtures>/<file name>.p<page>.md, as if the model had read the page."""
    name = "fixtures"

    def __init__(self, fixtures_dir: Path):
        self.dir = fixtures_dir

    def ocr(self, image_jpeg: bytes, file_name: str, page: int) -> str:
        path = self.dir / f"{file_name}.p{page}.md"
        if not path.exists():
            raise OcrError(f"no fixture {path.name}")
        return path.read_text(encoding="utf-8").strip()


class PageCache:
    def __init__(self, cache_dir: Path):
        self.dir = cache_dir
        self.dir.mkdir(parents=True, exist_ok=True)

    def _path(self, sha256: str, page: int) -> Path:
        return self.dir / sha256[:2] / f"{sha256}.p{page}.md"

    def get(self, sha256: str, page: int) -> str | None:
        p = self._path(sha256, page)
        return p.read_text(encoding="utf-8") if p.exists() else None

    def put(self, sha256: str, page: int, markdown: str) -> None:
        p = self._path(sha256, page)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(markdown, encoding="utf-8")
        tmp.replace(p)  # atomic, so a crash never leaves half a page in the cache
