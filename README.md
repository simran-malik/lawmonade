# Law-monade

Built at the Swans Applied AI Hackathon (Law-Di-Gras, San Diego, Oct 2, 2026).

**What it does:** turns a live personal-injury case in Clio Manage into a dashboard.
- **Attorneys** get up to speed in 2 minutes: what the case is worth vs. coverage, what's overdue / coming / waiting on others, what changed since they last looked, and the 10 entries that matter. Every fact links to its source note, email or document.
- **Treating medical providers** get a secure, expiring link showing only what the attorney chose to share: case status, what the firm needs from their office, and their bills as a range.

Clio is read-only input (GET requests only, read-only app permissions). Our own data lives outside Clio.
Full requirements: [`REQUIREMENTS.md`](REQUIREMENTS.md). How it's built (diagram, components, reliability, logging): [`ARCHITECTURE.md`](ARCHITECTURE.md).

## Run

```bash
bash run.sh setup     # once: Python 3.11, packages, tests
bash run.sh check     # keys, tools and the Clio connection
bash run.sh ui        # dashboard -> http://localhost:8501
bash run.sh up        # or: API + dashboard + n8n in the background (bash run.sh stop to end)
```
More commands and flags: `bash run.sh help`. First-time setup steps: [`SETUP.md`](SETUP.md).

## Folders

| Path | What it is |
|---|---|
| `app/config.py` | All settings, read from `.env` |
| `app/llm.py` | `ask`, `ask_json`, `ask_image`: Claude, Gemini or mock (`--llm`) |
| `app/llm_cache.py`, `app/usage.py` | Saved AI answers (`--cache on\|off\|only`), token use + cost per call |
| `app/retry.py`, `app/log.py` | Retry with backoff (Clio, Slack, Twilio, Gmail); logging with `--log-level`, secrets masked |
| `app/claude.py`, `app/gemini.py` | AI clients: 2-minute time limit, timing logs, structured output |
| `app/store.py` | Our SQLite DB (`data/lawmonade.db`): share links, link views, last opened, audit log |
| `app/pdf.py`, `app/grounding.py` | PDF text + OCR, and a check that an AI quote is really on the page |
| `app/integrations/` | Slack, Twilio, Word templates, CSV CRM helpers |
| `app/main.py` | API (http://localhost:8000/docs) |
| `ui/dashboard.py` | Streamlit dashboard |
| `scripts/` | `clio_check.py` (Clio connection + Sapini counts), `check_setup.py`, `show_config.py`, `extract.py` |
| `data/matters/` | JSON copies of Clio matters + cached AI digests (not in git) |
| `n8n/` | Example workflow (Slack webhook read from env, never stored in the JSON) |
| `tests/` | Tests, no keys needed: `bash run.sh test` |
| `REQUIREMENTS.md` | Problem, pain points, money math, MVP, Clio API setup |
| `SETUP.md` / `SETUP_accounts.md` | Setup steps / accounts and keys reference |
| `ARCHITECTURE.md` | Diagram, components, reliability, logging |
| `DEMO_LOG.md` | Demo script, how the secure link works, limitations, future scope, decision log |

## Stack
Python 3.11, Streamlit, FastAPI, Claude (Anthropic) or Gemini, SQLite + JSON files, Clio Manage API v4 (read-only).
