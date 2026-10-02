"""Tab 3: Share with a provider. 1) pick the provider  2) choose what they see  3) preview, approve, get the link.
Nothing is shared until the attorney ticks "I checked this" and presses Approve."""
import json

import streamlit as st

from app import share, store
from app.config import settings
from app.snapshot import nice_date
from ui import provider_view, theme
from ui.theme import esc


def render(s: dict):
    ss = st.session_state
    mid = str(s["matter"]["id"])

    # ---- 1. who
    theme.step_head(1, "Who are you sharing with?")
    show_all = st.toggle("Show all people and companies, not only medical providers", key="sh_all")
    provs = share.providers(s, show_all)
    if not provs:
        st.markdown('<div class="lm-never">No medical providers are linked to this case in Clio. '
                    'Turn on "Show all" above, or add the provider to the case in Clio.</div>', unsafe_allow_html=True)
        return
    labels = [f'{p["name"]} · {p["role"]}' for p in provs]
    i = st.selectbox("Provider", range(len(provs)), format_func=lambda k: labels[k], label_visibility="collapsed")
    prov = provs[i]
    d = share.build(s, prov)
    k = f"sh_{prov['id']}_"            # widget keys per provider, so switching provider starts fresh

    # ---- 2. what
    theme.step_head(2, "Choose what they will see")
    left, right = st.columns([3, 2], gap="large")
    with left:
        chosen = [key for key, label in share.SECTIONS.items()
                  if st.checkbox(label, value=key in share.DEFAULT_ON, key=k + key)]

        need_ids, note_ids, record_ids, billed, reduction = [], [], [], d["billed"], (20, 40)
        if "needs" in chosen:
            with st.expander(f"What we need: {len(d['needs'])} open request(s) found for this provider", expanded=bool(d["needs"])):
                if not d["needs"]:
                    st.caption("No open tasks mention this provider.")
                for t in d["needs"]:
                    if st.checkbox(f'{t["title"]} (due {nice_date(t.get("date"))})', value=True, key=k + "n" + str(t["id"])):
                        need_ids.append(str(t["id"]))
                        # The task's note is internal by default (it can hold strategy); share it only on purpose
                        if t.get("text") and st.checkbox("Also share this task's note", value=False,
                                                         key=k + "nn" + str(t["id"]), help=t["text"]):
                            note_ids.append(str(t["id"]))
                    st.caption(f'Source: {t["src"]["label"]}')
        if "bills" in chosen:
            with st.expander("Bills and expected payment", expanded=True):
                if d["bills"]:
                    st.caption("Billed amount added up from: " + "; ".join(b["src"]["label"] for b in d["bills"]))
                else:
                    st.caption("No bill amount for this provider in Clio. Enter it if you know it, or leave 0 "
                               "to ask the provider for an itemized bill.")
                billed = st.number_input("Billed amount ($)", min_value=0.0, step=100.0,
                                         value=float(d["billed"] or 0.0), key=k + "billed") or None
                reduction = st.slider("Expected reduction at settlement (%)", 0, 80, (20, 40), key=k + "red",
                                      help="Your estimate. The provider sees a range, never a final number.")
        if "records" in chosen:
            with st.expander(f"Records: {len(d['records'])} document(s) from this provider found", expanded=False):
                if not d["records"]:
                    st.caption("No documents in Clio mention this provider.")
                for r in d["records"]:
                    if st.checkbox(share.doc_name(r["title"]), value=True, key=k + "r" + str(r["id"])):
                        record_ids.append(str(r["id"]))
        message = st.text_area("Message to the provider (you can edit it)", key=k + "msg", height=190,
                               value=share.default_message(prov["name"], s["matter"].get("client", ""), settings.firm_name))
    with right:
        st.markdown('<div class="lm-label">Never shared</div><div class="lm-never">Notes, emails and calls · '
                    'case value and strategy · task notes (unless you tick "Also share this task\'s note") · '
                    'other providers\' bills · anything not ticked on the left.</div>',
                    unsafe_allow_html=True)
        if d["keys"]:
            st.caption("Items are matched to this provider by the name: " + ", ".join(d["keys"]) +
                       ". Untick anything that doesn't belong.")

    p = share.payload(d, chosen, need_ids, record_ids, billed, reduction, message, firm=settings.firm_name,
                      note_ids=note_ids)

    # ---- 3. preview + approve
    theme.step_head(3, "Check the preview")
    st.markdown(f'<span class="lm-preview-tag">PREVIEW · exactly what {esc(prov["name"])} will see after opening the link</span>'
                f'<div class="lm-preview-frame">{provider_view.html(p)}</div>', unsafe_allow_html=True)
    ok = st.checkbox("I checked this preview. It shares only what this provider should see.", key=k + "ok")
    if not chosen:
        st.caption("Tick at least one section to share.")

    # ---- 4. approve + email the LINK (the email never contains case details)
    from app import emailer
    theme.step_head(4, "Approve and send the secure link")
    c1, c2 = st.columns([3, 2])
    with c1:
        to = st.text_input("Send to", value=prov.get("email", ""), key=k + "to",
                           placeholder="No email in Clio for this provider: type one")
        where = "Clio" if s["source"] == "clio" else "the sample file"
        st.caption(f"Email address from {where}." if prov.get("email") else f"{where.capitalize()} has no email for this provider.")
        subject = st.text_input("Subject", key=k + "subj",
                                value=f"Secure case update from {settings.firm_name}: {s['matter'].get('client', '')}".rstrip(": "))
    with c2:
        st.markdown(f'<div class="lm-label">Sent from</div><div class="lm-never">{esc(emailer.sender())}</div>',
                    unsafe_allow_html=True)
        st.caption("The email holds only your message and the secure link. Case details stay behind the link.")
        if settings.email_demo_redirect:
            st.markdown(f'<span class="lm-pill check">DEMO</span> Emails go to <b>{esc(settings.email_demo_redirect)}</b> '
                        f'instead of the provider.', unsafe_allow_html=True)
        if emailer.mode() == "none":
            st.markdown('<span class="lm-pill check">SETUP NEEDED</span> Run <code>bash run.sh gmail</code> once.',
                        unsafe_allow_html=True)

    ready = ok and bool(chosen)
    send = st.button("Approve, create secure link and email it", type="primary", use_container_width=True,
                     disabled=not ready, key=k + "send")
    only = st.button("Only create the link (I'll send it myself)", disabled=not ready, key=k + "only")
    if not ok:
        st.caption("Tick \"I checked this preview\" above to continue.")

    if send and "@" not in (to or ""):
        theme.error_box("There's no valid email address to send to.", "Type the provider's email address, then try again.")
    elif send or only:
        token = store.create_share(mid, prov["id"], prov["name"], chosen, edited_text=json.dumps(p), created_by="attorney")
        sh = store.get_share(token)
        link, expires = f"{settings.public_url}/?share={token}", nice_date(sh["expires_at"])
        ss["last_result"] = {"token": token, "provider": prov["id"], "link": link, "expires": expires, "sent": None, "error": None}
        if send:
            try:
                r = emailer.send(to, subject, provider_view.link_email_text(message, link, expires),
                                 provider_view.link_email_html(message, link, expires, settings.firm_name))
                store.log("email_sent", token, {"to": r["to"], "intended": r["intended"], "via": r["via"], "subject": subject})
                ss["last_result"]["sent"] = r
            except emailer.EmailError as e:
                store.log("email_failed", token, {"to": to, "error": e.message})
                ss["last_result"]["error"] = (e.message, e.fix)

    res = ss.get("last_result")
    if res and res["provider"] == prov["id"]:
        if res["sent"]:
            r = res["sent"]
            note = f" (demo: meant for {r['intended']})" if r["to"] != r["intended"] else ""
            st.success(f"Secure link emailed to {r['to']}{note}. It works until {res['expires']}.")
        elif res["error"]:
            theme.error_box("The link was created, but the email was not sent. " + res["error"][0],
                            res["error"][1] + " You can also copy the link below and send it yourself.")
        else:
            st.success(f"Secure link created. It works until {res['expires']}. Copy it and send it to the provider:")
        st.code(res["link"], language=None)

    # ---- 5. already shared
    rows = store.shares_for_matter(mid)
    if rows:
        theme.step_head(5, "Already shared on this case")
        for r in rows:
            c1, c2, c3 = st.columns([4, 4, 1.3])
            state = "turned off" if r["revoked"] else f'works until {nice_date(r["expires_at"])}'
            seen = (f'opened {r["views"]} time(s), last {store.nice_time(r["last_view"])}' if r["views"] else "not opened yet")
            mails = store.emails_for(r["token"])
            mailed = f'emailed to {mails[-1]["to"]} {store.nice_time(mails[-1]["at"])}' if mails else "not emailed"
            c1.markdown(f'**{esc(r["provider_name"])}** · created {store.nice_time(r["created_at"])}  \n{mailed}')
            c2.markdown(f'{seen}  \n{state}')
            if not r["revoked"] and c3.button("Turn off", key="rv" + r["token"], help="The link stops working right away"):
                store.revoke_share(r["token"])
                st.rerun()
