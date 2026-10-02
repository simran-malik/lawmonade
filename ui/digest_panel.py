"""Daily digest bar on the Case brief tab: when the last digest went out, a preview, and "Send digest now".

The button sends exactly what is on screen (this copy of the case), through the same code as the n8n schedule
(app.digest.run), so the email's numbers and risks always match the cards below. Nothing is sent from the preview.
"""
import streamlit as st
import streamlit.components.v1 as components

from app import digest, store
from app.config import settings
from ui.theme import esc

ss = st.session_state
WORDS = {"sent": ("lm-ok", "✓"), "not_urgent": ("muted", "not needed (nothing urgent)"), "skipped": ("muted", "not sent"),
         "not_set_up": ("lm-meh", "not set up"), "no_recipients": ("lm-bad", "no recipient"),
         "failed": ("lm-bad", "failed"), "partial": ("lm-meh", "partly sent"), "unknown": ("lm-meh", "maybe sent (check)")}


def _ch(status: str) -> str:
    cls, word = WORDS.get(status or "", ("muted", status or "—"))
    return f'<span class="{cls}">{esc(word)}</span>'


def last_line(mid) -> str:
    r = store.last_digest(mid)
    if not r:
        return '<span class="muted">No digest sent for this case yet. The schedule sends one every weekday morning.</span>'
    who = "the morning schedule" if r["trigger"] == "scheduled" else (r["actor"] or "the Send button")
    when = digest.local_time(r.get("finished_at") or r["started_at"])
    if r["status"] == "running":
        return f"Sending now (started {esc(when)})…"
    return (f"Last digest: <b>{esc(when)}</b> by {esc(who)} · Email {_ch(r['email_status'])}"
            f"{' to ' + esc(r['recipients']) if r['recipients'] else ''} · Slack {_ch(r['slack_status'])}"
            + (f'<br><span class="muted">{esc(r["error"])}</span>' if r.get("error") and r["status"] != "sent" else ""))


RISK_CLASS = {"red": "lm-bad", "amber": "lm-meh", "review": "lm-meh", "unknown": "muted", "green": "lm-ok"}


def risks_line(rep: dict | None) -> str:
    """What today's digest flags (the same top 1-2 risks as the cards below)."""
    if not rep:
        return ""
    top = rep["top"]
    if not top:
        return '<br>Risks in the digest: <span class="lm-ok">nothing flagged</span>'
    return "<br>Risks in the digest: " + " · ".join(
        f'<span class="{RISK_CLASS[r["level"]]}">{esc(r["level_words"])}</span> {esc(r["label"])}: <b>{esc(r["value"])}</b>'
        for r in top)


def render(s: dict, lien_analysis: dict, risk_report: dict | None = None):
    mid = s["matter"]["id"]
    rc = digest.recipients(s)
    to = ", ".join(rc["to"]) or "nobody yet"
    warn = "" if rc["to"] else (' <span class="lm-bad">Set DIGEST_RECIPIENTS in .env (or the responsible attorney '
                                'in Clio) so it has somewhere to go.</span>')
    dropped = (f' <span class="lm-meh">Left out (not a firm address): {esc(", ".join(rc["dropped"]))}</span>'
               if rc["dropped"] else "")
    if not ss.get("digest_send"):          # pop-up closed with its X: forget the old result
        ss.pop(f"digest_result_{mid}", None)
        ss.pop(f"digest_confirm_{mid}", None)
    a, b, c = st.columns([5, 1.2, 1.4])
    with a:
        st.markdown(f'<div class="lm-digest"><b>Daily digest</b> <span class="muted">· email every weekday morning, '
                    f'Slack only for urgent items · goes to {esc(to)}</span>{warn}{dropped}<br>{last_line(mid)}'
                    f'{risks_line(risk_report)}</div>',
                    unsafe_allow_html=True)
    with b:
        if st.button("Preview digest", key="digest_preview", use_container_width=True,
                     help="See the email and the Slack message. Nothing is sent."):
            preview_dialog(s, lien_analysis, risk_report)
    with c:
        if st.button("Send digest now", key="digest_send", type="primary", use_container_width=True,
                     help="Send today's digest for this case now (same as the morning schedule)"):
            send_dialog(s, lien_analysis, risk_report)


