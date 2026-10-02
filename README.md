# Law-monade

Built at the Swans Applied AI Hackathon (Law-Di-Gras, San Diego, Oct 2, 2026).

**What it does:** turns a live personal-injury case in Clio Manage into a one-screen brief, a daily digest and a
secure provider update, with every fact linked back to where it came from in Clio.

Clio is read-only input (GET requests only, read-only app permissions). Our own data lives outside Clio.
Full requirements: [`REQUIREMENTS.md`](REQUIREMENTS.md). How it's built (diagram, components, reliability, logging):
[`ARCHITECTURE.md`](ARCHITECTURE.md). Demo script, limits and decision log: [`DEMO_LOG.md`](DEMO_LOG.md).

## Features

**At a glance: the Case brief tab**
- **What could hurt this case:** the top 1-2 risks for the case's stage, red / amber / green, each with a why line and
  a Clio link. Litigation: overdue or upcoming court and discovery deadlines, days since the last client contact,
  contested liability (AI quote, checked by code). Every stage: days since any activity, days in the current stage.
  Stage names and thresholds per firm in `config/risks.yaml`.
- **Money cards:** case value vs. coverage, liens, medical specials, firm costs. Each is marked Exact, Calculated or
  Check. **Where does this come from?** opens the source with a link to the exact Clio tab, plus **Looks good** /
  **Something wrong?**. Approved cards turn green with "Last reviewed by &lt;name&gt;"; a changed number needs a new look.
- **Lien breakdown:** the AI sorts the lien field into lien / paid benefit / pending / defense offset; code checks
  each quote and amount against the Clio text and adds up only checked liens.
- **What changed** since you last looked, and the entries that matter.

**Dive deeper: the Everything, by date tab**
- Every note, email, call, task, calendar entry, expense and document in one searchable list; each line shows its source.
- On top: **Overdue** (open tasks past due, most overdue first) and **Due today or tomorrow**. Each row can
  **Email** (Gmail / SMTP) or **Text** (Twilio) the person responsible in Clio, with a draft you can edit. A person
  presses send; every send is in the audit log.
- **Add to calendar** per task or calendar entry, or **Add all to calendar** for everything upcoming (Google Calendar,
  never added twice).

**Share with a provider**
- The attorney ticks exactly what a treating provider sees, previews it, approves it, and emails a secure link that
  expires (default 14 days, can be turned off anytime). The email carries only the link, never case details.
- The provider page (its own app, port 8502) shows a frozen copy: case status, what the firm needs from their office,
  and their bills as a range, never the billed amount. Task notes are shared only if ticked.
- **Already shared** shows when each link was opened. Shares, emails and views are logged: a paper trail.

**Daily digest**
- One email per case every weekday morning (n8n schedule, 6:55 AM firm time) or on demand with **Send digest now**:
  overdue / due soon / statute of limitations, what changed since the last digest, case risks, and a 3-5 sentence
  summary where each sentence must quote Clio word for word.
- **Slack** only when something is urgent, with counts and red risk names only, no client details.
- Never sent twice (one run per case per day), never sends numbers older than 48 hours, and can be limited to firm
  email domains (`FIRM_EMAIL_DOMAINS`).

**Guarantees**
- **Provenance and trust:** every fact links to its source; AI quotes and numbers are checked against Clio text;
  an append-only audit log records who approved, corrected, shared, emailed, texted or added to the calendar.
- **Not over-confident:** numbers we can't verify are amber "Check" with the reason; AI slow or down means the plain
  reading, not a guess; a search matching several cases asks a person to pick.
- **Privacy-first:** the firm picks what each provider sees; read-only Clio; secrets, tokens and note text never
  logged; `bash run.sh purge --matter ID` deletes what we keep about a case.

## Run

```bash
bash run.sh setup     # once: Python 3.11, packages, tests
bash run.sh check     # keys, tools and the Clio connection
bash run.sh ui        # firm dashboard -> http://localhost:8501 (keep internal)
bash run.sh provider  # provider portal -> http://localhost:8502 (the only page providers reach)
bash run.sh up        # or: API + dashboard + n8n in the background (bash run.sh stop to end)
```

| Command | What it does |
|---|---|
| `bash run.sh test` | All tests, no keys or network |
| `bash run.sh digest [--matter ID] [--preview] [--send]` | Daily digest now (`--preview` writes `logs/digest_preview.html`) |
| `bash run.sh gmail` / `bash run.sh gcal` | One-time Google sign-in for email / Google Calendar |
| `bash run.sh purge --matter ID [--with-cache]` | Delete what we keep about one case (`sample` resets the demo) |
| `bash run.sh config` | Settings this run would use (secrets hidden) |

