"""Print the settings this run will use (.env + flags). Secrets are hidden."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.config import settings  # noqa: E402

SECRET = ("key", "token", "secret", "sid", "webhook")
for k, v in settings.model_dump().items():
    if any(s in k for s in SECRET) and v:
        v = str(v)[:4] + "..." + f"({len(str(v))} chars)"
    print(f"{k:22} {v}")