def _preview(s: dict, lien_analysis: dict, risk_report: dict | None = None) -> dict:
    """Built once per copy of the case (the AI summary is cached on disk too)."""
    mid = s["matter"]["id"]
    reviews = hash(repr(sorted(store.card_reviews(mid).items())) + repr(sorted(store.card_edits(mid).items())))
    key = f"digest_prev_{mid}_{s.get('fetched_at')}_{reviews}"      # an approval changes the numbers' labels
    if key not in ss:
        with st.spinner("Writing the summary (AI, then checked against Clio)…"):
            ss[key] = digest.run(s["matter"]["id"], "manual", snap=s, dry_run=True, lien_analysis=lien_analysis,
                                 timeout=settings.llm_ui_timeout_s, risk_report=risk_report)
    return ss[key]


def _show(p: dict):
    if p["status"] != "preview":
        st.warning(p.get("message", "The digest could not be made."))
        return
    em, sl = p["email"], p["slack"]
    st.markdown(f"**To:** {esc(', '.join(em['to']) or 'nobody (set DIGEST_RECIPIENTS)')}  \n**Subject:** {esc(em['subject'])}")
    t1, t2 = st.tabs(["Email", "Slack"])
    with t1:
        components.html(em["html"], height=620, scrolling=True)
    with t2:
        if sl["text"]:
            st.code(sl["text"], language=None)
            st.caption("Counts only: no names, amounts or medical details go to Slack.")
        else:
            st.info("No Slack ping today: nothing is overdue or due within a day.")


@st.dialog("Daily digest preview", width="large")
def preview_dialog(s: dict, lien_analysis: dict, risk_report: dict | None = None):
    _show(_preview(s, lien_analysis, risk_report))


@st.dialog("Send today's digest", width="large")
def send_dialog(s: dict, lien_analysis: dict, risk_report: dict | None = None):
    mid = s["matter"]["id"]
    who = (ss.get("who") or "").strip()                    # optional "Reviewing as" name, only for the audit log
    res_key = f"digest_result_{mid}"
    if ss.get(res_key):                                     # already sent from this pop-up: show the result
        r = ss[res_key]
        (st.success if r["status"] == "sent" else st.warning)(r["message"])
        if st.button("Close", use_container_width=True):
            ss.pop(res_key, None)
            st.rerun()
        return
    p = _preview(s, lien_analysis, risk_report)
    if p["status"] == "preview":
        urgent = bool(p["slack"]["text"])
        st.markdown(f"Email to **{esc(', '.join(p['email']['to']) or 'nobody')}**"
                    + (" and a Slack ping (something is urgent)." if urgent else ". No Slack ping: nothing urgent."))
        st.caption(f"Uses the case as shown on screen (data from {digest.local_time(s.get('fetched_at'))}). "
                   "Click “Refresh from Clio” first for the newest data.")
    email_only = st.toggle("Email only (no Slack)", value=False)
    force = ss.get(f"digest_confirm_{mid}", False)
    if force:
        st.warning(ss.get(f"digest_confirm_msg_{mid}", "A digest was just sent. Send another one?"))
    label = "Yes, send again" if force else "Send now"
    if st.button(label, key="digest_send_confirm", type="primary", use_container_width=True,
                 disabled=ss.get("digest_busy", False)):
        ss["digest_busy"] = True                            # one click = one send, even if clicked twice
        try:
            with st.spinner("Sending…"):
                r = digest.run(mid, "manual", actor=who, snap=s, lien_analysis=lien_analysis, force=force,
                               email_only=email_only, timeout=settings.llm_ui_timeout_s, risk_report=risk_report)
        finally:
            ss["digest_busy"] = False
        if r["status"] == "cooldown":
            ss[f"digest_confirm_{mid}"], ss[f"digest_confirm_msg_{mid}"] = True, r["message"]
            st.rerun(scope="fragment")
        ss.pop(f"digest_confirm_{mid}", None)
        ss[res_key] = r
        st.rerun(scope="fragment")
    with st.expander("See what will be sent"):
        _show(p)
