"""Find input files and turn each into pages: PDF pages with a text layer keep their text, the rest
become JPEG images for OCR."""
from __future__ import annotations

import hashlib
import io
import re
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff", ".bmp"}
PDF_EXT = {".pdf"}
MAX_DIM = 1800           # longest side sent to the model, as in the official typhoon-ocr client
MIN_TEXT_CHARS = 80      # a PDF page with fewer extracted letters than this is treated as scanned
THAI_OR_LATIN = re.compile(r"[฀-๿a-zA-Z]")
# Above/below vowels and tone marks must follow a consonant (or another such mark). Many Thai PDFs
# have a text layer whose marks come out detached ("ส นักงาน", "ผ ื ชนะ"): text that looks
# present but is wrong. Too many orphan marks -> treat the page as scanned and OCR it.
_THAI_MARK = "ัิ-ฺ็-๎"
_ORPHAN_MARK = re.compile(rf"(?:^|(?<=[^ก-ฮ{_THAI_MARK}]))[{_THAI_MARK}]", re.M)
_THAI_CHAR = re.compile(r"[ก-๛]")
MAX_ORPHAN_RATIO = 0.005


def text_layer_is_usable(text: str) -> bool:
    if len(THAI_OR_LATIN.findall(text)) < MIN_TEXT_CHARS:
        return False
    thai = len(_THAI_CHAR.findall(text))
    if thai == 0:
        return True
    if "�" in text:
        return False
    return len(_ORPHAN_MARK.findall(text)) / thai <= MAX_ORPHAN_RATIO


@dataclass
class Page:
    number: int                    # 1-based
    image_jpeg: bytes | None = None
    text: str | None = None        # set when the PDF already has a usable text layer


@dataclass
class SourceFile:
    path: Path
    sha256: str
    kind: str                      # "pdf" | "image"
    pages: list[Page] = field(default_factory=list)

    @property
    def name(self) -> str:
        return self.path.name


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def discover(input_dir: Path) -> list[SourceFile]:
    files = []
    for p in sorted(input_dir.rglob("*")):
        if not p.is_file() or p.name.startswith("."):
            continue
        ext = p.suffix.lower()
        if ext in PDF_EXT:
            files.append(SourceFile(p, sha256_of(p), "pdf"))
        elif ext in IMAGE_EXT:
            files.append(SourceFile(p, sha256_of(p), "image"))
    return files


def _to_jpeg(img: Image.Image) -> bytes:
    img = img.convert("RGB")
    w, h = img.size
    scale = min(1.0, MAX_DIM / max(w, h))
    if scale < 1.0:
        img = img.resize((round(w * scale), round(h * scale)), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=92)
    return buf.getvalue()


def load_pages(src: SourceFile, force_ocr: bool = False, max_pages: int = 200) -> list[Page]:
    if src.kind == "image":
        with Image.open(src.path) as img:
            return [Page(1, image_jpeg=_to_jpeg(img))]

    import pypdfium2 as pdfium  # imported lazily: only needed for PDFs

    pages: list[Page] = []
    pdf = pdfium.PdfDocument(str(src.path))
    try:
        for i in range(min(len(pdf), max_pages)):
            page = pdf[i]
            text = ""
            if not force_ocr:
                tp = page.get_textpage()
                text = tp.get_text_range() or ""
                tp.close()
            if text_layer_is_usable(text):
                pages.append(Page(i + 1, text=text.replace("\r\n", "\n")))
            else:
                w, h = page.get_size()
                scale = MAX_DIM / max(w, h)
                pil = page.render(scale=scale).to_pil()
                pages.append(Page(i + 1, image_jpeg=_to_jpeg(pil)))
            page.close()
    finally:
        pdf.close()
    return pages
