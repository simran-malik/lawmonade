"""Daily case digest: one email per case every weekday morning, plus a Slack ping ONLY when something is urgent.
The same code runs for the n8n schedule (POST /matters/{id}/digest/run) and the "Send digest now" button.

run(matter_id, trigger="scheduled" | "manual", actor="", snap=None, dry_run=False, force=False, email_only=False)
  1. Claim the run (app.store.claim_digest). Scheduled runs use one key per case per firm day, so an n8n retry or
     a second server can never send twice. Manual runs get their own key, with a cooldown question instead.
  2. Get the case: `snap` from the dashboard (exactly what the person is looking at), else a fresh read from Clio,
     else the newest saved copy WITH its age. If that copy is older than DIGEST_MAX_AGE_H, we send a short
     "digest unavailable" note instead of old numbers (silence or stale numbers would both mislead).
  3. build(): the numbers and the case risks come from app.brief.build (the same function as the Case brief tab,
     so they always match), plus deadlines (app.deadlines), the checked summary (app.summary) and what changed since the last
     digest (dated snapshots).
  4. Send: email always (to the responsible attorney in Clio, else DIGEST_RECIPIENTS, only allowed domains);
     Slack only if urgent, with counts only (no names, amounts or medical details). Each channel's result is
     saved; a retry only redoes channels that didn't go out. A timeout or a 500 means "maybe sent": it is
     recorded as "unknown" and NOT resent automatically (better one missing message than two).
Clio is only read, never written.
"""
import html
import secrets
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app import brief, deadlines, retry, snapshot, store, summary
from app.config import settings
from app.log import get, new_run, stage

LOG = get("digest")
CLOSED = ("closed", "archived")


# ---------- small helpers ----------
def firm_day() -> str:
    return datetime.now(ZoneInfo(settings.timezone)).date().isoformat()


def age_h(iso: str | None) -> float | None:
    try:
        return round((datetime.now(timezone.utc) - datetime.fromisoformat(str(iso))).total_seconds() / 3600, 1)
    except (TypeError, ValueError):
        return None


def _secs_since(iso: str) -> float:
    try:
        return (datetime.now(timezone.utc) - datetime.fromisoformat(iso)).total_seconds()
    except (TypeError, ValueError):
        return float("inf")


def local_time(iso: str | None) -> str:
    try:
        return datetime.fromisoformat(str(iso)).astimezone(ZoneInfo(settings.timezone)).strftime("%b %-d, %-I:%M %p")
    except (TypeError, ValueError):
        return ""


def _csv(s: str) -> list[str]:
    return [x.strip() for x in str(s or "").split(",") if x.strip()]


def recipients(snap: dict) -> dict:
    """{"to": [...], "dropped": [...], "why": "..."}: the responsible attorney in Clio, else DIGEST_RECIPIENTS.
    Addresses outside FIRM_EMAIL_DOMAINS are dropped (case details must not leave the firm)."""
    att = ((snap.get("matter") or {}).get("attorney") or {})
    if "@" in (att.get("email") or ""):
        cands, why = [att["email"]], f"responsible attorney in Clio ({att.get('name') or att['email']})"
    else:
        cands, why = _csv(settings.digest_recipients), "DIGEST_RECIPIENTS in .env (no responsible attorney email in Clio)"
    domains = [d.lower().lstrip("@") for d in _csv(settings.firm_email_domains)]
    to, dropped = [], []
    for a in dict.fromkeys(cands):
        ok = "@" in a and (not domains or a.rsplit("@", 1)[1].lower() in domains)
        (to if ok else dropped).append(a)
    return {"to": to, "dropped": dropped, "why": why}


# ---------- what changed since the last digest ----------
LIST_LABELS = {"notes": ("note", "notes"), "communications": ("email or call", "emails and calls"),
               "tasks": ("task", "tasks"), "calendar": ("calendar entry", "calendar entries"),
               "documents": ("document", "documents"), "expenses": ("expense", "expenses")}


