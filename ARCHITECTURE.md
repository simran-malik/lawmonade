# Law-monade: architecture

Law-monade reads one personal-injury case **read-only** from Clio Manage. It does two things with it:
1. Gives the firm's team a one-screen case brief and timeline, where every fact links back to its source in Clio.
2. Lets an attorney share an approved, read-only update with a treating medical provider.

## Diagram

```mermaid
flowchart LR
  subgraph Sources["Case data (read-only)"]
    CLIO["Clio Manage API<br/>GET only"]
    SAMPLE["Sample file<br/>DEMO_FILE"]
  end

  subgraph Core["app/"]
    LOADER["clio.py<br/>loader, 5 timed steps"]
    RETRY["retry.py<br/>backoff"]
    SNAP["snapshot.py<br/>one case shape"]
    KPIS["kpis.py<br/>money cards"]
    SHARE["share.py<br/>provider share rules"]
    LLM["llm.py<br/>ask / ask_json / ask_image"]
    CACHE["llm_cache.py<br/>on / off / only"]
    USAGE["usage.py<br/>tokens + cost"]
    EMAIL["emailer.py<br/>Gmail or SMTP"]
    NOTIFY["integrations/<br/>Slack, Twilio"]
    LOG["log.py<br/>stage timing + redaction"]
  end

  subgraph Storage["Our storage (outside Clio)"]
    JSON[("data/matters/id/snapshot.json")]
    DB[("SQLite data/lawmonade.db<br/>shares, share_views,<br/>last_opened, audit")]
    LLMDISK[("data/cache/llm")]
  end

  subgraph AI["AI providers"]
    CLAUDE["Claude<br/>Structured Outputs"]
    GEMINI["Gemini<br/>JSON mode"]
    MOCK["Mock<br/>data/fixtures/llm"]
  end

  subgraph UI["ui/ (Streamlit)"]
    DASH["dashboard.py :8501<br/>firm only, internal"]
    PROV["provider_app.py :8502<br/>providers: approved shares only"]
  end
  BRIEF["brief.py<br/>one case brief"]

  CLIO -->|"GET + retry"| LOADER
  RETRY -.-> LOADER
  LOADER --> SNAP
  SAMPLE --> SNAP
  SNAP <--> JSON
  SNAP --> BRIEF --> DASH
  BRIEF --> API
  JSON -->|"Clio down: saved copy"| DASH
  BRIEF --> KPIS
  DASH --> SHARE --> DB
  SHARE --> EMAIL
  RETRY -.-> EMAIL
  RETRY -.-> NOTIFY
  DB --> PROV
  LLM --> CACHE <--> LLMDISK
  CACHE --> CLAUDE
  CACHE --> GEMINI
  LLM --> MOCK
  CLAUDE --> USAGE
  GEMINI --> USAGE
  API["main.py<br/>FastAPI /matters/id/brief"] --> LLM
  N8N["n8n<br/>schedules, Slack"] --> API
```

Data moves one way: **Clio → snapshot → screens**. Nothing in the app writes to Clio. Everything we create (share links, views, audit log, saved AI answers, which items we put on Google Calendar) lives in our own storage.

## Components

Each component can be swapped, can be tested on its own, and is configured from `.env` or a `run.sh` flag.

| Component | Input → Output | Can be swapped for | Config | Tests |
|---|---|---|---|---|
| `clio.py` loader | matter search → snapshot, in 5 progress steps | sample file, another case system (Filevine, …) | `CLIO_*` | `test_clio_links`, `test_retry` |
| `snapshot.py` | Clio or sample data → one case shape; latest + dated copies (`SNAPSHOT_KEEP`); find a saved copy; purge | SQLite/Postgres store | `SNAPSHOT_DIR`, `DEMO_FILE` | `test_snapshot_fallback` |
| `brief.py` | snapshot → cards (+ corrections, review status), lien status, risks, counts; never writes | — | — | `test_brief` |
| `risks.py` | snapshot (+ our dated copies) → the top 1-2 risks for the case's stage, red/amber/green, each with a why line and a Clio link. Litigation: overdue/upcoming deadlines, last client contact, liability (AI quote, checked by code). Every stage: days since activity, days in stage. Never writes | — | `config/risks.yaml` (stage names + thresholds per firm) | `test_risks` |
| `kpis.py` | snapshot → money cards, each with source + Exact/Calculated/Check | — | `config/fields.yaml` (field names per firm) | `test_kpis` |
| `share.py` + `store.py` | snapshot + attorney choices → frozen share (task notes opt-in, range not billed amount), 24-byte token, expiry; SQLite with numbered migrations, WAL, append-only audit | Postgres; signed links | `SHARE_LINK_DAYS`, `PUBLIC_URL` (provider portal) | `test_share`, `test_store` |
| `emailer.py` | to, subject, text → sent email (link only, never case details) | SMTP, SendGrid | `EMAIL_*`, `SMTP_*` | — |
| `llm.py` | prompt (+ Pydantic schema) → text or a checked object | any provider with JSON output | `--llm anthropic\|gemini\|mock`, `--model` | `test_llm_mock` |
| `llm_cache.py` | (provider, model, schema, prompt) → saved answer | Redis | `--cache on\|off\|only` | `test_llm_cache` |
| `usage.py` | tokens per call → log line + totals (cost per case) | provider billing export | `LLM_PRICE_*_PER_MTOK` | `test_llm_mock` |
| `retry.py` | function + "safe to repeat?" → result, or the original error | `tenacity` | defaults in code (3 tries, 10 s cap) | `test_retry` |
| `log.py` | events → one line per stage, secrets masked | JSON logs → Datadog etc. | `--log-level` | `test_log` |
| `grounding.py` | AI quote + page words → verified / needs_review / hallucination | — | `--ocr-threshold` | `test_smoke` |
| `ui/` | dashboard (firm, :8501) and provider portal (:8502, approved shares only) | any front end (calls `brief.build`) | `--port` | manual |
| `main.py` + n8n | HTTP → app functions; schedules → Slack | cron | `SLACK_WEBHOOK_URL` (env only) | `/health` |
| `digest.py` + `deadlines.py` + `summary.py` | case → daily email (+ Slack if urgent), once per case per day | APScheduler / a job queue; SendGrid | `DIGEST_*`, `FIRM_EMAIL_DOMAINS` | `test_digest` |

