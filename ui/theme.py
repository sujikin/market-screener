from __future__ import annotations

from pathlib import Path

import streamlit as st


def inject_theme() -> None:
    css_path = Path(__file__).resolve().parent.parent / "assets" / "theme.css"
    if not css_path.exists():
        return
    st.markdown(f"<style>{css_path.read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)

