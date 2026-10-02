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
            body = (f'<div class="lm-range">{_usd(b["low"])} – {_usd(b["high"])}</div>'
                    f'<div>Expected payment from the settlement. You billed <b>{_usd(b["billed"])}</b>. '
                    f'The final amount is set when the case settles, and bills are often reduced at that point.</div>')
        out.append(f'<div class="lm-sec"><div class="lm-label">Your bills</div>{body}</div>')

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