## Daily digest

One email per case every weekday morning, and a Slack ping **only** when something is urgent. The n8n schedule
(`n8n/daily_digest.json`, 6:55 AM firm time, Mon-Fri) and the **Send digest now** button on the Case brief tab call the
same function, `app/digest.py: run()`.

```mermaid
flowchart LR
  CRON["n8n schedule<br/>weekdays 6:55 firm time"] -->|"GET /digest/matters<br/>POST /matters/id/digest/run"| RUN
  BTN["Case brief tab<br/>Send digest now"] -->|"the copy on screen"| RUN
  RUN["digest.run()<br/>claim run_key (SQLite)"] --> LOAD["fresh Clio read<br/>else saved copy + age"]
  LOAD --> B["brief.build()<br/>same numbers + risks as the tab"]
  LOAD --> D["deadlines.py<br/>firm time zone"]
  LOAD --> S["summary.py<br/>AI sentences, each checked"]
  LOAD --> C["what changed<br/>vs. last digest's snapshot"]
  B & D & S & C --> R["render: email (always)<br/>Slack (urgent only, counts only)"]
  R --> OUT["digest_runs row + audit"]
```

| Part | What it does | Edge cases handled |
|---|---|---|
| `digest_runs` (SQLite) | One row per case per firm day (scheduled) or per click (manual); status per channel | Unique `run_key` + `BEGIN IMMEDIATE`: an n8n retry or a double click never sends twice. A failed run resumes and redoes only the channel that didn't go out. A crashed run is taken over after 10 min. |
| Case risks | "What could hurt this case" in the email (top 1-2 from `risks.py`, then other checks); same top risks in the digest bar on the Case brief tab | Slack adds red risk names only, and only when it pings anyway (risks never ping on their own); the button sends the risks shown on screen |
| `deadlines.py` | Overdue / long overdue (>90 days) / due today-tomorrow / next 14 days / no due date; SOL | Firm-time-zone days (UTC evening is still "today" in LA); only open tasks; past events never "overdue"; cancelled entries skipped; Clio's SOL reference object isn't treated as a date |
| Contact to text | For each overdue task: the contact it names, else the client, else the assigned staff member; `sms:` link with an editable draft | A person sends it (nothing auto-texted); no amounts in drafts; "no phone in Clio" shown instead of a dead link |
| `summary.py` (option C) | Facts line by code + 3-5 AI sentences from Clio fields, notes, emails, open tasks | Each sentence must quote its source word for word and may not add a number, date or month that isn't in the quote; otherwise dropped. Nothing passes / AI down / slow -> Clio's own case-summary words. Cached by input, so an unchanged case costs $0. |
| Recipients | Responsible attorney in Clio, else `DIGEST_RECIPIENTS` | Addresses outside `FIRM_EMAIL_DOMAINS` dropped; none left -> recorded as `no_recipients` + Slack ops warning |
| Stale data | Clio down -> newest saved copy with a red "data is N h old" banner | Older than `DIGEST_MAX_AGE_H` (48 h): sends "digest unavailable" instead of old numbers |
| Sends | Email via `emailer.py`, Slack via webhook | Timeout / 500 = "maybe sent": recorded as `unknown`, never auto-resent. Closed cases skipped by the schedule. Manual re-send within 2 min asks first. |

API: `GET /digest/matters`, `POST /matters/{id}/digest/run` (`{"trigger","actor","dry_run","force","email_only"}`,
optional `X-Api-Key` = `DIGEST_API_KEY`), `GET /matters/{id}/digest/runs`. CLI: `bash run.sh digest [--matter ID] [--send]`.

## Add to Google Calendar

