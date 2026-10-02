"""What a medical provider sees. Used for the attorney's preview AND the real provider page,
so the preview is exactly what the provider will get."""
from app.share import overdue
from app.snapshot import nice_date
from ui.theme import esc


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
        if b.get("billed") is None:
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


# ---------- email versions (inline styles: email apps ignore page CSS) ----------
def email_text(p: dict, link: str, expires: str) -> str:
    lines = [p.get("message", ""), ""]
    if "status" in p:
        s = p["status"]
        lines.append(f"CASE STATUS: {'Active' if s.get('active') else 'Not active'} (stage: {s.get('stage')})")
    if "needs" in p:
        lines.append("WHAT WE NEED FROM YOUR OFFICE:")
        lines += [f"  - {n['what']}" + (f" (due {nice_date(n.get('due'))})" if n.get("due") else "") for n in p["needs"]] or ["  - Nothing right now."]
    if "bills" in p:
        b = p["bills"]
        lines.append("EXPECTED PAYMENT RANGE: " + (f"{_usd(b['low'])} - {_usd(b['high'])}" if b.get("billed") is not None
                                                  else "please send your itemized bill"))
    if "records" in p:
        lines.append("RECORDS WE HAVE FROM YOU:")
        lines += [f"  - {r['name']}" for r in p["records"]] or ["  - None yet."]
    if "coverage" in p:
        lines.append(f"INSURANCE COVERAGE: {p['coverage']}")
    lines += ["", f"View this update online (link works until {expires}): {link}"]
    return "\n".join(lines)


def email_html(p: dict, link: str, expires: str) -> str:
    navy, gold, muted = "#13294B", "#C9A227", "#475467"
    sec = lambda title, body: (f'<div style="border:1px solid #D0D5DD;border-radius:10px;padding:12px 16px;margin:12px 0">'
                               f'<div style="font-size:12px;font-weight:700;letter-spacing:.08em;color:{muted};text-transform:uppercase">'
                               f'{esc(title)}</div>{body}</div>')
    out = [f'<div style="font-family:Arial,Helvetica,sans-serif;font-size:15px;color:#0F1B2D;max-width:640px">'
           f'<div style="background:{navy};color:#fff;padding:14px 18px;border-radius:10px 10px 0 0;border-bottom:4px solid {gold};'
           f'font-family:Georgia,serif;font-size:20px;font-weight:700">{esc(p.get("firm"))}</div>'
           f'<div style="padding:16px 4px">'
           f'<div style="white-space:pre-wrap">{esc(p.get("message"))}</div>']
    if "status" in p:
        s = p["status"]
        color = "#067647" if s.get("active") else "#B42318"
        out.append(sec("Case status", f'<div style="font-size:20px;font-weight:700;color:{color}">● '
                                      f'{"Active" if s.get("active") else "Not active"}</div>Stage: <b>{esc(s.get("stage"))}</b>'))
    if "needs" in p:
        rows = "".join(f'<li><b>{esc(n["what"])}</b>' + (f' (due {esc(nice_date(n.get("due")))})' if n.get("due") else "") + "</li>"
                       for n in p["needs"]) or "<li>Nothing right now.</li>"
        out.append(sec("What we need from your office", f"<ul style='margin:6px 0'>{rows}</ul>"))
    if "bills" in p:
        b = p["bills"]
        body = (f'<div style="font-size:22px;font-weight:700;color:{navy}">{_usd(b["low"])} – {_usd(b["high"])}</div>'
                if b.get("billed") is not None else "Please send your itemized bill.")
        out.append(sec("Expected payment range", body))
    if "records" in p:
        rows = "".join(f"<li>{esc(r['name'])}</li>" for r in p["records"]) or "<li>None yet.</li>"
        out.append(sec("Records we have from you", f"<ul style='margin:6px 0'>{rows}</ul>"))
    if "coverage" in p:
        out.append(sec("Insurance coverage", esc(p["coverage"])))
    out.append(f'<p><a href="{esc(link)}" style="background:{navy};color:#fff;padding:10px 16px;border-radius:8px;'
               f'text-decoration:none;font-weight:700">View this update online</a></p>'
               f'<p style="color:{muted};font-size:13px">The link works until {esc(expires)}. This update shows only what the firm '
               f'chose to share.</p></div></div>')
    return "".join(out)