Flags for any command: `--llm anthropic|gemini|mock`, `--cache on|off|only` (`only` = offline demo), `--model`,
`--port`, `--log-level`. More: `bash run.sh help`. First-time setup: [`SETUP.md`](SETUP.md); accounts and keys:
[`SETUP_accounts.md`](SETUP_accounts.md).

## AI and cost

Claude Sonnet 5.5 (`claude-sonnet-5-5`, Structured Outputs). Three small calls per case: lien breakdown, liability
read, case summary. Code checks every output; date math, deadlines, totals and risk levels are code, not AI.
Answers are cached by input, so an unchanged case costs $0. Rough cost: a few cents per case on first load.
Set `LLM_PRICE_IN_PER_MTOK` / `LLM_PRICE_OUT_PER_MTOK` in `.env` to see cost per call in the logs.
Gemini (`gemini-2.5-flash`) and a mock (saved answers, no key) can be swapped in with `--llm`.

## Folders

| Path | What it is |
|---|---|
| `app/config.py` | All settings, read from `.env` |
| `app/clio.py` | Clio loader (GET only, 5 timed steps, retry) |
| `app/snapshot.py` | One case shape; latest + dated copies; saved copy when Clio is down |
| `app/brief.py` | One case brief for the dashboard and `GET /matters/{id}/brief`; never writes |
| `app/kpis.py`, `app/liens.py` | Money cards (field names in `config/fields.yaml`), AI lien breakdown checked by code |
| `app/risks.py` | Case risks by stage (`config/risks.yaml`) |
| `app/digest.py`, `app/deadlines.py`, `app/summary.py` | Daily digest, deadline math in firm time, checked AI summary |
| `app/share.py`, `app/store.py` | Provider share rules; our SQLite DB (`data/lawmonade.db`): shares, views, reviews, edits, digest runs, calendar adds, append-only audit |
| `app/emailer.py`, `app/gcal.py` | Email via Gmail or SMTP; Google Calendar (fixed event ids, safe to retry) |
| `app/llm.py`, `app/claude.py`, `app/gemini.py` | `ask`, `ask_json`, `ask_image`: Claude, Gemini or mock |
| `app/llm_cache.py`, `app/usage.py` | Saved AI answers (`--cache`), token use + cost per call |
| `app/retry.py`, `app/log.py` | Retry with backoff (Clio, Google, Slack, Twilio, Gmail); logging, secrets masked |
| `app/pdf.py`, `app/grounding.py` | PDF text + OCR, and a check that an AI quote is really on the page |
| `app/integrations/` | Slack, Twilio, Word templates, CSV CRM helpers |
| `app/main.py` | API (http://localhost:8000/docs): brief, digest runs, health |
| `ui/dashboard.py` | Firm dashboard: Case brief (`digest_panel.py`), Everything, by date (`timeline.py`), Share with a provider (`share_tab.py`) |
| `ui/provider_app.py` | Provider portal: approved shares only |
| `config/` | `fields.yaml` (Clio field names per firm), `risks.yaml` (stages + thresholds per firm) |
| `scripts/` | `clio_check.py`, `check_setup.py`, `show_config.py`, `extract.py`, `digest.py`, `purge.py`, `make_templates.py` |
| `data/matters/` | Saved copies of Clio cases (not in git) |
| `data/fixtures/llm/` | Saved AI answers for `--llm mock` |
| `n8n/` | `daily_digest.json` schedule (Slack webhook read from env, never stored in the JSON) |
| `tests/` | Tests, no keys needed: `bash run.sh test` |

## Known limits

Single user, no login (the optional "Reviewing as" name is saved with approvals); runs on localhost over http; only
the Litigation stage has stage-specific risks; a Twilio trial account sends Twilio's fixed template instead of our
draft; Google Calendar events aren't updated when a Clio date changes; nothing is written back to Clio. Full list:
[`DEMO_LOG.md`](DEMO_LOG.md#5-limitations-today).

## Stack
Python 3.11, Streamlit, FastAPI, Claude (Anthropic) or Gemini, SQLite + JSON files, Clio Manage API v4 (read-only),
n8n, Gmail / SMTP, Slack webhook, Twilio, Google Calendar API, PyMuPDF + Tesseract.
