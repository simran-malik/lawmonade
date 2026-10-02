# Accounts and keys (reference, from hack/)

> Copied from `hack/SETUP.md`, with paths changed to `lawmonade/`. Most of this is already done (keys were copied into `lawmonade/.env`). For lawmonade's own setup, see `SETUP.md`.
> Parts about deadlines, Google Calendar, e-signature and n8n `workflow.json` belong to the old hack/ project and are optional here.

**Who does what:** 🧑 = you (accounts, sign-ins, keys, installs on your Mac). 🤖 = already done by Claude in this repo.
Never paste keys into chat. Put them only in `lawmonade/.env`.
Website buttons may have slightly different names than below. Look for the closest match.

| # | Item | Who | Time | Priority |
| --- | --- | --- | --- | --- |
| 1 | Claude API key (paid credit) | 🧑 | 5 min | Must, or use 1b |
| 1b | Gemini API key (free tier) + test | 🧑 (🤖 code done) | 5 min | Optional backup to 1 |
| 2 | Google Cloud: APIs + sign-in for Python | 🧑 (🤖 code done) | 20 min | Must |
| 3 | Google sign-in for n8n | 🧑 | 10 min | Must |
| 4 | Slack webhook | 🧑 (🤖 helper done) | 10 min | Must |
| 5 | n8n running | 🧑 (🤖 workflows done) | 15 min | Must |
| 6 | Twilio texting | 🧑 (🤖 helper done) | 15 min | Should |
| 7 | E-signature sandbox | 🧑 | 10 min | Should (skip if short on time) |
| 8 | Word templates | 🤖 done | 0 | Should |
| 9 | Fake CRM | 🤖 done (🧑 optional Google Sheet) | 5 min | Should |
| 10 | ngrok | 🧑 | 5 min | Nice |
| 11 | Lovable | 🧑 | 5 min | Nice |
| 12 | Screen recording | 🧑 | 2 min | Nice |
| 13 | Speech-to-text | skip | 0 | Skip |

First, once: `cd lawmonade && bash run.sh setup`

