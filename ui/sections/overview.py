from __future__ import annotations

import streamlit as st


def render_overview_cards(cards: list[dict[str, object]]) -> None:
    if not cards:
        return

    cols = st.columns(len(cards))
    for col, card in zip(cols, cards):
        tone = str(card.get("tone", "neutral"))
        with col:
            st.markdown(
                f"""
                <div class="ims-card ims-card--dashboard ims-card--{tone}">
                    <div class="ims-kicker">{card.get("title", "")}</div>
                    <div class="ims-value">{card.get("value", "")}</div>
                    <div class="ims-subtle">{card.get("caption", "")}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
