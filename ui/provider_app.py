"""Provider portal: the ONLY app providers can reach. Run: bash run.sh provider  ->  http://localhost:8502

It shows the approved, frozen share for ?share=<token> and nothing else: no case search, no Clio token use,
no firm dashboard. Put only THIS port online (PUBLIC_URL); keep the firm dashboard (8501) internal.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st  # noqa: E402

from app import log  # noqa: E402
from ui import provider_view, theme  # noqa: E402

log.setup()
theme.apply()
token = st.query_params.get("share")
if token:
    provider_view.page(token)
else:
    theme.empty_state("Nothing to show here", "Open the secure link the law firm sent you by email.")
