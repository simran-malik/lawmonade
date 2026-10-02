"""Law-monade look and small building blocks for the screens.

Navy + white + one gold accent. Serif only for headings. Large text for projectors.
"""
import html
import re
import time

import streamlit as st

NAVY, NAVY_2, INK, MUTED, LINE, SOFT = "#13294B", "#1F3A66", "#0F1B2D", "#475467", "#D0D5DD", "#F3F5F9"
GOLD, GOLD_TEXT = "#C9A227", "#7A5C0F"            # gold for lines/accents; darker gold when used as text
GREEN, AMBER, RED = "#067647", "#B54708", "#B42318"

CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Source+Serif+4:opsz,wght@8..60,600;8..60,700&display=swap');
html, body, .stApp {{ font-family: 'Inter', -apple-system, 'Segoe UI', Roboto, sans-serif; color: {INK}; }}
.stApp {{ font-size: 18px; }}
.stApp p, .stApp li, .stApp label, .stApp .stMarkdown {{ font-size: 1.05rem; line-height: 1.55; }}
h1, h2, h3, .lm-serif {{ font-family: 'Source Serif 4', Georgia, 'Times New Roman', serif !important;
                        color: {NAVY} !important; letter-spacing: -0.01em; }}
h1 {{ font-size: 2.3rem !important; }} h2 {{ font-size: 1.8rem !important; }} h3 {{ font-size: 1.4rem !important; }}
#MainMenu, footer, header [data-testid="stToolbar"] {{ visibility: hidden; }}
.block-container {{ padding-top: 1.2rem; max-width: 1280px; }}

/* buttons: biggest = main action */
.stButton > button, .stDownloadButton > button {{ min-height: 3rem; font-size: 1.05rem; font-weight: 600;
    border-radius: 10px; border: 1.5px solid {NAVY}; }}
.stButton > button[kind="primary"] {{ background: {NAVY}; color: #fff; min-height: 3.6rem; font-size: 1.2rem;
    box-shadow: inset 0 -3px 0 {GOLD}; }}
