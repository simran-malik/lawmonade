# Swans Hackathon: Case Digest (Sapini) — Requirements

Last updated: Fri Oct 2, 2026. Source: the 20 briefing slides (`LDG - 8_30 LDG Hackathon.pdf`), `Sapini - manual setup guide.pdf`, `sapini-clio-data.json`.

---

## 0. What we are building (in one picture)

We build a **separate app** (Python + Streamlit, running on your laptop). It does **not** run inside Clio.
Clio is only the **data source**. We read from it over the Clio REST API, and we never write to it.

```
Clio Manage (Sapini matter)            <- read-only API calls only
        |
        v
Our Python app
  1. Clio reader  -> saves a JSON snapshot of the matter (data/matters/<id>/)
  2. Digest       -> code does numbers/dates; Claude writes summary + top 10, each with a source
  3. Cache        -> digest saved as JSON, named by a content hash; AI re-runs only when data changed
  4. SQLite       -> small live tables: share links, link views, last-opened (data/lawmonade.db)
        |
        +--> Attorney page (Streamlit): 2-minute view + deep dive
        +--> Provider page (secure link, expires): only what the attorney chose to share
```

Why separate: the rules say "Clio is only your input… need a database? Bring your own, outside Clio."

### Storage plan (our own, outside Clio)

| What | Where | Why this format |
|---|---|---|
| Clio copy of the matter (notes, emails, tasks, calendar, expenses, docs list, custom fields, contacts) | JSON: `data/matters/<matter_id>/snapshot.json` | Written once by the reader, then only read. Easy to open and debug. |
| AI digest (summary, top 10, contradictions, provider view text) | JSON: `data/matters/<matter_id>/digest_<content_hash>.json` | The hash comes from the snapshot content. Same data = same file = no AI call ("don't digest the whole case again"). |
| Share links | SQLite table `shares`: token, matter_id, provider_contact_id, allowed_fields (JSON), edited_text, created_by, created_at, expires_at, revoked | Changes while the app runs; must be safe when two people use it at once |
| Link views | SQLite table `share_views`: share_token, viewed_at, ip/user_agent | "Has anyone in their office opened it?" |
| Last opened | SQLite table `last_opened`: user_id, matter_id, opened_at | "What changed since I last opened this matter?" |

Rules:
- Write JSON files safely: write to a temp file, then rename, so a crash never leaves half a file.
- SQLite is built into Python (`import sqlite3`), with no server and no install. The database is one file, `data/lawmonade.db`.
- `data/matters/` and `data/*.db` are in `.gitignore`: case data never goes to GitHub.

---

## 1. Rules from the organizers (must follow)

1. Everyone builds on one matter: **Sapini**. The app must read it **live** from our Clio Manage account. Demo it in the video.
2. They **read the repo**. Hardcoded features get spotted fast, so no Sapini text in the code.
3. **Read everything, write nothing** in Clio. Any create/update API call to Clio is not allowed.
4. Must solve **both halves** (slide 8): (a) the firm's team gets up to speed, (b) the medical providers get visibility.
5. "More than an AI chat": a **visual summary** of the case, so nobody has to know what to ask.
6. Submit by **4:00 PM, hard deadline**: GitHub repo, a 90-second video, tech stack, which AI models are used + cost per case, notes for judges.

---

## 2. Pain points (real quotes from the slides)

| Group | Quotes |
|---|---|
| A. Catch up fast (attorney) | "Get me up to speed… without asking anyone" · "What changed since I last opened this matter?" · "Out of 300 entries, show me the 10 that matter" · "Sometimes 2 minutes, sometimes dig into everything" · "When did anyone last talk to the client?" |
| B. Money + priorities (attorney) | "What is the case worth, and what coverage sits behind it" · "What's overdue, what's coming, what's waiting on someone else?" · "How much has the firm already spent?" |
| C. Trust | "If a date is on screen, I need to see where it came from" · "Click anything and open the note, document or email it came from" · "See the client's picture when I open the matter" |
| D. Sharing (attorney) | "Secure way to share part of my case with providers" · "Let me adjust what the provider sees before I send it" · "What did we share, and has anyone in their office opened it?" |
| E. Provider | "What does the firm need from my office right now?" · "Is this case still alive?" · "Is there coverage behind the case?" · "Tell me when the case moves" · "I only see the records I sent" · "Is my patient still showing up to treatment?" |
| F. Engineering | "Don't digest the whole case with AI again every time someone opens it" · "Somewhere in a 200-page scan are the client's primary injuries" |

