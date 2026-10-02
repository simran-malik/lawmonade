"""Print the text of one PDF, page by page. Optional: ask the AI a question about it.
Use: bash run.sh extract <file.pdf> [--ask "What injuries are listed?"] [--llm gemini]
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings  # noqa: E402
from app.pdf import read_pdf  # noqa: E402

args = sys.argv[1:]
question = ""
if "--ask" in args:
    i = args.index("--ask")
    question = args[i + 1] if i + 1 < len(args) else ""
    args = args[:i] + args[i + 2:]
files = [a for a in args if not a.startswith("--")]
if not files:
    sys.exit('Use: bash run.sh extract <file.pdf> [--ask "question"]')

pages = read_pdf(files[0])
for p in pages:
    print(f"\n===== Page {p['page']}" + (" (scanned: needs OCR)" if p["scanned"] else ""))
    print(p["text"][:3000])
print(f"\n{len(pages)} pages, {sum(p['scanned'] for p in pages)} scanned")

if question:
    from app.llm import ask
    print(f"\nLLM={settings.llm_provider}  question: {question}\n")
    print(ask(question, "\n\n".join(f"[Page {p['page']}]\n{p['text']}" for p in pages)))
