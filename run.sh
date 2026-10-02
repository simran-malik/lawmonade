#!/usr/bin/env bash
# Lawmonade. Use: bash run.sh <command> [flags]        Help: bash run.sh help
# Flags change settings for THIS run only. .env holds the defaults.
set -e
cd "$(dirname "$0")"

help() {
  cat <<'TXT'
Commands
  setup                     install everything (Mac)
  test                      run all tests (no keys needed)
  check [--slack] [--sms +1NUMBER]   check keys, tools and the Clio connection
  clio [--details]          check the Clio connection + Sapini counts (read-only)
  extract <file.pdf> [--ask "question"]   print a PDF's text, optionally ask the AI about it
  ui                        dashboard       http://localhost:8501   (firm only, keep internal)
  provider                  provider portal http://localhost:8502   (the only page providers reach)
  api                       API             http://localhost:8000/docs
  config                    show the settings this run would use (secrets hidden)
  purge --matter ID [--with-cache]   delete what we keep about one case (retention; 'sample' resets the demo)
  digest [--matter ID] [--preview] [--send]   daily digest now: --preview writes logs/digest_preview.html, --send sends
  up                        start API + dashboard + n8n in the background (logs in logs/)
  stop [--docker]           stop everything (add --docker to also quit Docker Desktop)
  status                    show what is running
  gmail                     one-time Google sign-in so Lawmonade can send email
  gcal                      one-time Google sign-in so Lawmonade can add tasks and events to Google Calendar
  templates                 remake the Word templates
  n8n                       start n8n in this terminal

Flags (any command; override .env for this run only)
  --llm anthropic|gemini|mock   which AI to use (mock = saved answers, no key or Wi-Fi)
  --cache on|off|only       saved AI answers: on = reuse + save, off = always ask, only = offline demo
  --model NAME              model for that AI (e.g. gemini-2.5-pro)
  --port N                  port for ui or api
  --ocr-threshold 80        OCR confidence (0-100) below which words count as unclear
  --log-level LEVEL         DEBUG | INFO | WARNING | ERROR (default INFO; logs go to the terminal or logs/)

Ports: API 8000, dashboard 8501, provider portal 8502, n8n 5678. Stop hack/ first: cd ../hack && bash run.sh stop

Examples
  bash run.sh ui --llm gemini
  bash run.sh ui --port 8502
  bash run.sh ui --cache only            (offline demo: only saved AI answers)
  bash run.sh extract data/samples/insurer_letter_nair.pdf --ask "List every date"
TXT
}

setup() {
  if ! command -v brew >/dev/null; then
    echo "Homebrew is missing. Install it from https://brew.sh, then run this again."; exit 1
  fi
  command -v uv >/dev/null        || brew install uv
  command -v tesseract >/dev/null || brew install tesseract
  uv python install 3.11
  uv venv --python 3.11 .venv --allow-existing
  uv sync --all-groups
  [ -f .env ] || cp .env.example .env
  uv run pytest -q
  echo
  echo "Setup done. Optional: source .venv/bin/activate"
  echo "Next: bash run.sh check"
}

die() { echo "Error: $1"; echo "See: bash run.sh help"; exit 1; }

port_busy() { lsof -nP -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1; }

env_val() { grep -E "^$1=" .env 2>/dev/null | head -1 | cut -d= -f2- | tr -d "\"'"; }
# n8n data (account, workflows) lives in the n8n_data volume.
# The Slack webhook is passed in from .env, never saved in the workflow JSON (workflows use $env.SLACK_WEBHOOK_URL).
TZ_FIRM="$(env_val TIMEZONE)"; TZ_FIRM="${TZ_FIRM:-America/Los_Angeles}"
# GENERIC_TIMEZONE: the digest schedule runs on the firm's clock (daylight saving included), not UTC
N8N_RUN="-p 5678:5678 -e N8N_BLOCK_ENV_ACCESS_IN_NODE=false -e SLACK_WEBHOOK_URL=$(env_val SLACK_WEBHOOK_URL) -e DIGEST_API_KEY=$(env_val DIGEST_API_KEY) -e GENERIC_TIMEZONE=$TZ_FIRM -e TZ=$TZ_FIRM -v n8n_data:/home/node/.n8n n8nio/n8n"

up() {
  for p in "${PORT:-8000}" 8501 8502; do
    port_busy "$p" && die "port $p is already in use. Stop hack/ first: (cd ../hack && bash run.sh stop), or: bash run.sh stop"
  done
  mkdir -p logs
  if ! docker info >/dev/null 2>&1; then
    echo "Starting Docker Desktop..."; open -a Docker
    for i in $(seq 1 45); do docker info >/dev/null 2>&1 && break; sleep 2; done
  fi
  docker rm -f n8n >/dev/null 2>&1 || true
  docker run -d --name n8n $N8N_RUN >/dev/null && echo "n8n       -> http://localhost:5678"
  nohup uv run uvicorn app.main:app --port "${PORT:-8000}" > logs/api.log 2>&1 &
  echo "API       -> http://localhost:${PORT:-8000}/docs   (log: logs/api.log)"
  nohup uv run streamlit run ui/dashboard.py --server.port 8501 --server.headless true > logs/ui.log 2>&1 &
  echo "Dashboard -> http://localhost:8501              (log: logs/ui.log)"
  nohup uv run streamlit run ui/provider_app.py --server.port 8502 --server.headless true > logs/provider.log 2>&1 &
  echo "Providers -> http://localhost:8502              (log: logs/provider.log)"
  echo "Give it ~10 s, then: bash run.sh status.   Stop everything: bash run.sh stop"
}

