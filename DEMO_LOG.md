# Law-monade: demo log

Notes for the 90-second video, the 4-minute pitch and the "anything the judges should know" form field.
Updated: Oct 2, 2026.

---

## 1. What the demo shows

| Step | What you show | What to say |
|---|---|---|
| 1 | **Open case from Clio** → progress steps with times | "Reads the whole Sapini file live from Clio. Read-only: the Clio app has no write permission." |
| 2 | **Case brief** money cards | "Every number shows its source and how sure we are. Amber = a person should check it." |
| 3 | **Everything, by date** | "All 160+ entries in one searchable list. Every line shows where it came from." |
| 4 | **Share with a provider** → tick → preview → approve → email | "The attorney picks exactly what the provider sees, previews it, approves it, and only a secure link is emailed." |
| 5 | Open the link in a new tab → back to **Already shared** | "The provider sees a read-only page. The attorney sees that it was opened." |

---

## 2. How the secure link works

1. **The attorney approves a frozen copy.** Clicking *Approve* saves only the ticked sections and items in our own database (`data/lawmonade.db`, table `shares`), never in Clio.
2. **The app makes a random key.** It has 24 random bytes from Python's `secrets` module (about 10^57 possible values), so it can't realistically be guessed. Link: `<PUBLIC_URL>/?share=<key>`.
3. **The email contains only the attorney's message and that link.** No case details are in the email.
4. **The provider's page reads only the frozen copy.** It never connects to Clio. Notes, emails, case value and strategy are never in the copy, so they cannot leak through it.
5. **Each visit is checked.** A key that is unknown, expired (default 14 days, `SHARE_LINK_DAYS`) or turned off shows: *"This link has expired or was turned off. Contact the law firm."*
6. **The attorney can turn a link off** at any time (**Turn off** in "Already shared").

## 3. How we know the link was opened

- When someone opens the link, the provider page loads, checks the key, and **writes one row** into the table `share_views` (key + time).
- It counts **once per browser visit**. Refreshing the same tab doesn't add more rows.
- **Already shared** reads that table: *"opened 2 time(s), last Oct 2, 11:20 AM"* or *"not opened yet"*.
- What it does **not** do: track email opens (no hidden tracking image) or know *who* opened the link.

Limits of this count:
- If the email is forwarded, a view by someone else counts the same way.
- Some email systems (e.g. corporate "safe links" scanners) open links automatically to check them. That can count as a view even if nobody read it.

## 4. Where emails come from and where they're recorded

- **Sent through Gmail** (the Google account signed in with `bash run.sh gmail`), or through SMTP if `SMTP_*` is set in `.env`. **Not through Clio.**
- **Recorded in our own database** (`audit` table: time, sent to, meant for, subject, which link). Failed sends are recorded too.
- **Not recorded in Clio**, because the hackathon rules allow reading from Clio only.
- **Demo safety:** `EMAIL_DEMO_REDIRECT` sends every email to us instead. The subject says who it was meant for, because the sample contacts have fake `.test` addresses.

---

## 5. Limitations (today)

| Area | Limitation | Why it's OK for the demo |
|---|---|---|
| Link access | Anyone holding the link can open it until it expires (e.g. a forwarded email) | Short expiry, turn off anytime, every view logged |
| Hosting | Runs on `localhost` over plain http; links only open on this laptop | Demo runs on one machine. Providers get a separate app (`bash run.sh provider`, port 8502) that can only show approved shares; only that port would ever go online, the firm dashboard (8501) stays internal |
| Key storage | Keys are stored as-is in the `shares` table (the audit log stores only a hash of each key) | Database is local and not in git |
| Brute force | No limit on repeated wrong keys | Keys can't realistically be guessed |
| Unused setting | `SHARE_LINK_SECRET` is set but not used yet | Planned for signed links |
| Open tracking | Counts page opens, not who opened; scanners may count as opens | Clearly labeled "opened", not "read by" |
| Clio logging | Shares and emails are not written to the Clio matter | Rules forbid writing to Clio |
| Provider matching | Items are matched to a provider by the distinctive word in its name | The attorney sees the matched word and unticks anything wrong before approving |
| Bill amounts | Uses Clio expense amounts for that provider; if missing, the attorney types one | Provider sees only a range, never the billed amount |
| Free-text numbers | Coverage and liens are read out of free-text fields | Marked "Check" in amber, with the reason |
| Sample data | Sample contacts have fake `.test` emails; sample documents don't name providers | Demo redirect for email; live Clio data has per-provider documents |
| Email | Gmail sign-in needs a one-time browser approval; Google may say "unverified app" | One-time setup before the demo |

## 6. Future scope

**Security**
- Ask for a one-time code sent to the provider's email address before showing the page, so a forwarded link alone isn't enough.
- Store only a scrambled (hashed) version of each key, so a stolen database reveals no working links.
- Sign links with `SHARE_LINK_SECRET`; block an address after too many wrong keys.
- Host with https on a firm-approved server, with signed agreements for handling medical information.

**Production path (system design)**
- **Users and roles:** real sign-in (SSO) instead of the "Reviewing as" name, so every approval in the append-only audit log is tied to a person; per-user Clio OAuth so Law-monade only sees what that person can see in Clio (today one firm-wide read-only token).
- **Clio sign-in expiry:** use the stored refresh token to renew the access token on a 401 and retry once, so overnight digests keep working.
- **Medical data at rest:** encrypt snapshots, the AI cache and the database; before real client data goes to an AI vendor, a zero-retention / BAA-type agreement with that vendor. Retention is already one command (`bash run.sh purge --matter ID`).
- **Scale:** a background sync with Clio's `updated_since` (and Clio webhooks) instead of loading a case on click; run the Clio reading steps in parallel. Snapshots are already per case and dated, and the brief is one function (`app/brief.py`) behind both the dashboard and `GET /matters/{id}/brief`.
- **Database:** SQLite (WAL, numbered migrations) is right for one office; the same tables move to Postgres for a multi-office firm.

