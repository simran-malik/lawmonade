"""API. Run: bash run.sh api  ->  http://localhost:8000/docs"""
import tempfile
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, UploadFile
from pydantic import BaseModel

from app import brief, digest, log, snapshot, store
from app.config import settings
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


# ---------- daily digest (n8n calls these; the dashboard button calls app.digest directly) ----------
class DigestRun(BaseModel):
    trigger: str = "scheduled"     # scheduled | manual
    actor: str = ""                # who asked (manual runs)
    dry_run: bool = False          # build + render only, send nothing
    force: bool = False            # manual only: send even if one went out a minute ago
    email_only: bool = False


def _check_key(x_api_key: str | None) -> None:
    """If DIGEST_API_KEY is set, sending needs it (n8n sends it as X-Api-Key). The API is internal either way."""
    if settings.digest_api_key and x_api_key != settings.digest_api_key:
        raise HTTPException(401, "Missing or wrong X-Api-Key.")


@app.get("/digest/matters")
def digest_matters():
    """Cases the daily digest covers (every case opened in the dashboard at least once)."""
    return digest.watched()


@app.post("/matters/{matter_id}/digest/run")
def digest_run(matter_id: str, body: DigestRun | None = None, x_api_key: str | None = Header(default=None)):
    """Build and send one case's digest. Safe to retry: a scheduled run is sent at most once per case per day.
    Returns status: sent | partial | failed | unavailable | skipped | already_sent | busy | cooldown | preview."""
    body = body or DigestRun()
    if body.trigger not in ("scheduled", "manual"):
        raise HTTPException(422, "trigger must be scheduled or manual")
    if not body.dry_run:
        _check_key(x_api_key)
    out = digest.run(matter_id, trigger=body.trigger, actor=body.actor or ("n8n" if body.trigger == "scheduled" else ""),
                     dry_run=body.dry_run, force=body.force, email_only=body.email_only)
    if out["status"] == "failed":
        raise HTTPException(502, out)          # n8n marks the item red (a retry is safe: same run key)
    return out


@app.get("/matters/{matter_id}/digest/runs")
def digest_runs(matter_id: str, limit: int = 10):
    return store.digest_runs(matter_id, limit)
