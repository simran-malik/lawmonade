"""Starter screen. Lawmonade dashboard. Run: bash run.sh ui  ->  http://localhost:8501"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st

from app.config import settings
from app.pdf import read_pdf

st.set_page_config(page_title="Lawmonade", layout="wide")
st.title("Lawmonade (starter screen)")

samples = sorted((settings.data_dir / "samples").glob("*.pdf"))
up = st.file_uploader("Drop a PDF", type="pdf")
pick = st.selectbox("...or a sample", ["(none)"] + [p.name for p in samples])

path = None
if up:
    path = Path(tempfile.mkdtemp()) / up.name
    path.write_bytes(up.getvalue())
elif pick != "(none)":
    path = settings.data_dir / "samples" / pick

if path:
    pages = read_pdf(path)
    for p in pages:
        with st.expander(f"Page {p['page']}" + (" (scanned)" if p["scanned"] else "")):
            st.text(p["text"] or "(no text: needs OCR)")

    prompt = st.text_area("Ask Claude about this PDF", "List every date in this document.")
    if st.button("Ask", type="primary"):
        from app.llm import ask
        with st.spinner("Thinking..."):
            text = "\n\n".join(f"[Page {p['page']}]\n{p['text']}" for p in pages)
            st.markdown(ask(prompt, text))