stop() {
  # Stops anything on our ports (also hack/'s screens, since both use the same ports)
  pkill -f "streamlit run ui/" && echo "stopped dashboard + provider portal" || echo "dashboard was not running"
  pkill -f "uvicorn app.main:app" && echo "stopped API" || echo "API was not running"
  ids=$(docker ps -q --filter ancestor=n8nio/n8n 2>/dev/null || true)
  if [ -n "$ids" ]; then docker stop $ids >/dev/null && echo "stopped n8n (your n8n account and workflows are kept)"; else echo "n8n was not running"; fi
  pkill -f "ngrok http" && echo "stopped ngrok" || true
  if [ "${1:-}" = "--docker" ]; then osascript -e 'quit app "Docker"' && echo "quit Docker Desktop"; fi
}

status() {
  for p in 8000:API 8501:dashboard 8502:provider-portal 5678:n8n; do
    port=${p%%:*}; name=${p#*:}
    if port_busy "$port"; then echo "UP    $name  http://localhost:$port"; else echo "down  $name"; fi
  done
  docker info >/dev/null 2>&1 && echo "UP    Docker Desktop" || echo "down  Docker Desktop"
}

cmd="${1:-help}"; [ $# -gt 0 ] && shift
PASS=(); MODEL=""; PORT=""
while [ $# -gt 0 ]; do
  case "$1" in
    --llm)    case "$2" in anthropic|gemini|mock) export LLM_PROVIDER="$2" ;; *) die "--llm must be anthropic, gemini or mock" ;; esac; shift 2 ;;
    --cache)  case "$2" in on|off|only) export LLM_CACHE="$2" ;; *) die "--cache must be on, off or only" ;; esac; shift 2 ;;
    --model)  MODEL="$2"; shift 2 ;;
    --port)   PORT="$2"; shift 2 ;;
    --ocr-threshold) export OCR_MIN_CONF="$2"; shift 2 ;;
    --log-level) case "$2" in DEBUG|INFO|WARNING|ERROR|debug|info|warning|error) export LOG_LEVEL="$2" ;; *) die "--log-level must be DEBUG, INFO, WARNING or ERROR" ;; esac; shift 2 ;;
    *)        PASS+=("$1"); shift ;;
  esac
done
if [ -n "$MODEL" ]; then   # --model goes to whichever AI is in use
  P="${LLM_PROVIDER:-$(grep -E '^LLM_PROVIDER=' .env 2>/dev/null | cut -d= -f2)}"
  if [ "$P" = gemini ]; then export GEMINI_MODEL="$MODEL"; else export ANTHROPIC_MODEL="$MODEL"; fi
fi
[ -n "${LLM_PROVIDER:-}${LLM_CACHE:-}$MODEL" ] && echo "This run: LLM=${LLM_PROVIDER:-from .env} cache=${LLM_CACHE:-from .env} ${MODEL:+model=$MODEL}"

case "$cmd" in
  setup)     setup ;;
  test)      uv run pytest -q ${PASS[@]+"${PASS[@]}"} ;;
  check)     uv run python scripts/check_setup.py ${PASS[@]+"${PASS[@]}"} ;;
  clio)      uv run python scripts/clio_check.py ${PASS[@]+"${PASS[@]}"} ;;
  extract)   uv run python scripts/extract.py ${PASS[@]+"${PASS[@]}"} ;;
  ui)        uv run streamlit run ui/dashboard.py --server.port "${PORT:-8501}" ;;
  provider)  uv run streamlit run ui/provider_app.py --server.port "${PORT:-8502}" ;;
  api)       uv run uvicorn app.main:app --reload --port "${PORT:-8000}" ;;
  config)    uv run python scripts/show_config.py ;;
  purge)     uv run python scripts/purge.py ${PASS[@]+"${PASS[@]}"} ;;
  digest)    uv run python scripts/digest.py ${PASS[@]+"${PASS[@]}"} ;;
  templates) uv run python scripts/make_templates.py ;;
  gmail)     uv run python -m app.emailer ;;
  gcal)      uv run python -m app.gcal ;;
  n8n)       docker rm -f n8n >/dev/null 2>&1 || true; docker run -it --rm --name n8n $N8N_RUN ;;
  up)        up ;;
  stop)      stop ${PASS[@]+"${PASS[@]}"} ;;
  status)    status ;;
  help|*)    help ;;
esac