**Share with providers:** status changes, bills and records (what we owe them and for what), shown as a **range** because bills get negotiated down.
**Never share:** case strategy, anything confidential that doesn't concern the provider. Each attorney may choose differently.

---

## 3. Top 3 pain points and money math

Hourly costs:
- Lawyer: $76.76/hr median × 1.3 = **$99.79/hr**. Wage is sourced ([BLS, 2025](https://www.bls.gov/ooh/legal/lawyers.htm)); the 30% overhead is an assumption.
- Paralegal: $30.24/hr median × 1.3 = **$39.31/hr**. Wage is sourced ([BLS, 2025](https://www.bls.gov/ooh/legal/paralegals-and-legal-assistants.htm)); the 30% overhead is an assumption.

Average firm fee per case: about **$12,300**. That is a $37,249 average car-accident settlement × 33%. Sourced via [CasePeer](https://casepeer.com/blog/personal-injury-statistics), which cites other firms and gives a 30–40% fee range. Treat it as a rough figure.

All case counts and time estimates are **assumptions**: low = 100 active cases, high = 300.

| # | Pain point | Who / what goes wrong | Math per year | Range | Effort |
|---|---|---|---|---|---|
| 1 | Attorney catch-up + priorities (A+B+C) | Attorney or case manager clicks tab by tab or asks a colleague; overdue items get missed | Low 0.25 h × 100 × 12 × $99.79 = $29,936 · High 1 h × 300 × 12 × $99.79 = $359,237 · + lost cases prevented 0–1 × $12.3K | **$30K – $372K** | Medium |
| 2 | Provider visibility (D+E) | Paralegal answers "where is this case?" calls and emails; providers chase settled cases; records arrive late | Low 0.17 h × 100 × 12 × $39.31 = $7,862 · High 0.75 h × 300 × 12 × $39.31 = $106,142 | **$8K – $106K** | Medium |
| 3 | Injuries from 200-page scans (F) | Paralegal or nurse builds the medical chronology by hand | Low 1.5 h × 10 × 12 × $39.31 = $7,076 · High 5.6 h × 30 × 12 × $39.31 = $79,253 | **$7K – $79K** | Large |

Note: PI firms don't bill by the hour, so saved time = more capacity (more cases per person), not more billable hours.
Useful stat: lawyers capture only 3.0 billable hours of an 8-hour day ([Clio Legal Trends 2025](https://clio.com/resources/legal-trends/benchmarks/)).

---

## 4. The pick

**#1 attorney digest + a thin #2 provider view built from the same digest.**
#1 has the biggest money and covers the most quotes. #2 is required (both halves) and is cheap once #1 exists.

---

## 5. MVP

### User flow
1. The attorney opens a matter and sees the **2-minute view**:
   - top numbers: value vs. coverage, liens, money spent, stage
   - "changed since you last opened"
   - overdue / coming / waiting on others
   - the top 10 things that matter
2. Clicks any fact to see the source note, email or document.
3. Opens **Deep dive**: full timeline plus flagged contradictions.
4. Clicks **Share with provider**: picks a provider, ticks what to share, previews, edits, creates a link that expires.
5. The provider opens the link and sees:
   - status, and whether the case is still alive
   - what the firm needs from their office
   - their bills as a range

   The attorney sees that the link was opened.

### Features, in build order (about 6 h)

| # | Feature | Time | Requirement covered |
|---|---|---|---|
| 1 | **Clio reader**: OAuth with read-only scopes, paging, `fields=`, `updated_since`, saved as a JSON snapshot; SQLite tables created on start | 1 h | rules 1, 3 |
| 2 | **Digest engine**: code computes numbers, dates, overdue/coming/waiting and spend. Claude writes the summary, top 10 and contradictions. Every AI item must cite a real source ID or it's dropped. Cached by content hash. | 1.5 h | A, B, C, F (caching) |
| 3 | **Attorney dashboard** (Streamlit): 2-min view, deep-dive tab, click-through to sources, "since last opened" | 1.5 h | A, B, C |
| 4 | **Provider share**: allowlist filtered on the server, edit before sending, signed link that expires, view log, provider page | 1.5 h | D, E |
| 5 | *If time:* poll for stage changes and email the provider (Gmail) | 0.5 h | E ("tell me when the case moves") |

### Do NOT build today
- a chat box
- OCR / medical chronology from the 34–42 MB scans (just list the documents)
- any Clio writes or webhooks
- provider accounts or logins
- Twilio
- support for many matters at once
- visual polish beyond clean

### Risks and how the demo handles them

| Risk | Handling |
|---|---|
| Wrong AI answer | Numbers and dates come from code, not the LLM. Every AI bullet must cite a valid source ID or it's dropped. AI text is labeled. Contradictions are shown, not settled. |
| Privacy / strategy leaks to providers | Filter on the server against an allowlist. Notes are off by default. The attorney previews before sending. Links expire and every view is logged. No keys or case data in git. |
| Missing data | Show gaps openly (e.g. "2 providers sent nothing", empty Insurance and Settlement folders, second surgery with no date). Show when data was last refreshed. |
| AI cost and speed | The content-hash cache re-runs the AI only on changed items. Report cost per case in the submission. |
| "Hardcoded" suspicion | No Sapini strings in the code; everything comes from live Clio reads. Say so in the judges' notes. |

### What Sapini contains that the demo should surface (found by reading the data, not hardcoded)
- **Case value vs. coverage:** $375,000 value against a $100,000 defendant limit, minus a $22,180 Medicaid lien.
- **Coverage contradiction:** notes N2/N3 say Metro-North is self-insured with no limit, but field F6 lists $100K/$300K. That $100K/$300K is Ferrara's personal auto policy.
- **Three versions of how the crash happened** (N5). **Prior ankle injury** the client denied (N6). **PT "discharge" followed by 91 days of visit notes** (N13).
- **Overdue tasks:** McCulloch records (due 8/25/2026), client employment records (due 9/26/2026).
- **Waiting on others:** 3 open tasks start with "By medical provider:".
- **Money spent:** 5 real firm costs ($1,410). The other 9 expenses are provider medical charges (bills/liens), NOT firm spend: show them on the provider side as a range. Split them by Clio data (expense category / provider contact), not by matching text.
- **Per-provider records + itemized bills** exist in folders 04 and 05: a natural source for each provider's view ("I only see the records I sent").

---

## 6. Pitch

**"Gets an attorney up to speed on any case in 2 minutes and gives treating doctors a safe live view, giving back $38K–$465K a year of attorney and paralegal time at a 100–300 case firm."** (#1 + #2 combined, assumption-based.)

## 7. Questions for the organizers
1. Is creating a Clio webhook allowed? It's a write call, but not to case data.
2. For bills shown "as a range": what reduction do firms expect, or should the attorney set it?
3. Is a signed link that expires, with no provider login, secure enough for the provider side?

---

## 8. Clio setup, step by step

### Step 1. Check your region (1 min)
Log in to Clio Manage. If the address bar shows `app.clio.com`, you are on **US**, and everything below uses `https://app.clio.com`.
(EU, CA and AU accounts use other hosts, and a US token won't work there.)

### Step 2. Check the Sapini matter is complete (5 min)
Open Matters → Sapini and check:
- Stage = **Litigation**, Practice area = **Personal Injury**, Status = Open
- Counts (what the Swans setup app actually loads, confirmed): 16 custom fields · 15 contacts (14 related + client) · 42 notes · 69 communications · 14 tasks · 17 calendar entries · 14 expenses · 31 documents
- The app loads more than the manual guide: 5 extra medical providers, 9 "DEMO medical charges" expenses (one per provider), and 18 per-provider records + itemized bill PDFs. The two big scan bundles (doc-19, doc-20) are NOT in Clio.

(Step 8 checks these counts automatically too.)

### Step 3. Create a developer app (5 min)
1. Go to **https://developers.clio.com/apps/new** and log in with the same Clio account.
2. Fill in:
   - **Name:** `Case Digest (hackathon)`
   - **Website URL:** `http://localhost:8501`
   - **Redirect URI:** `http://127.0.0.1:8765/callback`
3. **Permissions:** pick **Read only** for each of these:
   Matters, Contacts, Custom Fields, Documents, Notes, Communications, Tasks, Calendars, Activities, Users, Practice Areas.
   Leave everything else off. **Do not pick Read/Write anywhere.** This makes "write nothing" impossible to break, which is worth showing to the judges.
4. Accept the Developer Terms and create the app.
5. Copy the **App key** (client ID) and **App secret** (client secret).

If the portal refuses the `127.0.0.1` redirect URI, try `http://localhost:8765/callback`.

### Step 4. Save the keys (2 min)
Already done for `lawmonade/.env` (copied from `hack/.env`). For a fresh setup, the keys go in `.env`, which is listed in `.gitignore`:
```
CLIO_BASE=https://app.clio.com
CLIO_CLIENT_ID=...
CLIO_CLIENT_SECRET=...
CLIO_REDIRECT_URI=http://127.0.0.1:8765/callback
```

### Step 5. Get an authorization code (2 min)
Open this in your browser (put your client ID in):
```
https://app.clio.com/oauth/authorize?response_type=code&client_id=YOUR_CLIENT_ID&redirect_uri=http://127.0.0.1:8765/callback&state=hack
```
Click **Allow**. The browser goes to `127.0.0.1:8765/callback?code=XXXX&state=hack`.
The page itself may fail to load. That's fine: copy the `code` value from the address bar.
**The code expires in 10 minutes**, so do Step 6 right away.

### Step 6. Swap the code for tokens (1 min)
```bash
curl -s -X POST https://app.clio.com/oauth/token \
  -d client_id=$CLIO_CLIENT_ID -d client_secret=$CLIO_CLIENT_SECRET \
  -d grant_type=authorization_code -d code=PASTE_CODE \
  -d redirect_uri=http://127.0.0.1:8765/callback
```
Save `access_token` and `refresh_token` in `.env` as `CLIO_ACCESS_TOKEN` and `CLIO_REFRESH_TOKEN`.
- The access token lasts **30 days**. The refresh token does not expire.
- To refresh: POST to the same URL with `grant_type=refresh_token`, `refresh_token`, `client_id` and `client_secret`.

### Step 7. Test with read calls (2 min)
```bash
H="Authorization: Bearer $CLIO_ACCESS_TOKEN"
curl -s -H "$H" "https://app.clio.com/api/v4/users/who_am_i.json"
curl -s -H "$H" "https://app.clio.com/api/v4/matters.json?fields=id,display_number,description,status"
```
Note the Sapini **matter id**. The app should look it up by search, never hardcode it.

### Step 8. Count check (the first thing the app's reader does)
Read each list for that matter and compare with the expected counts in Step 2:
- `notes.json?matter_id=ID`
- `communications.json?matter_id=ID`
- `tasks.json?matter_id=ID`
- `calendar_entries.json?matter_id=ID`
- `activities.json?matter_id=ID&type=ExpenseEntry`
- `documents.json?matter_id=ID`
- `relationships.json?matter_id=ID`
- `matters/ID.json?fields=custom_field_values{value,custom_field}`

API tips:
- Clio returns only `id` and `etag` unless you pass **`fields=`**. Always list the fields you need.
- Results are paged. Use `limit=200` and follow `meta.paging.next`.
- `updated_since=<ISO time>` returns only what changed. Use it for "what changed since last opened" and to skip AI work.
- Rate limit: 600 requests/min per token.

### Step 9. Safety before the first commit
`.gitignore` must include: `.env`, `credentials.json`, `token.json`, `data/*.db`, `data/matters/`. Already set in `lawmonade/.gitignore`. No case text or keys go in git.
