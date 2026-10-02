"""What a medical provider sees. Used for the attorney's preview AND the real provider page,
so the preview is exactly what the provider will get."""
from app.share import overdue
from app.snapshot import nice_date
from ui.theme import esc


def page(token: str) -> None:
    """The provider's page for one share link: only the approved, frozen copy. No Clio access, no case search."""
    import json

    import streamlit as st

    from app import store
    from app.config import settings
    from ui import theme
    ss = st.session_state
    st.markdown(f'<div class="lm-bar"><div class="lm-brand">{esc(settings.firm_name)}'
                f'<small>Secure case update · read-only</small></div>'
                f'<div><span class="lm-badge">SHARED WITH YOU</span></div></div>', unsafe_allow_html=True)
    sh = store.get_share(token)
    if not sh:
        theme.error_box("This link has expired or was turned off.",
                        "Contact the law firm and ask for a new link.")
        return
    if not ss.get("viewed_" + token):          # count each visit once
        store.record_view(token, "provider page")
        ss["viewed_" + token] = True
    _, mid, _ = st.columns([1, 3, 1])
    with mid:
        st.markdown(html(json.loads(sh["edited_text"])), unsafe_allow_html=True)


def _usd(x) -> str:
    return "—" if x is None else f"${x:,.0f}"


def html(p: dict) -> str:
    out = [f'<div class="lm-pv"><h2>{esc(p.get("client"))}: case update for {esc(p.get("provider"))}</h2>'
           f'<div class="lm-foot" style="margin-top:0">From {esc(p.get("firm"))} · prepared {esc(nice_date(p.get("made")))}</div>']

    if p.get("message"):
        out.append(f'<div class="lm-msg" style="margin-top:0.8rem">{esc(p["message"])}</div>')

    if "status" in p:
        s = p["status"]
        if s.get("active"):
            out.append(f'<div class="lm-status on"><div class="big">● Active</div><div>The case is open and moving. '
                       f'Current stage: <b>{esc(s.get("stage"))}</b>.</div></div>')
        else:
            out.append(f'<div class="lm-status off"><div class="big">● Not active</div><div>This case is '
                       f'<b>{esc(s.get("status"))}</b> (stage: {esc(s.get("stage"))}). Contact the firm about any balance.</div></div>')

    if "needs" in p:
        rows = "".join(
            f'<div class="lm-need"><b>{esc(n["what"])}</b>'
            + (f'<span class="lm-late">{"OVERDUE · " if overdue(n.get("due")) else ""}due {esc(nice_date(n.get("due")))}</span>' if n.get("due") else "")
            + (f'<div class="lm-srcline">{esc(n["detail"])}</div>' if n.get("detail") else "") + "</div>"
            for n in p["needs"]) or "Nothing right now. Thank you."
        out.append(f'<div class="lm-sec"><div class="lm-label">What we need from your office</div>{rows}</div>')

    if "bills" in p:
        b = p["bills"]
        if b.get("low") is None:
            body = "We don't have a bill amount from your office yet. Please send your itemized bill."
        else:
            body = f'<div class="lm-range">{_usd(b["low"])} – {_usd(b["high"])}</div>'
        out.append(f'<div class="lm-sec"><div class="lm-label">Expected payment range</div>{body}</div>')

    if "records" in p:
        rows = "".join(f'<div class="lm-need">{esc(r["name"])}'
                       f'<span class="lm-srcline"> · received {esc(nice_date(r.get("date")))}</span></div>' for r in p["records"])
        out.append(f'<div class="lm-sec"><div class="lm-label">Records we have from you</div>'
                   f'{rows or "We have not received records from your office yet."}</div>')

    if "coverage" in p:
        out.append(f'<div class="lm-sec"><div class="lm-label">Insurance coverage behind the case</div>'
                   f'{esc(p["coverage"] or "Not confirmed yet.")}</div>')

    out.append('<div class="lm-foot">This page is read-only and shows only what the law firm chose to share. '
               'Questions? Reply to the firm\'s email.</div></div>')
    return "".join(out)


# ---------- the email: only the attorney's message + the secure link (no case details) ----------
def link_email_text(message: str, link: str, expires: str) -> str:
    return (f"{message.strip()}\n\n"
            f"Open your secure case update here (works until {expires}):\n{link}\n\n"
            f"For privacy, case details are not included in this email.")


def link_email_html(message: str, link: str, expires: str, firm: str) -> str:
    navy, gold, muted = "#13294B", "#C9A227", "#475467"
    return (f'<div style="font-family:Arial,Helvetica,sans-serif;font-size:15px;color:#0F1B2D;max-width:600px">'
            f'<div style="background:{navy};color:#fff;padding:14px 18px;border-radius:10px 10px 0 0;'
            f'border-bottom:4px solid {gold};font-family:Georgia,serif;font-size:20px;font-weight:700">{esc(firm)}</div>'
            f'<div style="padding:16px 4px"><div style="white-space:pre-wrap">{esc(message.strip())}</div>'
            f'<p style="margin:22px 0"><a href="{esc(link)}" style="background:{navy};color:#fff;padding:12px 20px;'
            f'border-radius:8px;text-decoration:none;font-weight:700">Open secure case update</a></p>'
            f'<p style="color:{muted};font-size:13px">The link works until {esc(expires)}. For privacy, case details '
            f'are not included in this email.</p></div></div>')