def baseline(snap: dict) -> dict | None:
    """The copy of the case the last sent digest was built from; else the newest dated copy at least 20 h older."""
    mid = snap["matter"]["id"]
    last = store.last_digest(mid, sent_only=True)
    if last and last.get("snapshot_fetched_at") and last["snapshot_fetched_at"] != snap.get("fetched_at"):
        b = snapshot.load_version(mid, last["snapshot_fetched_at"])
        if b:
            return b
    try:
        cutoff = datetime.fromisoformat(snap["fetched_at"]) - timedelta(hours=20)
    except (KeyError, TypeError, ValueError):
        return None
    for p in reversed(snapshot.versions(mid)):
        try:
            when = datetime.strptime(p.stem, "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        if when <= cutoff:
            return snapshot.load_version(mid, when.isoformat())
    return None


def changes(snap: dict, base: dict | None) -> dict:
    if not base:
        return {"since": None, "lines": []}
    lines = []
    for k, (one, many) in LIST_LABELS.items():
        old = {str(i.get("id")) for i in base.get(k, [])}
        new = [i for i in snap.get(k, []) if str(i.get("id")) not in old]
        if new:
            line = f"{len(new)} new {one if len(new) == 1 else many}"
            if k in ("tasks", "calendar"):
                line += ": " + "; ".join(deadlines.what(i.get("title")) for i in new[:3]) + (" …" if len(new) > 3 else "")
            lines.append(line)
    from app.share import is_open
    was_open = {str(t.get("id")) for t in base.get("tasks", []) if is_open(t)}
    done = [t for t in snap.get("tasks", []) if str(t.get("id")) in was_open and not is_open(t)]
    lines += [f"Task completed: {deadlines.what(t.get('title'))}" for t in done[:5]]
    of, nf = base.get("fields") or {}, snap.get("fields") or {}
    changed = [k for k in nf if k in of and nf[k] != of[k]] + [k for k in nf if k not in of]
    if changed:
        lines.append("Clio fields changed: " + ", ".join(changed[:6]) + (" …" if len(changed) > 6 else ""))
    return {"since": base.get("fetched_at"), "lines": lines}


# ---------- build ----------
def review_text(card: dict) -> str:
    rv = card.get("review") or {}
    st_ = rv.get("status")
    if st_ == "needs_review":
        return "Needs review"
    if st_ == "approved":
        return f"Last reviewed by {rv.get('by') or 'a team member'}"
    if st_ == "corrected":
        return f"Last reviewed by {rv.get('by') or 'a team member'} (corrected)"
    return "Checked by code"


def _risk(r: dict) -> dict:
    return {k: r.get(k) for k in ("key", "label", "level", "level_words", "value", "why", "scope")} | \
        {"url": (r.get("link") or {}).get("url", "")}


def risk_part(rep: dict) -> dict:
    """The case risks (app/risks.py) as the digest shows them: the top 1-2, then the other checks."""
    top = [_risk(r) for r in rep["top"]]
    keys = {r["key"] for r in top}
    return {"stage": rep["stage"], "set_up": rep["set_up"], "note": rep["note"], "top": top,
            "others": [_risk(r) for r in rep["signals"] if r["key"] not in keys],
            "red": [r["label"] for r in rep["signals"] if r["level"] == "red"]}


def build(snap: dict, lien_analysis: dict | None = None, timeout: float | None = None, summary_ask=None,
          stale_reason: str = "", risk_report: dict | None = None) -> dict:
    """Everything one digest says, as plain JSON (also returned by the API)."""
    b = brief.build(snap, lien_analysis, risk_report)
    dl = deadlines.lists(snap)
    reasons = deadlines.urgent(dl)
    m = snap["matter"]
    with stage("digest.summary", LOG) as info:
        summ = summary.summarize(snap, timeout=timeout, ask=summary_ask)
        info.update(mode=summ["mode"], sentences=len(summ["sentences"]), dropped=summ["dropped"])
    return {
        "matter": {k: m.get(k) for k in ("id", "number", "client", "description", "stage", "status", "practice_area",
                                          "open_date", "url")},
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": snap.get("source"), "data_as_of": snap.get("fetched_at"), "data_age_h": age_h(snap.get("fetched_at")),
        "stale_reason": stale_reason,
        "summary": summ,
        "cards": [{"key": c["key"], "label": c["label"], "value": c["value"], "amount": c.get("amount"),
                   "review": review_text(c), "review_status": (c.get("review") or {}).get("status"),
                   "sure": c["sure"][1], "why": c.get("why", "")} for c in b["cards"]],
        "liens_status": b["liens_status"], "counts": b["counts"], "risks": risk_part(b["risks"]),
        "deadlines": dl, "changes": changes(snap, baseline(snap)),
        "urgent": reasons, "recipients": recipients(snap),
    }


# ---------- render ----------
NAVY, GOLD, MUTED, LINE, AMBER, RED, GREEN, BLUE = ("#13294B", "#C9A227", "#475467", "#D0D5DD", "#B54708",
                                                    "#B42318", "#067647", "#175CD3")
e = html.escape


def _cap(items: list, n: int | None = None) -> tuple[list, int]:
    n = n or settings.digest_list_max
    return items[:n], max(0, len(items) - n)


def _h2(text: str) -> str:
    return (f'<h2 style="font-family:Georgia,serif;color:{NAVY};font-size:18px;margin:22px 0 8px;'
            f'border-bottom:2px solid {GOLD};padding-bottom:4px">{e(text)}</h2>')


def _a(url: str, text: str, color: str = BLUE) -> str:
    return f'<a href="{e(url)}" style="color:{color};font-weight:600">{e(text)}</a>' if url else e(text)


def _contact_html(c: dict | None) -> str:
    if not c:
        return f'<span style="color:{MUTED}">No contact found in Clio</span>'
    links = []
    if c.get("sms_url"):
        links.append(_a(c["sms_url"], f"Text {c['phone']}"))
    if c.get("mail_url"):
        links.append(_a(c["mail_url"], "Email"))
    if not links:
        links.append(f'<span style="color:{MUTED}">No phone or email in Clio</span>')
    return (f'<b>{e(c["name"])}</b><br><span style="color:{MUTED};font-size:12px">{e(c["role"])}</span><br>'
            + " · ".join(links))


def _late(days: int) -> str:
    d = -days
    return f"{d} day{'s' if d != 1 else ''} late"


def _rows(items: list[dict], overdue: bool) -> str:
    out = ""
    for it in items:
        when = _late(it["days"]) if overdue else ("today" if it["days"] == 0 else
                                                   "tomorrow" if it["days"] == 1 else f"in {it['days']} days")
        src = _a(it["src"].get("url", ""), "Open in Clio", MUTED) if it["src"].get("url") else ""
        out += (f'<tr><td style="padding:8px 6px;border-bottom:1px solid {LINE};white-space:nowrap;vertical-align:top">'
                f'<b>{e(it["nice"])}</b><br><span style="color:{RED if overdue else MUTED};font-size:12px;font-weight:700">'
                f'{e(when)}</span></td>'
                f'<td style="padding:8px 6px;border-bottom:1px solid {LINE};vertical-align:top">'
                f'<span style="font-size:11px;color:{MUTED};text-transform:uppercase;font-weight:700">{e(it["kind"])}</span><br>'
                f'{e(it["title"])}<br><span style="font-size:12px">{src}</span></td>'
                + (f'<td style="padding:8px 6px;border-bottom:1px solid {LINE};vertical-align:top;font-size:13px">'
                   f'{_contact_html(it.get("contact"))}</td>' if overdue else "")
                + "</tr>")
    return out


def _table(items: list[dict], overdue: bool) -> str:
    shown, more = _cap(items)
    head = ("<th align=left style='padding:4px 6px'>Due</th><th align=left style='padding:4px 6px'>What</th>"
            + ("<th align=left style='padding:4px 6px'>Who to contact</th>" if overdue else ""))
    t = (f'<table style="width:100%;border-collapse:collapse;font-size:14px"><tr style="color:{MUTED};font-size:12px">'
         f'{head}</tr>{_rows(shown, overdue)}</table>')
    return t + (f'<p style="color:{MUTED};font-size:13px">and {more} more in the dashboard.</p>' if more else "")


RISK_COLORS = {"red": (RED, "#FEF3F2"), "amber": (AMBER, "#FFFAEB"), "review": ("#5925DC", "#F4F3FF"),
               "unknown": (MUTED, "#F9FAFB"), "green": (GREEN, "#F6FEF9")}


def _risks_html(r: dict) -> str:
    """'What could hurt this case': the top 1-2 risks as colored boxes, then the other checks in one small table."""
    out = [_h2("What could hurt this case")]
    if r.get("note"):
        out.append(f'<p style="color:{MUTED};font-size:13px;margin:0 0 6px">{e(r["note"])}</p>')
    if not r["top"]:
        out.append(f'<p style="color:{GREEN};font-weight:600">Nothing flagged today.</p>')
    for x in r["top"]:
        fg, bg = RISK_COLORS[x["level"]]
        out.append(f'<div style="border-left:5px solid {fg};background:{bg};padding:8px 12px;border-radius:6px;margin:6px 0">'
                   f'<span style="color:{fg};font-size:12px;font-weight:700;text-transform:uppercase">{e(x["level_words"])}</span>'
                   f' · <b>{e(x["label"])}</b>: <b style="color:{NAVY}">{e(x["value"])}</b><br>{e(x["why"])}'
                   + (f' <span style="font-size:12px">{_a(x["url"], "Open in Clio", MUTED)}</span>' if x.get("url") else "")
                   + "</div>")
    if r["others"]:
        rows = "".join(
            f'<tr><td style="padding:5px 6px;border-bottom:1px solid {LINE};color:{RISK_COLORS[x["level"]][0]};'
            f'font-weight:700;font-size:12px;white-space:nowrap">{e(x["level_words"])}</td>'
            f'<td style="padding:5px 6px;border-bottom:1px solid {LINE}">{e(x["label"])}</td>'
            f'<td style="padding:5px 6px;border-bottom:1px solid {LINE};font-weight:600;white-space:nowrap">{e(x["value"])}</td></tr>'
            for x in r["others"])
        out.append(f'<p style="margin:10px 0 2px;color:{MUTED};font-size:13px">Other checks</p>'
                   f'<table style="width:100%;border-collapse:collapse;font-size:14px">{rows}</table>')
    return "".join(out)


def render_email(d: dict) -> tuple[str, str, str]:
    """(subject, plain text, HTML) for one digest."""
    m, dl, s = d["matter"], d["deadlines"], d["summary"]
    late = dl["overdue"] + dl["long_overdue"]
    who = m.get("client") or m.get("description") or "Case"
    stale = d.get("stale_reason")
    subject = (f"{'[Data ' + str(round(d['data_age_h'] or 0)) + ' h old] ' if stale else ''}Daily digest · {who}"
               f"{' (' + m['number'] + ')' if m.get('number') else ''} · {len(late)} overdue, {len(dl['due_soon'])} due soon")
    dash = settings.dashboard_url

    h = [f'<div style="font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;color:#0F1B2D;max-width:720px;'
         f'margin:0 auto;font-size:15px;line-height:1.5">',
         f'<div style="background:{NAVY};color:#fff;padding:14px 18px;border-radius:10px 10px 0 0;border-bottom:4px solid {GOLD}">'
         f'<div style="font-size:12px;letter-spacing:.08em;text-transform:uppercase;opacity:.85">Law-monade · Daily case digest · '
         f'{e(settings.firm_name)}</div><div style="font-family:Georgia,serif;font-size:24px;font-weight:700">{e(who)}</div>'
         f'<div style="opacity:.9">{e(m.get("description") or "")}{" · " + e(m["number"]) if m.get("number") else ""}</div></div>',
         f'<div style="border:1px solid {LINE};border-top:none;padding:14px 18px;border-radius:0 0 10px 10px">',
         f'<p style="margin:0 0 6px"><b>Stage:</b> {e(m.get("stage") or "—")} · <b>Status:</b> {e(m.get("status") or "—")} · '
         f'<b>Data as of:</b> {e(local_time(d["data_as_of"]))} ({"live Clio" if d["source"] == "clio" else "sample file"})</p>']
    if stale:
        h.append(f'<p style="background:#FEF3F2;border:1px solid #FECDCA;color:{RED};padding:8px 10px;border-radius:8px">'
                 f'<b>Clio could not be read this morning.</b> {e(stale)} These numbers are from the copy saved '
                 f'{e(str(d["data_age_h"]))} hours ago.</p>')
    if d["urgent"]:
        h.append(f'<div style="background:#FFFAEB;border:1px solid #FEC84B;padding:8px 12px;border-radius:8px;margin:8px 0">'
                 f'<b style="color:{AMBER}">Needs attention today</b><ul style="margin:4px 0 0 18px;padding:0">'
                 + "".join(f"<li>{e(r)}</li>" for r in d["urgent"]) + "</ul></div>")

    h.append(_risks_html(d["risks"]))

    # summary
    h.append(_h2("Case summary"))
    h.append(f'<p style="margin:0 0 6px;color:{MUTED}">{e(s["facts"])}</p>')
    for x in s["sentences"]:
        h.append(f'<p style="margin:4px 0">{e(x["text"])} <span style="font-size:12px;color:{MUTED}">'
                 f'({_a(x["src"].get("url", ""), x["src"]["label"], MUTED)})</span></p>')
    h.append(f'<p style="font-size:12px;color:{MUTED}">'
             + (f'Written by AI from this case\'s Clio fields, notes and emails; each sentence was checked word for word against '
                f'its source{" (" + str(s["dropped"]) + " left out that didn&#39;t match)" if s["dropped"] else ""}.'
                if s["mode"] == "ai" else e(s["note"] or "Clio's own words.")) + "</p>")

    ch = d["changes"]
    h.append(_h2("What changed since the last digest"))
    if ch["since"] is None:
        h.append(f'<p style="color:{MUTED}">This is the first digest for this case, so there is nothing to compare yet.</p>')
    elif ch["lines"]:
        h.append(f'<p style="color:{MUTED};margin:0">Compared with the copy from {e(local_time(ch["since"]))}:</p><ul>'
                 + "".join(f"<li>{e(x)}</li>" for x in ch["lines"]) + "</ul>")
    else:
        h.append(f'<p>No changes in Clio since {e(local_time(ch["since"]))}.</p>')

    h.append(_h2(f"Overdue ({len(dl['overdue'])})"))
    h.append(_table(dl["overdue"], True) if dl["overdue"] else "<p>Nothing overdue.</p>")
    if dl["long_overdue"]:
        h.append(f'<p style="margin:12px 0 4px"><b>Long overdue</b> <span style="color:{MUTED}">(more than '
                 f'{settings.digest_long_overdue_days} days; may be stale in Clio)</span></p>' + _table(dl["long_overdue"], True))
    h.append(_h2(f"Due today or tomorrow ({len(dl['due_soon'])})"))
    h.append(_table(dl["due_soon"], False) if dl["due_soon"] else "<p>Nothing due today or tomorrow.</p>")
    h.append(_h2(f"Coming up, next {settings.digest_upcoming_days} days ({len(dl['upcoming'])})"))
    h.append(_table(dl["upcoming"], False) if dl["upcoming"] else "<p>Nothing scheduled.</p>")
    notes = []
    if dl["no_date"]:
        notes.append(f"{dl['no_date']} open task{'s have' if dl['no_date'] != 1 else ' has'} no due date in Clio.")
    if dl.get("sol"):
        sol = dl["sol"]
        notes.append(f"Statute of limitations: {sol['nice']} ({'passed; case is in ' + (m.get('stage') or 'litigation') if sol['days'] < 0 and sol['filed'] else str(sol['days']) + ' days' if sol['days'] >= 0 else 'PASSED ' + str(-sol['days']) + ' days ago'}). Source: {sol['source']}.")
    if notes:
        h.append("".join(f'<p style="font-size:13px;color:{MUTED};margin:6px 0 0">{e(n)}</p>' for n in notes))

    # numbers
    h.append(_h2("The numbers (same as the Case brief tab)"))
    rows = ""
    for c in d["cards"]:
        color = AMBER if c["review_status"] == "needs_review" else GREEN if c["review_status"] in ("approved", "corrected") else MUTED
        rows += (f'<tr><td style="padding:6px;border-bottom:1px solid {LINE}">{e(c["label"])}</td>'
                 f'<td style="padding:6px;border-bottom:1px solid {LINE};font-weight:700;color:{NAVY};white-space:nowrap">{e(c["value"])}</td>'
                 f'<td style="padding:6px;border-bottom:1px solid {LINE};color:{color};font-weight:600;font-size:13px">{e(c["review"])}</td></tr>')
    h.append(f'<table style="width:100%;border-collapse:collapse;font-size:14px">{rows}</table>')
    n = d["counts"]
    h.append(f'<p style="font-size:13px;color:{MUTED}">Read from {n["notes"]} notes · {n["communications"]} emails and calls · '
             f'{n["tasks"]} tasks · {n["calendar"]} calendar entries · {n["expenses"]} expenses · {n["documents"]} documents · '
             f'{n["contacts"]} people and companies.</p>')
    h.append(f'<p style="margin-top:18px">{_a(dash, "Open the case in Law-monade")}'
             + (f' · {_a(m["url"], "Open in Clio")}' if m.get("url") else "") + "</p>")
    h.append(f'<p style="font-size:12px;color:{MUTED};border-top:1px dashed {LINE};padding-top:8px">Law-monade only reads '
             f'Clio; nothing in Clio was changed. Text links open your phone\'s messages app with a draft; nothing is '
             f'sent until you send it. Recipient: {e(d["recipients"]["why"])}.</p></div></div>')

    # plain text
    t = [f"Daily case digest · {who} {m.get('number') or ''}".strip(),
         f"Stage: {m.get('stage') or '-'} · Status: {m.get('status') or '-'} · Data as of {local_time(d['data_as_of'])}"]
    if stale:
        t.append(f"WARNING: Clio could not be read ({stale}); data is {d['data_age_h']} h old.")
    if d["urgent"]:
        t += ["", "NEEDS ATTENTION TODAY"] + [f"- {r}" for r in d["urgent"]]
    r = d["risks"]
    t += ["", "WHAT COULD HURT THIS CASE"] + ([f"  ({r['note']})"] if r.get("note") else [])
    t += [f"- [{x['level_words']}] {x['label']}: {x['value']}. {x['why']}" for x in r["top"]] or ["- Nothing flagged today."]
    t += [f"- Other check [{x['level_words']}] {x['label']}: {x['value']}" for x in r["others"]]
    t += ["", "CASE SUMMARY", s["facts"]] + [f"- {x['text']} ({x['src']['label']})" for x in s["sentences"]]
    t += ["", "WHAT CHANGED"] + ([f"- {x}" for x in ch["lines"]] or ["- First digest" if ch["since"] is None else "- No changes"])
    t += ["", f"OVERDUE ({len(late)})"]
    for it in late[:settings.digest_list_max]:
        c = it.get("contact")
        who_ = f" -> {c['name']} ({c['role']}) {c['phone'] or c['email'] or 'no phone/email in Clio'}" if c else ""
        t.append(f"- {it['nice']} ({_late(it['days'])}): {it['title']}{who_}")
    t += ["", f"DUE TODAY OR TOMORROW ({len(dl['due_soon'])})"] + [f"- {i['nice']}: {i['title']}" for i in dl["due_soon"][:settings.digest_list_max]]
    t += ["", f"COMING UP ({len(dl['upcoming'])})"] + [f"- {i['nice']}: {i['title']}" for i in dl["upcoming"][:settings.digest_list_max]]
    t += ["", "THE NUMBERS"] + [f"- {c['label']}: {c['value']} ({c['review']})" for c in d["cards"]]
    t += ["", f"Open the case: {dash}", "Law-monade only reads Clio; nothing in Clio was changed."]
    return subject, "\n".join(t), "".join(h)


def render_slack(d: dict) -> str | None:
    """Short ping, only when something is urgent. Counts and days only: no names, amounts or medical details."""
    if not d["urgent"]:
        return None
    m = d["matter"]
    head = f"*Law-monade · {m.get('client') or 'Case'}{' (' + m['number'] + ')' if m.get('number') else ''}* needs attention:"
    lines = [head] + [f"• {r}" for r in d["urgent"]]
    red = (d.get("risks") or {}).get("red") or []
    if red:     # risk names only (no case details); risks never trigger a ping on their own
        lines.append(f"• {len(red)} red risk{'s' if len(red) != 1 else ''}: {', '.join(red)}")
    if d.get("stale_reason"):
        lines.append(f"• Data is {d['data_age_h']} h old (Clio could not be read)")
    lines.append(f"<{settings.dashboard_url}|Open the case> · full digest sent by email")
    return "\n".join(lines)


def unavailable_email(matter: dict, reason: str, age: float | None) -> tuple[str, str]:
    who = matter.get("client") or matter.get("description") or "Case"
    subject = f"Daily digest unavailable · {who}"
    text = (f"Today's digest for {who} {matter.get('number') or ''} could not be made.\n\n"
            f"Reason: {reason}\nNewest saved copy: {'none' if age is None else str(age) + ' hours old'}, "
            f"too old to send numbers from (limit {settings.digest_max_age_h:g} h).\n\n"
            f"Open the dashboard to check the case: {settings.dashboard_url}")
    return subject, text


# ---------- send ----------
def _maybe_sent(exc: BaseException) -> bool:
    """True if the send may have gone through (timeout, 500): then we never resend automatically."""
    for x in (exc, exc.__cause__, exc.__context__):
        if x is None:
            continue
        t = x if isinstance(x, retry.Transient) else (retry.from_urllib_error(x) or retry.from_google_error(x))
        if t and (t.kind == "timeout" or t.status in (500, 502, 504)):
            return True
    return False


def send_email(to: list[str], subject: str, text: str, html_: str | None,
               already: list[str] | None = None) -> tuple[str, list[str], str]:
    """(status, sent_to, error). status: sent | partial | failed | unknown | not_set_up | no_recipients.
    `already` = addresses an earlier try of this run reached: they are not emailed twice."""
    from app.emailer import EmailError, send
    already = list(already or [])
    if not to:
        return "no_recipients", already, "No allowed recipient (set the responsible attorney in Clio, or DIGEST_RECIPIENTS)."
    sent, fails, err = list(already), [], ""
    for a in to:
        if a in already:
            continue
        try:
            send(a, subject, text, html_)
            sent.append(a)
        except EmailError as x:
            err = f"{x.message} {x.fix}"
            fails.append("not_set_up" if "isn't set up" in x.message else ("unknown" if _maybe_sent(x) else "failed"))
            if fails[-1] == "not_set_up":
                break
    if not fails:
        return "sent", sent, ""
    if "unknown" in fails:
        return "unknown", sent, err
    return ("partial" if sent else fails[0]), sent, err


def send_slack(text: str | None) -> tuple[str, str]:
    """(status, error). status: sent | not_urgent | not_set_up | failed | unknown"""
    if text is None:
        return "not_urgent", ""
    if not settings.slack_webhook_url:
        return "not_set_up", "SLACK_WEBHOOK_URL is empty in .env"
    from app.integrations import slack
    try:
        return ("sent", "") if slack.notify(text) else ("failed", "Slack did not accept the message")
    except Exception as x:
        return ("unknown" if _maybe_sent(x) else "failed"), f"Slack: {type(x).__name__}"


def ops_ping(text: str) -> None:
    """Tell the firm's Slack that a digest did NOT go out (never contains case details)."""
    try:
        if settings.slack_webhook_url:
            from app.integrations import slack
            slack.notify(f":warning: Law-monade: {text}")
    except Exception as x:
        LOG.warning("[digest] ops ping failed: %s", type(x).__name__)


# ---------- get the case ----------
def fresh(matter_id) -> tuple[dict | None, str]:
    """(snapshot, problem). Reads Clio again (or the sample file); if that fails, the newest saved copy + why."""
    saved = snapshot.load_saved(matter_id)
    if str(matter_id) == "sample":
        if settings.demo_file.exists():
            s = snapshot.from_sample_file(settings.demo_file)
            snapshot.save(s)
            return s, ""
        return saved, "the sample file is missing"
    from app.clio import ClioError, load_steps
    m = (saved or {}).get("matter") or {}
    words = (m.get("client") or "").split()
    queries = [q for q in dict.fromkeys([m.get("number"), words[-1] if words else "", settings.clio_matter_query]) if q]
    problem = "no saved copy of this case to find it by"
    for q in queries:
        try:
            state, steps = load_steps(q, matter_id)     # the matter id is fixed: never another client's case
            for _, fn in steps:
                fn()
            snapshot.save(state["snapshot"])
            return state["snapshot"], ""
        except ClioError as x:
            problem = x.message
            if "No case in Clio matches" not in x.message:
                break                                   # Clio down / sign-in expired: other queries won't help
        except Exception as x:                          # unexpected: keep the reason, use the saved copy
            LOG.exception("[digest] Clio read failed")
            problem = f"unexpected error ({type(x).__name__})"
            break
    return saved, problem


# ---------- the run ----------
def run(matter_id, trigger: str = "scheduled", actor: str = "", snap: dict | None = None, dry_run: bool = False,
        force: bool = False, email_only: bool = False, lien_analysis: dict | None = None,
        timeout: float | None = None, risk_report: dict | None = None) -> dict:
    """See the module docstring. Returns {"status", "message", "run_key", "email", "slack", "digest", ...}."""
    new_run()
    mid = str(matter_id)
    out = {"matter_id": mid, "trigger": trigger, "dry_run": dry_run}

    # cooldown for the button: "Sent 1 min ago. Send again?"
    if trigger == "manual" and not dry_run and not force:
        last = store.last_digest(mid)
        if last and last["status"] in ("sent", "partial") and last.get("finished_at") and \
                _secs_since(last["finished_at"]) < settings.digest_manual_cooldown_s:
            return out | {"status": "cooldown", "last": last,
                          "message": f"A digest was sent at {local_time(last['finished_at'])}. Send another one?"}
    if trigger == "scheduled" and not settings.digest_enabled and not dry_run:
        return out | {"status": "skipped", "message": "Daily digests are turned off (DIGEST_ENABLED=false)."}

    run_key = f"{mid}:{firm_day()}:scheduled" if trigger == "scheduled" else f"{mid}:manual:{secrets.token_hex(4)}"
    out["run_key"] = run_key
    prev = {}
    if not dry_run:
        state, prev = store.claim_digest(run_key, mid, trigger, actor)
        if state == "done":
            return out | {"status": "already_sent", "message": f"Today's digest was already handled ({prev['status']}).",
                          "last": prev}
        if state == "busy":
            return out | {"status": "busy", "message": "This digest is being sent right now."}

    try:
        result = _run(mid, trigger, actor, snap, dry_run, email_only, lien_analysis, timeout, prev, run_key,
                      risk_report if snap is not None else None)
    except Exception as x:          # never leave a run stuck in "running"
        LOG.exception("[digest] run failed")
        if not dry_run:
            store.finish_digest(run_key, status="failed", error=f"{type(x).__name__}: {x}"[:500])
            ops_ping(f"daily digest for case {mid} failed ({type(x).__name__}). Check logs/api.log.")
        return out | {"status": "failed", "message": f"The digest could not be made: {x}"}
    return out | result


def _run(mid, trigger, actor, snap, dry_run, email_only, lien_analysis, timeout, prev, run_key,
         risk_report=None) -> dict:
    stale = ""
    if snap is None:
        with stage("digest.load", LOG) as info:
            snap, stale = fresh(mid)
            info.update(fallback=bool(stale))
    if not snap:
        if not dry_run:
            store.finish_digest(run_key, status="failed", error=f"No data: {stale}")
            ops_ping(f"daily digest for case {mid} not sent: Clio unreachable ({stale}) and no saved copy.")
        return {"status": "failed", "message": f"No copy of this case to build a digest from ({stale})."}

    m = snap["matter"]
    age = age_h(snap.get("fetched_at"))
    if trigger == "scheduled" and (m.get("status") or "").lower() in CLOSED:
        if not dry_run:
            store.finish_digest(run_key, status="skipped", error="case is closed")
        return {"status": "skipped", "message": "The case is closed in Clio, so no daily digest."}

    rcpt = recipients(snap)
    if stale and (age is None or age > settings.digest_max_age_h):
        subject, text = unavailable_email(m, stale, age)
        if dry_run:
            return {"status": "unavailable", "message": text, "email": {"subject": subject, "text": text}}
        es, sent_to, err = send_email(rcpt["to"], subject, text, None)
        ops_ping(f"daily digest for case {m.get('number') or mid} not sent: {stale}; saved copy is "
                 f"{age if age is not None else '?'} h old.")
        store.finish_digest(run_key, status="unavailable", email_status=es, recipients=", ".join(sent_to),
                            error=f"{stale} {err}".strip(), snapshot_fetched_at=snap.get("fetched_at") or "", data_age_h=age)
        return {"status": "unavailable", "message": f"Clio unreachable and the saved copy is too old. {text}",
                "email": {"status": es, "to": sent_to, "error": err}}

    d = build(snap, lien_analysis, timeout=timeout, stale_reason=stale, risk_report=risk_report)
    subject, text, html_ = render_email(d)
    slack_text = None if email_only else render_slack(d)
    if dry_run:
        return {"status": "preview", "message": "Preview only; nothing was sent.", "digest": d,
                "email": {"subject": subject, "text": text, "html": html_, "to": rcpt["to"], "dropped": rcpt["dropped"]},
                "slack": {"text": slack_text}}

    # send: only the channels that haven't gone out in an earlier try of this same run
    es = prev.get("email_status") or ""
    sent_to = [x for x in (prev.get("recipients") or "").split(", ") if x]
    err_e = ""
    if es not in ("sent", "unknown"):
        with stage("digest.email", LOG) as info:
            es, sent_to, err_e = send_email(rcpt["to"], subject, text, html_, already=sent_to)
            info.update(status=es, recipients=len(sent_to))
    ss = prev.get("slack_status") or ""
    err_s = ""
    if email_only:
        ss = ss or "skipped"
    elif ss not in ("sent", "unknown"):
        with stage("digest.slack", LOG) as info:
            ss, err_s = send_slack(slack_text)
            info.update(status=ss)

    ok_e, ok_s = es == "sent", ss in ("sent", "not_urgent", "skipped", "not_set_up")
    status = "sent" if ok_e and ok_s else ("partial" if (ok_e or ss == "sent" or es in ("partial", "unknown")) else "failed")
    err = " ".join(x for x in (err_e, err_s) if x)
    store.finish_digest(run_key, status=status, email_status=es, slack_status=ss, recipients=", ".join(sent_to),
                        error=err[:500], snapshot_fetched_at=snap.get("fetched_at") or "", data_age_h=age,
                        summary=d["summary"]["mode"])
    store.log("digest_" + status, mid, {"run_key": run_key, "trigger": trigger, "email": es, "slack": ss,
                                        "to": sent_to, "dropped": rcpt["dropped"], "urgent": d["urgent"]}, actor=actor)
    if status != "sent" and trigger == "scheduled":
        ops_ping(f"daily digest for case {m.get('number') or mid}: email {es}, Slack {ss}. {err[:200]}")
    words = {"sent": "Digest sent", "partial": "Digest only partly sent", "failed": "Digest not sent"}[status]
    return {"status": status, "message": f"{words}. Email: {es}{' to ' + ', '.join(sent_to) if sent_to else ''}. "
                                         f"Slack: {ss}.{' ' + err if err else ''}",
            "email": {"status": es, "to": sent_to, "dropped": rcpt["dropped"], "error": err_e, "subject": subject},
            "slack": {"status": ss, "error": err_s}, "digest": d}


def watched() -> list[dict]:
    """Cases with a saved copy (opened in the dashboard at least once): what the n8n schedule loops over.
    The sample case is left out unless it's the only one, so the demo still works."""
    out = []
    for p in sorted(settings.snapshot_dir.glob("*/snapshot.json")):
        s = snapshot.load_saved(p.parent.name) or {}
        m = s.get("matter") or {}
        if m:
            out.append({"id": str(m.get("id")), "client": m.get("client"), "number": m.get("number"),
                        "status": m.get("status"), "source": s.get("source")})
    live = [x for x in out if x["source"] != "sample"]
    return live or out
