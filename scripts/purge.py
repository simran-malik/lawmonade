"""Retention: delete what Law-monade keeps about one case. Clio is not touched.
Use:  bash run.sh purge --matter 1811193158 [--by "Sam"] [--with-cache]
      bash run.sh purge --matter sample          (reset the demo case: its corrections, approvals, shares)
Removes: saved copies (data/matters/<id>), corrections, approvals, last-opened; turns off the case's share
links and blanks their frozen copies. The audit log keeps a record that this happened (it is append-only).
--with-cache also empties the saved AI answers (data/cache/llm; they are keyed by content, not by case).
"""
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import log, snapshot, store  # noqa: E402
from app.config import settings  # noqa: E402


def arg(name: str, default: str = "") -> str:
    a = sys.argv
    return a[a.index(name) + 1] if name in a and a.index(name) + 1 < len(a) else default


log.setup()
mid = arg("--matter")
if not mid:
    sys.exit('Use: bash run.sh purge --matter <Clio matter id | sample> [--by "Name"] [--with-cache]')
files = snapshot.purge(mid)
rows = store.purge_matter(mid, arg("--by", "run.sh purge"))
print(f"Case {mid}: removed {files} saved copies; {rows}")
if "--with-cache" in sys.argv:
    shutil.rmtree(settings.llm_cache_dir, ignore_errors=True)
    print("Saved AI answers removed.")
