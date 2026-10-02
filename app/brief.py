"""The case brief, built in ONE place for every front end: the dashboard, the API (GET /matters/{id}/brief)
and scheduled digests. No Streamlit here, and building a brief never writes to the database:
only a person's click (approve, correct) does.

build(snap) -> {"matter", "source", "fetched_at", "cards", "liens_status", "risks", "counts"}
risks = app.risks.build(snap): the case's top 1-2 risks for its stage (red / amber / green, each with a why line).
"""
from app import liens, risks, snapshot, store
from app.kpis import apply_edits, apply_reviews, kpis


def build(snap: dict, lien_analysis: dict | None = None, risk_report: dict | None = None) -> dict:
    """Money cards (with corrections and review status), lien status and item counts for one case snapshot.
    lien_analysis: pass a result you already have (the dashboard keeps one per session); else it's computed
    (the AI answer is cached on disk, so this is cheap after the first time). risk_report: the same, for risks."""
    mid = snap["matter"]["id"]
    la = lien_analysis if lien_analysis is not None else liens.analyze(snap)
    cards = apply_reviews(apply_edits(kpis(snap, la), store.card_edits(mid)), store.card_reviews(mid))
    return {"matter": snap["matter"], "source": snap.get("source"), "fetched_at": snap.get("fetched_at"),
            "cards": cards, "liens_status": la.get("status"),
            "risks": risk_report if risk_report is not None else risks.build(snap), "counts": snapshot.counts(snap)}