On the **Everything, by date** tab, under the search bar, **Add all to calendar** puts every task and calendar entry dated
today or later (open tasks only) that isn't on the calendar yet onto `GOOGLE_CALENDAR_ID`. Each task and calendar row
also has its own **Add to calendar** button (works for past and finished items too); once added it shows **✓ On calendar**
with a link to the event. Code: `app/gcal.py`, `ui/timeline.py`. Setup once: `bash run.sh gcal`.

| Part | What it does | Edge cases handled |
|---|---|---|
| Fixed event id | `lm` + hash of calendar + case + item | A double click, a retry after a timeout, or two people pressing at once: Google refuses the second insert (409) and we count it as "already on your calendar". So the insert is safe to retry. |
| `calendar_adds` (SQLite) | One row per item per calendar: event id, link, who, when (+ an audit line) | Drives "Add all" (skips what's there) and the ✓ on each row. Changing `GOOGLE_CALENDAR_ID` starts fresh for the new calendar. Purge removes the rows, not the Google events. |
| Event shape | Task -> all-day event on its due day (firm time zone). Calendar entry -> its start/end time (1 h if Clio has no end) | Description has the case, the Clio source line and the link back into Clio. Items without a date get no button. |
| Errors | "Add all" keeps going past one bad item | Sign-in expired or wrong calendar id: stops after the first item and says how to fix it. |

Not copied later: if a date changes in Clio, the Google event keeps the old one (revisit: update events whose Clio item changed).

## Reliability

**Retries** (`app/retry.py`): exponential backoff (0.5 s, 1 s, 2 s plus a little randomness, or the server's `Retry-After`), capped at 10 s total so the screen never hangs.

| Call | Safe to repeat? | Retried on | Never retried |
|---|---|---|---|
| Clio GET | yes | timeout, connection error, 429, 5xx | other 4xx |
| Google Calendar insert | yes (fixed event id: a repeat gets 409 = already added) | timeout, connection error, 429, 5xx | other 4xx |
| Gmail / Slack / Twilio send | **no** | connection error (nothing sent), 429, 503 | timeout, 500, other 4xx: the message may already have gone out, and a provider getting the same email twice is worse than a clear error |
| Claude | — | the Anthropic SDK retries once itself | — |

**When something fails:**
- **Clio unreachable or token expired:** the screen shows the newest copy saved from Clio and how old it is. If there's none, it offers the sample case. The error message always says what to do next.
- **AI slow:** calls a person waits on stop after 20 s (`LLM_UI_TIMEOUT_S`); the lien card shows the plain reading.
- **AI unavailable:**
  - `--cache only` replays saved answers with no network (the offline demo).
  - `--llm mock` uses fixtures, with no key needed.
- **Bad input:** Clio field lists fall back to simpler ones if Clio rejects a field. Snapshot and cache files are written with temp file + rename, so a crash never leaves half a file.

**Security boundaries:**
- Providers reach only `ui/provider_app.py` (port 8502), which reads frozen, approved shares and nothing else. The firm dashboard (8501) stays internal.
- A search matching several Clio cases asks a person to pick; it never opens the first one.
- The audit log is append-only (SQLite triggers), records the actor, and stores a hash of each share key, never the key.

## Logging

`app/log.py`. Set the level with `--log-level DEBUG|INFO|WARNING|ERROR` (or `LOG_LEVEL` in `.env`). Each stage logs one line, with a run id shared by every line of one case load:

```
12:41:03 INFO    a3f9c1 lawmonade.clio   [clio.notes] 1.1s, notes=42, communications=69
12:41:09 INFO    a3f9c1 lawmonade.llm    [llm] 4.2s, schema=LienBreakdown, provider=anthropic, cache=miss
12:41:09 INFO    a3f9c1 lawmonade.llm    [llm.usage] anthropic claude-sonnet-5-5 in=812 out=240 cost=$0.0xx
12:41:20 WARNING a3f9c1 lawmonade.retry  [retry] clio GET: status 503, try 2/3 in 0.5s
```

**Never logged:** API keys, OAuth tokens, share tokens, document or note text, full email addresses. As a safety net, a filter on the handler masks `sk-ant-…`, `Bearer …`, `Basic …`, Slack webhook URLs, `token=`/`share=`/`secret=` values and email names.

## Configuration

`.env` holds the defaults (see `.env.example`). `run.sh` flags override them for one run:

```bash
bash run.sh ui --llm mock --cache only --log-level DEBUG
```

Secrets live only in `.env`, `token*.json` and `credentials.json`, and all of them are in `.gitignore`. The n8n workflows read the Slack webhook from the environment (`$env.SLACK_WEBHOOK_URL`).

## Testing

`bash run.sh test` runs every test with no keys and no network. Clio, HTTP and AI calls are replaced with fakes, and retries use a fake clock.

## Known limits (prototype)

- Single user, no login.
- Share links are bearer links over http on localhost.
- Share tokens are stored in plain text.
- The provider page has no rate limit.
- Email isn't logged back to Clio, because that needs write access.

See `DEMO_LOG.md` for the full list and future scope.