**Clio integration (needs write permission)**
- Log each share and email on the Clio matter as a communication, so the official case file stays complete.
- Save the provider's reply and uploaded records straight into the right Clio folder.

**Provider experience**
- "Tell me when the case moves": automatic email when the case stage changes (n8n or a daily check with Clio's `updated_since`).
- Let providers upload records and bills through the same secure page.
- A per-provider history of all updates sent.

**Attorney experience**
- A provider-sharing template per attorney (some attorneys share coverage, some don't).
- See who opened what, across all cases, in one place.

---

## 7. Decision log

| Time | Decision | Why |
|---|---|---|
| 09:55 | JSON files for Clio copies and AI summaries, SQLite for shares, views, last-opened and the audit log | JSON is simple and easy to inspect; SQLite is safe when two things write at once |
| 10:05 | New project `lawmonade` built from the `hack/` template | Reuse tested helpers; leave out deadline-specific code |
| 10:12 | Claude (`claude-sonnet-5-5`) as the AI; Gemini off | The Gemini key was rejected; Claude passed the check |
| 10:41 | The provider never sees the billed amount, only a payment range | The attorney's request: keep negotiation room |
| 11:02 | The email carries only a secure link, never case details | Less exposure if an email is forwarded or misdirected |
| 11:10 | App name shown as **Law-monade**; demo firm is the fictional **Brightwater & Vance Injury Law** (`FIRM_NAME` in `.env`) | Clear branding; no real firm's name used |
| 11:31 | Task links open the Tasks tab with a search hint, not the task | Clio opens a single task in edit mode; avoid accidental edits |
| 13:00 | Money cards link to the exact Clio tab (Custom Fields, Activities) and say which field or filter to look for | Clio has no address for one field or for the Expense filter (checked in Clio) |
| 13:00 | People can correct a money card; saved in our DB (card_edits + audit), Clio never changed; card shows "Edited", keeps the Clio number, warns if Clio changes later | Read-only rule; numbers in free text are sometimes wrong |
| 13:15 | Lien card: AI sorts the lien field into lien / paid benefit / pending / defense offset; code checks each quote and amount against the Clio text, adds up only checked liens, and counts other Clio items with the same amount | Taking every $ amount would count the $50,000 exhausted no-fault as a lien; one small cached call per case; falls back to the plain reading if the AI is unavailable |
| 13:25 | Every money card has a review status saved in our DB (card_reviews): needs review / approved / corrected / no review needed. "Looks good" approves that exact number; a new number needs a new look. Source details are behind "Where this comes from" with Looks good / Something wrong? | Make the cards that need a person obvious, keep the rest quiet, and keep a record of who checked what |
| 13:35 | Provider portal is its own app (`ui/provider_app.py`, port 8502); `PUBLIC_URL` points there | One app for firm + providers meant putting the link online also put the firm dashboard online |
| 13:35 | Several Clio cases match a search -> a person picks one | Opening the first match could show the wrong client's case |
| 13:35 | Task notes are not shared unless ticked per task; the billed amount is never stored in a share | Task notes can hold strategy; keep only what the provider sees |
| 13:40 | AI calls a person waits on stop after 20 s (`LLM_UI_TIMEOUT_S`) and the card shows the plain reading | A slow AI froze the brief for 2-4 minutes |
| 13:40 | Lien quote check matches whole words; amounts understand $100k / $1.2M; "100/300" limits are flagged | A cut-off quote ("$22") could pass the check; PI limits are often written in shorthand |
| 13:45 | SQLite: numbered migrations, WAL, append-only audit (triggers) with an actor column, share keys hashed in the audit | Upgrade the DB in place, allow concurrent use, and keep a trustworthy record |
| 13:50 | `app/brief.py` builds the brief for the dashboard and `GET /matters/{id}/brief`; drawing it never writes; approvals record the snapshot seen | One brain, two front ends; no hidden writes |
| 13:50 | Dated snapshots (`SNAPSHOT_KEEP`), field names per firm in `config/fields.yaml`, `bash run.sh purge`, run id on every log line | "What changed", onboarding a new firm, retention, and tracing one case load |
| 14:00 | Daily digest: n8n is only the clock; `app/digest.py` does the work for the schedule AND the "Send digest now" button | The schedule and the button can never disagree; the numbers come from `brief.build`, same as the tab |
| 14:00 | Case summary = option C (approved): code writes the facts, the AI writes 3-5 sentences, code checks each sentence's quote and every number/date in it against the Clio text; falls back to Clio's own words | Readable but verifiable; judges can see nothing was invented |
| 14:00 | Email every weekday; Slack only when something is urgent, with counts only | Silence would look like "it broke"; Slack is noisy and less private |
| 14:00 | Overdue items name who to contact (the contact the task names, else the client, else the assignee) with a one-tap text draft a person sends | Twilio trial can't send free text, and auto-texting clients/providers is risky |
| 14:00 | Money cards: the source link sits inside the card and opens a pop-up; it reads "Review" when a person must check the number and "Reviewed by <name>" after approval | Long source lists didn't fit under the cards; reviews need a name |
