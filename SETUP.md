# Law-monade: setup steps

Do these once, in order, in **Terminal on your Mac**. About 10 minutes.

Already done for you:
- the project files and `run.sh`
- `.env`, with Clio keys + tokens, Claude/Gemini keys and a share-link secret copied in
- `.gitignore`, so keys, the database and case data never reach GitHub
- the first git commit ("Initial commit: Skeleton")

---

## Step 1. Stop the old project (hack/ uses the same ports)
```bash
cd ~/Documents/"Applied AI Hackathon"/hack && bash run.sh stop
```
Check that the ports are free:
```bash
lsof -nP -iTCP:8000 -iTCP:8501 -iTCP:5678 -sTCP:LISTEN
```
No output means they are free. If a line shows up, stop it: `kill <PID>`, using the number in the PID column.

## Step 2. Install (2–4 min)
```bash
cd ~/Documents/"Applied AI Hackathon"/lawmonade
bash run.sh setup
```
This installs Python 3.11 and all packages, then runs the tests. You're done when it prints `Setup done.` and the tests say `passed`.

## Step 3. Run the tests again (10 sec)
```bash
bash run.sh test
```
Every test should pass. No keys are needed for the tests.

## Step 4. Check keys, tools and Clio (30 sec)
```bash
bash run.sh check
```
These lines must say **OK**:
- `.env`
- `Claude API` (or `Gemini API`)
- `Clio API (signed in as Simran Malik)`
- `Share link secret`

Slack and Twilio lines may say FAIL. They are optional.

| FAIL line | Fix |
|---|---|
| Claude API | Fix `ANTHROPIC_API_KEY` in `.env` |
| Clio API: HTTP 401 | Token expired or wrong. Redo `REQUIREMENTS.md` section 8, steps 5–6, and paste the new tokens into `.env` |
| Share link secret | Run `python3 -c "import secrets;print(secrets.token_urlsafe(32))"` and paste the result as `SHARE_LINK_SECRET=` in `.env` |

## Step 5. Check the Sapini data in Clio (30 sec)
```bash
bash run.sh clio
```
Every row should say **yes**. To see the items behind the counts: `bash run.sh clio --details`

## Step 6. Start the dashboard
```bash
bash run.sh ui
```
Open http://localhost:8501, then press `Ctrl + C` to stop it.
To run everything in the background instead, use `bash run.sh up`, then `bash run.sh status` and `bash run.sh stop`.

## Step 7. Push to GitHub. The repo is the submission.
The first commit is already made. Create an **empty** repo at https://github.com/new (name `lawmonade`, no README), then:
```bash
git remote add origin https://github.com/<your-username>/lawmonade.git
git branch -M main
git push -u origin main
```
Or, if you use the GitHub CLI: `gh repo create lawmonade --private --source=. --push`

If you make the repo private, add the judges as collaborators or make it public before 4:00 PM.
**Commit and push often. The deadline is 4:00 PM sharp.**

---

## Rules while coding
- Clio: **GET requests only.** The Clio app has read-only permissions, so a write would fail anyway.
- No Sapini names, ids or amounts in the code. Find the matter with `CLIO_MATTER_QUERY` in `.env`.
- Before every commit, run `git status` and make sure `.env`, `credentials.json`, `token.json` and `data/*.db` are not listed.
