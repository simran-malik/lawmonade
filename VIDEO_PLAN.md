# Law-monade: 90-second video plan

Judges: **PI firm owners** (money, clarity) and **Swans engineers** (does it work in a real firm?).
Rule for every shot: show it working on the real Sapini case, with one text headline saying what it proves.
Label colors: 🟦 Feature · 🟪 Differentiator · 🟩 Guarantee · 🟨 Money.

No voiceover: the on-screen text tells the story. Each shot gets one **headline** (top of the
screen, the point being shown) and up to two small **tags** (next to the thing on screen).
Headlines stay 6-9 words so they can be read in 2-3 seconds; each stays up for the whole shot.

Recording tips: 1440×900 browser window, zoom 110%, mouse moves slowly, pause ~2 s on each thing
being shown, no typing on camera (pre-fill the search box). Silent screen recording is fine; I add a
quiet music bed only if you want one.

---

## Shot list

| Time | On screen (clicks) | Headline (top) | Tags (next to the item) |
|---|---|---|---|
| **0:00–0:06** | Title card over a blurred Clio matter with 160+ entries | **160+ entries. One hour to catch up. Every case.** | 🟨 $38K–$465K/yr of time back at a 100–300 case firm |
| **0:06–0:12** | Click **Open case from Clio** → progress steps → **LIVE FROM CLIO · READ-ONLY** badge | **Reads the live case straight from Clio** | 🟩 Read-only: never changes Clio |
| **0:12–0:22** | **Case brief** tab: money cards (value $375K vs $100K coverage, $22,180 lien), case summary | **The whole case at a glance, in 2 minutes** | 🟦 At-a-glance brief · 🟨 Value vs coverage vs liens |
| **0:22–0:30** | **What could hurt this case**: McCulloch records 38 days overdue (red); $214K wage claim waiting on overdue records | **Flags what could hurt the case, before it does** | 🟪 Risk detection by case stage |
| **0:30–0:40** | Amber card → **Where does this come from?** → Clio quote + link → **Looks good** → green "Reviewed by <name>" | **Every number shows its source** | 🟩 Amber = not sure, a person checks · 🟩 Every approval logged by name |
| **0:40–0:48** | **Everything, by date** tab: Overdue + Due today, scroll, search | **Need more? Every entry, by date, searchable** | 🟦 Dual mode: brief ↔ full file |
| **0:48–0:56** | Overdue item: **Send email** / **Send text (Twilio)** → send | **Chase overdue items in one click** | 🟪 Email · Text for urgent outside contacts |
| **0:56–1:08** | **Preview digest** → Email tab (risks, overdue, what changed) → Slack tab | **A daily digest, so nothing slips** | 🟪 Email every weekday · Slack only when urgent · 🟩 Slack shows counts, no client details |
| **1:08–1:22** | **Share with a provider**: pick McCulloch → tick items → bill as a range → **Approve, create secure link and email it** → open link → back: "opened 1 time" | **Providers get answers without calling the firm** | 🟩 Firm picks exactly what's shared · 🟦 One expiring link · 🟦 Every share + view logged = paper trail |
| **1:22–1:30** | End card | **Law-monade: up to speed in 2 minutes** | 🟩 Provenance · Human review · Privacy-first · 🟨 $38K–$465K/yr |

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