.stButton > button[kind="primary"]:hover {{ background: {NAVY_2}; border-color: {GOLD}; }}
.stButton > button[kind="secondary"] {{ background: #fff; color: {NAVY}; }}
.stButton > button:focus-visible {{ outline: 3px solid {GOLD}; outline-offset: 2px; }}

/* tabs */
.stTabs [data-baseweb="tab"] {{ font-size: 1.1rem; font-weight: 600; padding: 0.6rem 1.1rem; }}
.stTabs [aria-selected="true"] {{ color: {NAVY}; }}
.stTabs [data-baseweb="tab-highlight"] {{ background-color: {GOLD}; height: 3px; }}

/* top bar */
.lm-bar {{ background: {NAVY}; color: #fff; border-radius: 14px; padding: 0.9rem 1.4rem; display: flex;
    align-items: center; justify-content: space-between; border-bottom: 4px solid {GOLD}; margin-bottom: 1.2rem; }}
.lm-brand {{ font-family: 'Source Serif 4', Georgia, serif; font-size: 1.7rem; font-weight: 700; letter-spacing: 0.01em; }}
.lm-brand small {{ font-family: 'Inter', sans-serif; font-size: 0.95rem; font-weight: 400; opacity: 0.85; margin-left: 0.8rem; }}
.lm-badge {{ display: inline-block; padding: 0.25rem 0.7rem; border-radius: 999px; font-size: 0.85rem; font-weight: 600;
    border: 1.5px solid {GOLD}; color: {GOLD}; letter-spacing: 0.03em; }}
.lm-badge.live {{ border-color: #7FD1A8; color: #7FD1A8; }}

/* case header */
.lm-case {{ border: 1px solid {LINE}; border-left: 6px solid {GOLD}; border-radius: 12px; padding: 1.1rem 1.4rem; margin-bottom: 1rem; }}
.lm-case h1 {{ margin: 0 0 0.2rem 0; padding: 0; }}
.lm-case .desc {{ color: {MUTED}; font-size: 1.1rem; }}
.lm-chips {{ margin-top: 0.7rem; display: flex; flex-wrap: wrap; gap: 0.5rem; }}
.lm-chip {{ background: {SOFT}; border: 1px solid {LINE}; border-radius: 999px; padding: 0.3rem 0.8rem; font-size: 0.95rem; }}
.lm-chip b {{ color: {NAVY}; }}

/* cards */
.lm-card {{ border: 1px solid {LINE}; border-radius: 12px; padding: 1rem 1.15rem; background: #fff; height: 100%;
    display: flex; flex-direction: column; gap: 0.35rem; }}
.lm-card.warn {{ border-left: 5px solid {AMBER}; }}
.lm-card.needs_review {{ border: 2px solid {AMBER}; background: #FFFAEB; box-shadow: 0 0 0 4px #FEF0C7; }}
.lm-rev {{ display: inline-block; width: fit-content; border-radius: 6px; padding: 0.15rem 0.55rem;
    font-size: 0.8rem; font-weight: 700; }}
.lm-rev.needs_review {{ background: {AMBER}; color: #fff; }}
.lm-rev.approved {{ background: #ECFDF3; color: {GREEN}; border: 1px solid #ABEFC6; }}
.lm-rev.corrected {{ background: #EFF8FF; color: #175CD3; border: 1px solid #B2DDFF; }}
.lm-rev.not_required {{ background: {SOFT}; color: {MUTED}; font-weight: 600; }}
.lm-lines div {{ margin: 0.1rem 0; }}
.lm-lines b {{ color: {NAVY}; }}
.lm-lines .lbl {{ display: block; font-size: 0.8rem; color: {MUTED}; font-weight: 600; margin-top: 0.25rem; }}
.lm-gtitle {{ font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.06em; color: {MUTED};
    font-weight: 700; margin-top: 0.45rem; }}
.lm-row {{ display: flex; justify-content: space-between; align-items: baseline; gap: 0.6rem;
    padding: 0.25rem 0; border-bottom: 1px dotted {LINE}; }}
.lm-row .n {{ font-weight: 600; color: {INK}; }}
.lm-row .s {{ display: block; font-size: 0.82rem; color: {MUTED}; font-weight: 400; }}
.lm-row .a {{ font-weight: 700; color: {NAVY}; white-space: nowrap; }}
.lm-group.muted .n, .lm-group.muted .a {{ color: {MUTED}; }}
.lm-summary {{ border-radius: 10px; padding: 0.6rem 0.9rem; margin: 0.2rem 0 0.8rem; font-weight: 600; }}
.lm-summary.todo {{ background: #FFFAEB; border: 1px solid #FEC84B; color: {AMBER}; }}
.lm-summary.done {{ background: #ECFDF3; border: 1px solid #ABEFC6; color: {GREEN}; }}
.lm-label {{ text-transform: uppercase; letter-spacing: 0.08em; font-size: 0.8rem; font-weight: 700; color: {MUTED}; }}
.lm-value {{ font-size: 2rem; font-weight: 700; color: {NAVY}; line-height: 1.15; }}
.lm-sub {{ color: {INK}; font-size: 0.98rem; overflow-wrap: anywhere; white-space: normal; }}
.lm-why {{ color: {AMBER}; font-weight: 600; font-size: 0.95rem; }}
.lm-src {{ overflow-wrap: anywhere; margin-top: auto; padding-top: 0.5rem; border-top: 1px dashed {LINE}; font-size: 0.85rem; color: {MUTED}; }}
.lm-src b {{ color: {INK}; font-weight: 600; }}
.lm-pill {{ display: inline-block; border-radius: 999px; padding: 0.1rem 0.55rem; font-size: 0.78rem; font-weight: 700;
    margin-right: 0.35rem; }}
.lm-pill.exact {{ background: #ECFDF3; color: {GREEN}; border: 1px solid #ABEFC6; }}
.lm-pill.calc {{ background: #EEF2F8; color: {NAVY}; border: 1px solid #C7D2E3; }}
.lm-pill.check {{ background: #FFFAEB; color: {AMBER}; border: 1px solid #FEC84B; }}
.lm-pill.ai {{ background: #F4F3FF; color: #5925DC; border: 1px solid #D9D6FE; }}
.lm-pill.edited {{ background: #EFF8FF; color: #175CD3; border: 1px solid #B2DDFF; }}
.lm-src a {{ color: {NAVY}; font-weight: 600; }}

/* money cards: the frame is a keyed Streamlit container (st-key-lmcard_<class>_<key>) so a real button
   ("Where this comes from" / "Review" / "Reviewed by ...") can sit INSIDE the card and open a pop-up */
div[class*="st-key-lmcard_"] {{ border: 1px solid {LINE}; border-radius: 12px; padding: 1rem 1.15rem 0.6rem; background: #fff;
    gap: 0.4rem; }}
div[class*="st-key-lmcard_"] > div {{ flex-shrink: 0; }}   /* never squeeze the card text under the link */
div[class*="st-key-lmcard_warn_"] {{ border-left: 5px solid {AMBER}; }}
div[class*="st-key-lmcard_needs_review_"] {{ border: 2px solid {AMBER}; background: #FFFAEB; box-shadow: 0 0 0 4px #FEF0C7; }}
.lm-card-in {{ display: flex; flex-direction: column; gap: 0.35rem; }}
div[class*="st-key-srclink_"] {{ border-top: 1px dashed {LINE}; padding-top: 0.35rem; margin-top: 0.2rem; }}
div[class*="st-key-srclink_"] button {{ background: none !important; width: auto; border: none !important; box-shadow: none !important;
    min-height: 0 !important; padding: 0.15rem 0 !important; color: #175CD3 !important; text-decoration: underline;
    text-underline-offset: 3px; font-weight: 600; justify-content: flex-start; }}
div[class*="st-key-srclink_"] button p {{ font-size: 1rem !important; color: #175CD3 !important; }}
div[class*="st-key-srclink_"] button:hover p {{ color: #0B4A9E !important; }}
div[class*="st-key-lmcard_needs_review_"] div[class*="st-key-srclink_"] button p {{ font-weight: 700; }}
.lm-digest {{ border: 1px solid {LINE}; border-left: 6px solid {NAVY}; border-radius: 12px; padding: 0.7rem 1rem;
    margin: 0.2rem 0 0.6rem; font-size: 0.98rem; }}
.lm-digest b {{ color: {NAVY}; }}
.lm-digest .muted {{ color: {MUTED}; font-size: 0.9rem; }}
.lm-ok {{ color: {GREEN}; font-weight: 700; }} .lm-bad {{ color: {RED}; font-weight: 700; }} .lm-meh {{ color: {AMBER}; font-weight: 700; }}

/* empty state */
.lm-empty {{ text-align: center; padding: 2.5rem 1rem 1rem; }}
.lm-empty h1 {{ font-size: 2.6rem !important; margin-bottom: 0.4rem; }}
.lm-empty p {{ color: {MUTED}; font-size: 1.2rem !important; max-width: 760px; margin: 0 auto 1.4rem; }}
.lm-rule {{ width: 72px; height: 4px; background: {GOLD}; margin: 0.6rem auto 1.2rem; border-radius: 2px; }}

/* progress */
.lm-steps {{ border: 1px solid {LINE}; border-radius: 12px; padding: 1.1rem 1.4rem; max-width: 760px; margin: 1rem auto; }}
.lm-step {{ display: flex; align-items: center; gap: 0.8rem; padding: 0.35rem 0; font-size: 1.1rem; }}
.lm-step .ico {{ width: 1.6rem; height: 1.6rem; border-radius: 50%; display: inline-flex; align-items: center;
    justify-content: center; font-size: 0.9rem; font-weight: 700; flex: none; }}
.lm-step.done .ico {{ background: {NAVY}; color: #fff; }}
.lm-step.now .ico {{ border: 3px solid {LINE}; border-top-color: {GOLD}; animation: lmspin 0.9s linear infinite; }}
.lm-step.todo .ico {{ border: 2px solid {LINE}; }}
.lm-step.todo {{ color: {MUTED}; }}
.lm-step .t {{ margin-left: auto; color: {MUTED}; font-variant-numeric: tabular-nums; font-size: 0.95rem; }}
.lm-fact {{ margin-top: 0.9rem; padding: 0.7rem 0.9rem; background: {SOFT}; border-left: 4px solid {GOLD}; border-radius: 6px;
    font-size: 1rem; }}
.lm-fact b {{ color: {GOLD_TEXT}; }}
@keyframes lmspin {{ to {{ transform: rotate(360deg); }} }}

/* errors */
.lm-error {{ border: 2px solid {RED}; background: #FEF3F2; border-radius: 12px; padding: 1rem 1.2rem; margin: 1rem 0; }}
.lm-error .h {{ color: {RED}; font-weight: 700; font-size: 1.15rem; }}
.lm-error .fix {{ margin-top: 0.35rem; }}
</style>
"""

# Short, plain-words facts shown while the user waits (definitions, not statistics).
FACTS = [
    ("Lien", "a provider who treats on a lien gets paid from the settlement, not up front."),
    ("Statute of limitations", "the last day to file the lawsuit. Miss it and the case is usually gone."),
    ("Specials", "the case's hard costs, such as medical bills and lost wages."),
    ("Policy limits", "the most an insurance policy will pay, no matter what the case is worth."),
    ("Contingency fee", "the firm is paid a share of the recovery, and nothing if the case is lost."),
    ("Demand package", "the letter and records the firm sends the insurer to ask for a settlement."),
    ("Gap in treatment", "weeks without care that the insurer may use to argue the injury healed."),
    ("Medical chronology", "a dated list of every visit and finding, built from the medical records."),
]


def firm_name() -> str:
    from app.config import settings
    return settings.firm_name


def apply():
    st.set_page_config(page_title="Law-monade", page_icon="⚖️", layout="wide", initial_sidebar_state="collapsed")
    st.markdown(CSS, unsafe_allow_html=True)
    st.markdown(CSS_MORE, unsafe_allow_html=True)


def esc(x) -> str:
    return html.escape(str(x if x is not None else ""))


def top_bar(source: str | None):
    """source: 'sample' -> Demo mode badge, 'clio' -> Live from Clio badge, None -> no badge."""
    badge = ""
    if source == "sample":
        badge = '<span class="lm-badge" title="Using the sample file, not live Clio data">DEMO MODE · SAMPLE DATA</span>'
    elif source == "clio":
        badge = '<span class="lm-badge live" title="Reading live from your Clio account (read-only)">LIVE FROM CLIO · READ-ONLY</span>'
    st.markdown(f'<div class="lm-bar"><div class="lm-brand">Law-monade<small>Case briefings · {esc(firm_name())}</small></div>'
                f'<div>{badge}</div></div>', unsafe_allow_html=True)


def pill(level: str, text: str) -> str:
    """level: exact | calc | check | ai | edited"""
    return f'<span class="lm-pill {level}">{esc(text)}</span>'


MONEY_RE = re.compile(r"\$\s?[\d,]+(?:\.\d{1,2})?")
LABEL_RE = re.compile(r"^([A-Za-z][^:$\d]{0,30}):\s+")


def bold_money(text: str) -> str:
    """Escape, then make dollar amounts bold."""
    return MONEY_RE.sub(lambda m: f"<b>{m.group(0)}</b>", esc(text))


def rich(text: str) -> str:
    """One line per line of the Clio text; short labels ("Client UM/UIM") muted, dollar amounts in bold."""
    out = []
    for line in str(text or "").split("\n"):
        line = line.strip()
        if not line:
            continue
        m = LABEL_RE.match(line)
        out.append(f'<div><span class="lbl">{esc(m.group(1))}</span> {bold_money(line[m.end():])}</div>' if m
                   else f"<div>{bold_money(line)}</div>")
    return f'<div class="lm-sub lm-lines">{"".join(out)}</div>' if out else ""


def groups_html(groups: list[dict]) -> str:
    """Rows like "New York State Medicaid ........ $22,180", grouped ("Counted as liens", "Not counted")."""
    html_ = ""
    for g in groups:
        rows = "".join(f'<div class="lm-row"><span class="n">{esc(r["name"])}<span class="s">{esc(r["note"])}</span></span>'
                       f'<span class="a">{esc(r["amount"])}</span></div>' for r in g["rows"])
        html_ += (f'<div class="lm-group{" muted" if g.get("muted") else ""}">'
                  f'<div class="lm-gtitle">{esc(g["title"])}</div>{rows}</div>')
    return html_


def review_badge(rv: dict) -> str:
    from app.store import nice_time
    st_, text = rv["status"], rv["label"]
    if st_ == "needs_review":
        text = "⚠ " + text.upper()
    elif st_ in ("approved", "corrected"):
        text = ("✓ " if st_ == "approved" else "✎ ") + text + (f" by {rv['by']}" if rv.get("by") else "") \
               + (f" · {nice_time(rv['at'])}" if rv.get("at") else "")
    return f'<span class="lm-rev {st_}">{esc(text)}</span>'


def card_class(k: dict) -> str:
    """needs_review | warn | plain: picks the card's border (see the st-key-lmcard_* CSS)."""
    rv = k.get("review") or {}
    return "needs_review" if rv.get("status") == "needs_review" else ("warn" if k.get("warn") else "plain")


def card_body(k: dict) -> str:
    """What's inside one money card: label, review status, number, what's behind it, and a warning if any.
    The card's frame is a Streamlit container (so the "Where this comes from" link can sit inside it)."""
    rv = k.get("review") or {"status": "not_required", "label": ""}
    return (f'<div class="lm-card-in"><div class="lm-label">{esc(k["label"])}</div>'
            + (review_badge(rv) if rv.get("label") else "")
            + f'<div class="lm-value">{esc(k["value"])}</div>'
            + (groups_html(k["groups"]) if k.get("groups") else "")
            + rich(k.get("sub", ""))
            + (f'<div class="lm-why">⚠ {bold_money(k["why"])}</div>' if k.get("why") else "")
            + '</div>')


def card(k: dict) -> str:
    """The whole card as one HTML block (for places with no link inside, e.g. previews)."""
    cls = card_class(k)
    return f'<div class="lm-card {"" if cls == "plain" else cls}">{card_body(k)}</div>'


def source_link_label(k: dict) -> str:
    """Words on the blue link inside a card. Needs review -> "Review"; approved -> "Reviewed by Sam"."""
    rv = k.get("review") or {}
    who = (rv.get("by") or "").strip()
    if rv.get("status") == "needs_review":
        return "Review →"
    if rv.get("status") == "approved":
        return f"✓ Reviewed by {who}" if who else "✓ Reviewed"
    if rv.get("status") == "corrected":
        return f"✎ Corrected by {who}" if who else "✎ Corrected"
    return "Where does this come from?"


def source_html(k: dict) -> str:
    """How sure we are, where the number comes from, and a link to the exact Clio tab."""
    link, open_ = k.get("link"), ""
    if link and link.get("url"):
        open_ = (f'<br><a href="{esc(link["url"])}" target="_blank">Open {esc(link.get("place") or "")} in Clio ↗</a>'
                 + (f' <span class="lm-hint">then look for {esc(link["hint"])}</span>' if link.get("hint") else ""))
    return f'<div class="lm-src">{pill(*k["sure"])}<b>Source:</b> {esc(k["source"])}{open_}</div>'


def review_summary(cards: list[dict]) -> str:
    """One line above the cards: which numbers still need a person to look at them."""
    need = [k["label"] for k in cards if (k.get("review") or {}).get("status") == "needs_review"]
    if not need:
        return '<div class="lm-summary done">✓ Every number is checked or reviewed.</div>'
    return (f'<div class="lm-summary todo">⚠ {len(need)} of {len(cards)} numbers need your review: '
            f'{esc(", ".join(need))}. Click “Review” on each card.</div>')

def empty_state(title: str, text: str):
    st.markdown(f'<div class="lm-empty"><h1>{esc(title)}</h1><div class="lm-rule"></div><p>{esc(text)}</p></div>',
                unsafe_allow_html=True)


def error_box(message: str, fix: str):
    st.markdown(f'<div class="lm-error"><div class="h">{esc(message)}</div><div class="fix"><b>What to do:</b> {esc(fix)}</div></div>',
                unsafe_allow_html=True)


def _steps_html(labels, current, times, fact_i, title):
    rows = []
    for i, label in enumerate(labels):
        state = "done" if i < current else "now" if i == current else "todo"
        ico = "✓" if state == "done" else ""
        t = f"{times[i]:.1f} s" if i < len(times) else ("working…" if state == "now" else "")
        rows.append(f'<div class="lm-step {state}"><span class="ico">{ico}</span><span>{esc(label)}</span><span class="t">{t}</span></div>')
    term, meaning = FACTS[fact_i % len(FACTS)]
    total = f' · {sum(times):.1f} s' if current >= len(labels) else ""
    return (f'<div class="lm-steps"><div class="lm-label">{esc(title)}{total}</div>{"".join(rows)}'
            f'<div class="lm-fact"><b>Good to know · {esc(term)}:</b> {esc(meaning)}</div></div>')


def run_steps(steps: list[tuple[str, callable]], title: str = "Getting your case ready") -> list[float]:
    """Run each step and show progress: done ✓ with time taken, current one spinning, the rest waiting.
    Errors from a step are raised after the box shows where it stopped."""
    box = st.empty()
    labels = [s[0] for s in steps]
    times: list[float] = []
    fact_i = int(time.time()) % len(FACTS)
    for i, (_, fn) in enumerate(steps):
        box.markdown(_steps_html(labels, i, times, fact_i + i, title), unsafe_allow_html=True)
        t0 = time.monotonic()
        fn()
        times.append(time.monotonic() - t0)
    box.markdown(_steps_html(labels, len(labels), times, fact_i, title + " · Done"), unsafe_allow_html=True)
    return times


# ---------- timeline + sharing + provider page ----------
CSS_MORE = f"""
<style>
.lm-month {{ font-family: 'Source Serif 4', Georgia, serif; color: {NAVY}; font-size: 1.35rem; font-weight: 700;
    margin: 1.4rem 0 0.4rem; padding-bottom: 0.25rem; border-bottom: 2px solid {GOLD}; }}
.lm-item {{ display: grid; grid-template-columns: 7.5rem 1fr; gap: 1rem; padding: 0.75rem 0.4rem;
    border-bottom: 1px solid {LINE}; }}
.lm-item .d {{ color: {MUTED}; font-variant-numeric: tabular-nums; font-size: 0.98rem; padding-top: 0.15rem; }}
.lm-item .h {{ font-weight: 600; font-size: 1.08rem; }}
.lm-item .x {{ color: {INK}; margin-top: 0.2rem; white-space: pre-wrap; overflow-wrap: anywhere; }}
.lm-item details summary {{ cursor: pointer; color: {NAVY}; font-weight: 600; margin-top: 0.3rem; font-size: 0.95rem; }}
.lm-item details[open] summary {{ margin-bottom: 0.3rem; }}
.lm-kind {{ display: inline-block; font-size: 0.75rem; font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase;
    border-radius: 6px; padding: 0.1rem 0.45rem; margin-right: 0.5rem; vertical-align: 2px; border: 1px solid {LINE};
    background: {SOFT}; color: {NAVY}; }}
.lm-kind.Task {{ background: #FFF8E6; border-color: #F5D98B; color: {GOLD_TEXT}; }}
.lm-kind.Email, .lm-kind.Phone {{ background: #EEF2F8; border-color: #C7D2E3; }}
.lm-kind.Expense {{ background: #ECFDF3; border-color: #ABEFC6; color: {GREEN}; }}
.lm-late {{ color: {RED}; font-weight: 700; font-size: 0.85rem; margin-left: 0.4rem; }}
.lm-srcline {{ font-size: 0.85rem; color: {MUTED}; margin-top: 0.3rem; }}
.lm-hint {{ color: {GOLD_TEXT}; font-weight: 600; }}

.lm-stepnum {{ display: inline-flex; width: 2rem; height: 2rem; border-radius: 50%; background: {NAVY}; color: #fff;
    align-items: center; justify-content: center; font-weight: 700; margin-right: 0.6rem; border: 2px solid {GOLD}; }}
.lm-stephead {{ font-family: 'Source Serif 4', Georgia, serif; color: {NAVY}; font-size: 1.35rem; font-weight: 700;
    margin: 1.2rem 0 0.6rem; display: flex; align-items: center; }}
.lm-never {{ background: {SOFT}; border: 1px dashed {LINE}; border-radius: 10px; padding: 0.7rem 1rem; color: {MUTED};
    font-size: 0.95rem; }}
.lm-preview-frame {{ border: 3px solid {NAVY}; border-radius: 16px; padding: 0.4rem; background: {SOFT}; }}
.lm-preview-tag {{ display: inline-block; background: {NAVY}; color: #fff; border-radius: 8px 8px 0 0; padding: 0.25rem 0.8rem;
    font-size: 0.85rem; font-weight: 700; letter-spacing: 0.04em; }}

/* provider page */
.lm-pv {{ background: #fff; border-radius: 12px; padding: 1.2rem 1.4rem; }}
.lm-pv h2 {{ margin-top: 0 !important; }}
.lm-status {{ display: flex; align-items: center; gap: 1rem; padding: 1rem 1.2rem; border-radius: 12px; margin: 0.6rem 0 1rem; }}
.lm-status.on {{ background: #ECFDF3; border: 2px solid #ABEFC6; }}
.lm-status.off {{ background: #FEF3F2; border: 2px solid #FECDCA; }}
.lm-status .big {{ font-size: 1.5rem; font-weight: 700; }}
.lm-status.on .big {{ color: {GREEN}; }} .lm-status.off .big {{ color: {RED}; }}
.lm-sec {{ border: 1px solid {LINE}; border-radius: 12px; padding: 0.9rem 1.2rem; margin-bottom: 0.9rem; }}
.lm-sec .lm-label {{ margin-bottom: 0.4rem; }}
.lm-need {{ padding: 0.5rem 0; border-bottom: 1px solid {LINE}; }} .lm-need:last-child {{ border-bottom: none; }}
.lm-range {{ font-size: 2rem; font-weight: 700; color: {NAVY}; }}
.lm-msg {{ border-left: 4px solid {GOLD}; padding: 0.6rem 1rem; background: {SOFT}; border-radius: 6px; white-space: pre-wrap; }}
.lm-foot {{ color: {MUTED}; font-size: 0.9rem; margin-top: 0.8rem; }}
</style>
"""


def apply_more():
    st.markdown(CSS_MORE, unsafe_allow_html=True)


def step_head(n: int, text: str):
    st.markdown(f'<div class="lm-stephead"><span class="lm-stepnum">{n}</span>{esc(text)}</div>', unsafe_allow_html=True)