**Done for the night? Jump to [Turn off / turn on](#turn-off--turn-on).**

---

## 1. Claude API key 🧑
1. Go to **console.anthropic.com** and sign in.
2. **Billing**: add credit ($10–20 is plenty for a day).
3. **API Keys > Create Key**. Name it `hackathon`. Copy it now (it is shown only once).
4. In `lawmonade/.env`: `ANTHROPIC_API_KEY=` paste the key, and `LLM_PROVIDER=anthropic`.
5. Test: `bash run.sh check`. The Claude line must say OK. If the model fails, set `ANTHROPIC_MODEL` to a model listed in the console.

## 1b. Gemini API key 🧑 (free, no credit card)
Your Google AI Plus plan does **not** include API credits, but the Gemini API has a free tier.
**Free tier: Google may use your prompts to improve its products.** Only send the fake sample documents.

**Get the key (5 min)**
1. Go to **aistudio.google.com** and sign in with your Google account.
2. Click **Get API key** (left menu or top right) > **Create API key**. Pick your `hackathon` Google Cloud project if asked, or let it make one.
3. Copy the key (starts with `AIza`). Don't paste it in chat.
4. Open `lawmonade/.env` and set:
   ```
   GEMINI_API_KEY=AIza...your key...
   GEMINI_MODEL=gemini-2.5-flash
   ```
   Leave `LLM_PROVIDER` as it is. You pick Gemini per run with `--llm gemini`.
5. Check your terminal doesn't have an old Gemini key that would override `.env`:
   ```bash
   echo "terminal key: ${GEMINI_API_KEY:+set}${GEMINI_API_KEY:-not set}"
   ```
   If it says `set` and you didn't mean it: run `unset GEMINI_API_KEY`, and remove the `export GEMINI_API_KEY=...` line from `~/.zshrc` if it's there.

**Test it (3 steps, ~1 min)**
1. Key works:
   ```bash
   bash run.sh check
   ```
   Look for `Gemini said: OK` and then `OK  Gemini API (gemini-2.5-flash)`.
2. Gemini reads a document:
   ```bash
   bash run.sh extract data/samples/depo_notice_lopez.pdf --llm gemini
   ```
   Expect: deposition on **2026-11-04** and "Prep client for deposition" on **2026-10-28**.
3. Gemini reads a scanned page (image):
   ```bash
   bash run.sh extract data/samples/hearing_notice_carter_scanned.pdf --llm gemini
   ```
   Expect: hearing on **2026-12-03**, opposition due **2026-11-18**.

**If something fails**
- `API key not valid`: copy the key again from AI Studio; check for spaces in `.env`.
- `model not found`: in AI Studio, pick a model name from the list and set `GEMINI_MODEL`.
- `429` / `quota` / `rate limit`: you hit the free-tier limit. Wait a minute, or use `--llm anthropic` / `--llm mock`. Your limits are shown in AI Studio.
- Nothing for 90 s, then an error: Google is slow or blocked on this Wi-Fi. Use `--llm anthropic`.

**Using it**: `bash run.sh ui --llm gemini` (dashboard), `bash run.sh extract <pdf> --llm gemini` (terminal).
In code: `from app.gemini import gemini_json, gemini_text, gemini_image`.

## 2. Google Cloud: APIs + sign-in for Python 🧑
1. Go to **console.cloud.google.com**. Top bar: project picker > **New project** > name `hackathon` > Create. Make sure it is selected.
2. **APIs & Services > Library**. Search and **Enable** each: Google Calendar API, Gmail API, Google Drive API, Google Sheets API, Google Docs API.
3. **Google Auth Platform** (older name: OAuth consent screen) > **Get started**:
   app name `Law-monade`, your email, audience **External**, your email as contact > Create.
   (Tip: use the same project as your Gemini key from step 1b, so everything lives in one place.)
4. **Audience > Test users > Add users**: add your Gmail.
5. **Clients > Create client** > type **Desktop app** > name `python` > Create > **Download JSON**.
6. Rename the file to `credentials.json` and move it into `lawmonade/`.
7. In Google Calendar (calendar.google.com): **Other calendars > + > Create new calendar** named `Hackathon Demo`. Open its settings > **Integrate calendar** > copy **Calendar ID** into `.env` as `GOOGLE_CALENDAR_ID`.
8. Test: `bash run.sh calendar`. A browser opens. You will see "Google hasn't verified this app": click **Continue** (it's your own app). Allow. It should say OK.

## 3. Google sign-in for n8n 🧑 (do after step 5)
1. Same Google Cloud project > **Clients > Create client** > type **Web application** > name `n8n`.
2. **Authorized redirect URIs > Add URI**: `http://localhost:5678/rest/oauth2-credential/callback` > Create.
3. Copy the **Client ID** and **Client secret** (keep the tab open).
4. In n8n: **Credentials > Add credential** > search **Gmail OAuth2 API** > paste Client ID and secret > **Sign in with Google** > Continue > Allow. It should say "Connection successful".
5. Repeat step 4 for **Google Calendar OAuth2 API** and **Google Sheets OAuth2 API** (same ID and secret).

## 4. Slack webhook 🧑
1. If you have no workspace: **slack.com > Get started** > make a free workspace. Make a channel `#docket`.
2. Go to **api.slack.com/apps > Create New App > From scratch** > name `Law-monade`, pick your workspace.
3. **Incoming Webhooks** > turn **On** > **Add New Webhook to Workspace** > pick `#docket` > Allow.
4. Copy the webhook URL (starts with `https://hooks.slack.com/`) into `.env` as `SLACK_WEBHOOK_URL`.
5. Test: `bash run.sh check --slack`. A message should appear in `#docket`.

🤖 In code: `from app.integrations.slack import notify; notify("text")`

## 5. n8n running 🧑
1. Install Docker: `brew install --cask docker`. Open the **Docker** app once and wait until it says it is running.
2. Download n8n now (big, don't do it on hackathon Wi-Fi): `docker pull n8nio/n8n`
3. Start it: `bash run.sh n8n`. Open **http://localhost:5678**. Make the local owner account (stays on your laptop).
4. Import both workflows: **Workflows > ⋯ (or Add workflow > ⋯) > Import from File**:
   `lawmonade/n8n/example_daily_digest_from_hack.json`. In each, paste your Slack URL into the Slack node.
5. Test the digest: start the API in another tab (`bash run.sh api`), read a sample in the UI first (`bash run.sh ui`), then in n8n open the digest workflow and click **Test workflow**. A Slack message should arrive.
6. Now do step 3 (Google sign-in for n8n).

## 6. Twilio texting 🧑 (for intake-style briefs)
1. Go to **twilio.com/try-twilio** and sign up. Verify your email and your phone.
2. Console home: copy **Account SID** and **Auth Token** into `.env` (`TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`). Never paste the token in chat.
3. **Get a phone number** (free trial number). Put it in `.env` as `TWILIO_FROM_NUMBER` (format `+1XXXXXXXXXX`).
4. **Limited trial accounts can't send your own words**, only one of Twilio's fixed templates (error `572006`).
   Set in `.env`:
   ```
   TWILIO_TRIAL_TEMPLATE=sms_appointment_reminders
   ```
   The phone then gets Twilio's fixed reminder text. The message the app *meant* to send (with real names and dates)
   is printed in the terminal and returned as `intended_body`, so show that on screen in the demo.
   Templates you can pick: `sms_2fa`, `sms_appointment_reminders`, `sms_order_confirmation`, `sms_delivery_updates`,
   `sms_customer_support`, `sms_marketing_promotions`, `sms_event_notifications`, `sms_account_alerts`,
   `sms_feedback_surveys`, `sms_internal_alerts`. You can't change their wording, dates or names.
   On a paid (upgraded) account, leave `TWILIO_TRIAL_TEMPLATE` empty to send your own text.
5. Test: `bash run.sh check --sms +1YOURPHONE` (your own verified number; trial allows up to 5 verified numbers).
   For one run you can also pick a template with a flag: `bash run.sh check --sms +1YOURPHONE --sms-template sms_event_notifications`.
6. If it fails, the check shows Twilio's error code and a hint. More detail: Twilio **Monitor > Logs > Messaging**.

🤖 In code: `r = send_sms("+1...", "Hi Maria, your deposition is Nov 4 at 10 AM")` then show `r["intended_body"]` on screen.

## 7. E-signature sandbox 🧑 (only matters for retainer-style briefs)
1. Go to **developers.docusign.com** > create a free **developer account** (sandbox, no real signatures).
   Or use Dropbox Sign: sign up, then **Settings > API** for an API key; its test mode is free.
2. Save the login. No code is wired up yet. On the day, the fast path is: fill the template (item 8), then either
   call the e-sign API, or show a "Send for signature" button that emails the filled document.

## 8. Word templates 🤖 done
- `data/templates/retainer_agreement.docx` and `letter_of_representation.docx` have `{{ fields }}` like `{{ client_name }}`.
- Use: `from app.integrations.docs import render_docx; render_docx(template, {"client_name": "..."}, "out.docx")`
- Edit them in Word. Type each `{{ field }}` in one go (don't format half of it), or the fill can break.
- Demo templates only. Not real legal documents.

## 9. Fake CRM 🤖 done, 🧑 optional Google Sheet
- `data/crm_leads.csv` has 10 made-up leads (some good, some bad: old accident, workers comp, client at fault).
- Use: `from app.integrations.crm import load_leads`
- Optional, looks better in a demo: **sheets.google.com > Blank > File > Import > Upload** `crm_leads.csv`.
  Then **File > Share > Publish to web** > pick the sheet > **CSV** > Publish > copy the link into `.env` as `CRM_CSV_URL`.
  Now `load_leads()` reads the live sheet, and n8n's Google Sheets node can write to it.
- In the pitch: "This sheet stands in for Lawmatics or Filevine."

## 10. ngrok 🧑 (only if an outside service must reach your laptop)
1. Sign up at **ngrok.com**. Copy your **authtoken** from the dashboard.
2. `brew install ngrok` then `ngrok config add-authtoken YOUR_TOKEN`
3. Test: `bash run.sh api` in one tab, `ngrok http 8000` in another. Open the `https://...ngrok...` link + `/docs`.

## 11. Lovable 🧑 (only if Streamlit looks too plain)
1. Sign up at **lovable.dev** (Google sign-in is fine). Check how many free messages you get per day.
2. Test one prompt tonight: "A dashboard for a law firm paralegal: table of deadlines with status badges and an Approve button."
3. To connect it to your API on the day, you need ngrok (item 10).

## 12. Screen recording 🧑
1. QuickTime is built in: **File > New Screen Recording**. Click Options and pick your microphone.
2. Record 10 seconds now to check sound. Tomorrow at ~3:40 PM, record a 2-minute backup demo.

## 13. Speech-to-text: skip
Swans says they don't build voice agents. If a brief is about call recordings, send the audio to an API on the day.

---

# How to use n8n tomorrow

**Rule: Python does the thinking, n8n does the moving.** Keep AI and logic in the API (`bash run.sh api`). Use n8n only to connect apps. It's easier to debug and to show.

From inside n8n, your laptop's API is `http://host.docker.internal:8000` (not `localhost`).

**Recipe A: email in → deadlines → Slack** (5 nodes)
1. **Gmail Trigger**: "Message received", filter `has:attachment`, turn on "Download attachments".
2. **HTTP Request**: POST `http://host.docker.internal:8000/documents`, Body = **Form-Data**, field `file` = type **n8n Binary File**, input field `attachment_0`.
3. **Slack** (or HTTP Request to your webhook): "{{ $json.count }} dates found, {{ $json.needs_review }} need review."

**Recipe B: new lead → instant text + alert** (intake briefs)
1. **Webhook** (or **Google Sheets Trigger**: row added to the fake CRM sheet).
2. **HTTP Request** to your API (e.g. `/leads/score`, which you write on the day with `ask_json`).
3. **IF** score is high > **Twilio** node: text the lead > **Slack**: "Call Grace Liu now".

**Recipe C: daily digest** (already built: `n8n/daily_digest.json`)

**Tips**
- Click **Test step** on each node and look at its output before adding the next one.
- **Pin** a node's output (pin icon) so you don't re-trigger Gmail every test.
- When done: **⋯ > Download** the workflow JSON into `n8n/` and commit it. Judges can see it in the repo.
- Show the n8n canvas in the pitch for ~10 seconds. It makes "how this plugs into the firm" obvious.

---

# Turn off / turn on

What runs while you work: the **API** (port 8000), the **dashboard** (port 8501), **n8n** in Docker (port 5678),
**Docker Desktop**, and maybe **ngrok**. Your data is safe when you stop them:
our data stays in `data/lawmonade.db` and `data/matters/`, n8n keeps your account and workflows (in Docker's `n8n_data` volume),
and Google/Twilio/Slack keys stay in `.env`.

## Turn off (tonight)
```bash
cd ~/Documents/"Applied AI Hackathon"/lawmonade
bash run.sh stop --docker      # stops dashboard, API, n8n, ngrok, and quits Docker Desktop
bash run.sh status             # everything should say "down"
```
Then close the terminal tabs. Leave out `--docker` to keep Docker Desktop open.

By hand instead: press **Ctrl+C** in each terminal tab (press twice if it hangs), then quit Docker from the whale icon in the menu bar.

## Turn on (tomorrow)
**Easy way (one command, runs in the background):**
```bash
cd ~/Documents/"Applied AI Hackathon"/lawmonade
bash run.sh up                 # opens Docker if needed, starts n8n, API and dashboard
bash run.sh status             # wait ~10 s; all should say "UP"
bash run.sh check              # keys still OK
```
Then open:
- Dashboard: http://localhost:8501
- API: http://localhost:8000/docs
- n8n: http://localhost:5678 (log in with the account you made; workflows are still there)

Pick the AI for the day with a flag: `bash run.sh up --llm anthropic` (or `gemini`, `mock`).
If something misbehaves, read its log: `tail -f logs/api.log` or `tail -f logs/ui.log`.

**One tab per app (easier to see errors, good while building):** open 3 terminal tabs in `lawmonade/`:
1. `bash run.sh api`
2. `bash run.sh ui`
3. `open -a Docker`, wait for the whale icon to stop animating, then `bash run.sh n8n`

## Morning checklist (at the hackathon)
1. Connect to Wi-Fi (phone hotspot as backup).
2. `bash run.sh up` then `bash run.sh status` then `bash run.sh check`.
3. Do one real read to warm up Claude: `bash run.sh extract data/samples/depo_notice_lopez.pdf --llm anthropic`.
4. Start the git repo (README > Git setup).
5. Read the brief, then build. `bash run.sh stop` any time you need a clean restart.

