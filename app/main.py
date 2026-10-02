"""API. Run: bash run.sh api  ->  http://localhost:8000/docs"""
import tempfile
from pathlib import Path

from fastapi import FastAPI, HTTPException, UploadFile

from app import brief, log, snapshot
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


@app.get("/matters/{matter_id}/brief")
def matter_brief(matter_id: str):
    """The same case brief the dashboard shows (money cards with sources, review status), from the latest
    saved copy of the case. For n8n digests and other tools. Read-only: Clio is never called here."""
    snap = snapshot.load_saved(matter_id)
    if not snap:
        raise HTTPException(404, "No saved copy of this case yet. Open it once in the dashboard first.")
    return brief.build(snap)
