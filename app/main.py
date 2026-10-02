"""API. Run: bash run.sh api  ->  http://localhost:8000/docs"""
import tempfile
from pathlib import Path

from fastapi import FastAPI, UploadFile

from app import log
from app.pdf import read_pdf

log.setup()

app = FastAPI(title="Law-monade API")


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/pdf/text")
async def pdf_text(file: UploadFile):
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / file.filename
        path.write_bytes(await file.read())
        return read_pdf(path)
