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
| Hosting | Runs on `localhost` over plain http; links only open on this laptop | Demo runs on one machine; real use needs hosting (see future scope) |
| Key storage | Keys are stored as-is in the database | Database is local and not in git |
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
