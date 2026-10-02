# Law-monade: 90-second video plan

Judges: **PI firm owners** (money, clarity) and **Swans engineers** (does it work in a real firm?).
Rule for every shot: show it working on the real Sapini case, and put one short on-screen label on it.
Label colors: 🟦 Feature · 🟪 Differentiator · 🟩 Guarantee · 🟨 Money.

Recording tips: 1440×900 browser window, zoom 110%, mouse moves slowly, no typing on camera
(pre-fill the search box). Record each shot as its own clip and cut them together; the voiceover is
about 210 words, read at a normal pace.

---

## Shot list

| Time | On screen (clicks) | On-screen label | Voiceover |
|---|---|---|---|
| **0:00–0:06** | Title card over a blurred Clio matter with 160+ entries | 🟨 *"$38K–$465K/yr of attorney + paralegal time at a 100–300 case firm"* | "A PI attorney opens a case with 160 entries in Clio. Getting up to speed takes an hour, or a colleague's time." |
| **0:06–0:12** | Type nothing; click **Open case from Clio** → progress steps → **LIVE FROM CLIO · READ-ONLY** badge | 🟩 *Live Clio data · read-only, never writes* | "Law-monade reads the live case from Clio. Read-only: it can't change anything." |
| **0:12–0:22** | **Case brief** tab: money cards (value $375K vs $100K coverage, $22,180 lien), case summary | 🟦 *At-a-glance case brief* · 🟨 *Value vs coverage in one look* | "In two minutes: what the case is worth, the coverage behind it, and the liens that come off the top." |
| **0:22–0:30** | Scroll up to **What could hurt this case**: McCulloch records 38 days overdue (red); wage records overdue, $214K claim depends on it | 🟪 *Risk detection by case stage* | "It flags what could hurt the case: a records request 38 days overdue, and a $214K wage claim waiting on missing paperwork." |
| **0:30–0:40** | Click an amber card's **Review** link → pop-up with the exact Clio quote + link → click **Looks good** → card turns green "Reviewed by <name>" | 🟩 *Provenance: every number links to its source* · 🟩 *Not over-confident: amber = a person checks* · 🟩 *Logged: who approved what* | "Every number shows where it came from. When the AI isn't sure, it says so and asks a person. Approvals are logged by name." |
| **0:40–0:48** | **Everything, by date** tab: Overdue + Due today sections, then scroll the full list; type in search | 🟦 *Dual mode: 2-minute brief ↔ every entry, by date* | "Need more? Switch to everything in the file, by date, searchable, each line linked to its source." |
| **0:48–0:56** | On an overdue item: **Send email** / **Send text (Twilio)** draft → send; **Add to calendar** | 🟪 *Comms: email · text for urgent external contacts* | "Overdue item? Email or text the provider right from the line, and put it on the calendar." |
| **0:56–1:08** | **Daily digest** → **Preview digest** → Email tab (risks, overdue, what changed) → Slack tab (counts only) | 🟪 *Daily digest: email every weekday, Slack only when urgent* · 🟩 *Slack shows counts, no case details* | "Every morning the attorney gets a digest by email. Slack pings only when something is urgent, and only with counts, never client details." |
| **1:08–1:22** | **Share with a provider** tab: pick McCulloch → tick sections → bill shown as a range → **Approve, create secure link and email it** → open link in new tab (provider's read-only page) → back: "opened 1 time" | 🟦 *Provider portal: one secure, expiring link* · 🟩 *Privacy-first: firm picks exactly what's shared* · 🟦 *Paper trail: every share + view logged* | "Providers keep calling to ask where the case is. Now the attorney picks exactly what they see, approves it, and sends one expiring link. Every share and every view is logged, so there's a paper trail instead of phone tag." |
| **1:22–1:30** | End card: logo, 3 guarantee chips, the money line | 🟩 *Provenance · Human review · Privacy-first* · 🟨 *$38K–$465K/yr* | "Law-monade: up to speed in two minutes, nothing invented, nothing shared without your say." |

---

## Why this order

- **Owners** hear the money in the first 6 seconds and see value vs coverage by second 15.
- **Engineers** see live Clio, read-only, source quotes, human review and logs: the things that decide
  whether this survives a real firm.
- The two differentiators (risks, digest) land in the middle, where attention is highest after the hook.
- The provider share is last among features because it is the longest flow and ends on a visible result
  ("opened 1 time").

## Cut if over time (in this order)

1. Add to calendar (0:48–0:56 keeps email/text only).
2. Search on the by-date tab.
3. Provider page in the new tab (keep the "opened" line only).

## Before recording

- [ ] `.env` has Clio, Gmail and Twilio set; `EMAIL_DEMO_REDIRECT` on, so nothing reaches the fake `.test` addresses.
- [ ] `bash run.sh purge --matter sample` if using the sample, so cards start in "needs review".
- [ ] Run the digest preview and the share flow once off-camera so the AI answers are cached (no waiting on camera).
- [ ] Reviewer name pre-filled; search box pre-filled with "Sapini".
- [ ] Slack channel and phone visible in a second window if you want to show the ping/text arrive (optional, +3 s each).
