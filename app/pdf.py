"""PDF + OCR helpers.

read_pdf(path)          -> [{"page", "text", "scanned"}]
pdf_words(path, page)   -> [{"text", "conf", "box"}]  words from a digital PDF (conf = 100)
page_png(path, page)    -> PNG bytes of one page
ocr_words(png)          -> [{"text", "conf", "box"}]  Tesseract words with confidence 0-100
page_words(path, page)  -> digital words if the page has text, else OCR words
"""
import io
from pathlib import Path

import fitz  # PyMuPDF

MIN_TEXT_CHARS = 40


def read_pdf(path: str | Path) -> list[dict]:
    with fitz.open(path) as doc:
        out = []
        for i, p in enumerate(doc, start=1):
            text = p.get_text("text").strip()
            out.append({"page": i, "text": text, "scanned": len(text) < MIN_TEXT_CHARS})
        return out


def pdf_words(path: str | Path, page: int) -> list[dict]:
    with fitz.open(path) as doc:
        return [{"text": w[4], "conf": 100, "box": (w[0], w[1], w[2] - w[0], w[3] - w[1])}
                for w in doc[page - 1].get_text("words")]


def page_png(path: str | Path, page: int, dpi: int = 300) -> bytes:
    with fitz.open(path) as doc:
        return doc[page - 1].get_pixmap(dpi=dpi).tobytes("png")


def ocr_words(png: bytes) -> list[dict]:
    import pytesseract
    from PIL import Image

    d = pytesseract.image_to_data(Image.open(io.BytesIO(png)), output_type=pytesseract.Output.DICT)
    return [{"text": t, "conf": float(c), "box": (x, y, w, h)}
            for t, c, x, y, w, h in zip(d["text"], d["conf"], d["left"], d["top"], d["width"], d["height"])
            if t.strip()]


def page_words(path: str | Path, page: int) -> list[dict]:
    words = pdf_words(path, page)
    if sum(len(w["text"]) for w in words) >= MIN_TEXT_CHARS:
        return words
    return ocr_words(page_png(path, page))
