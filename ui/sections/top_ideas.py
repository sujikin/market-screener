from __future__ import annotations

import streamlit as st


def _badge_class(action: str) -> str:
    action_upper = action.upper()
    if action_upper in {"OVERSOLD", "CONTRA BUY", "BUY", "BUILD"}:
        return "opportunity"
    if action_upper in {"SELL", "EXIT", "SHORT"}:
        return "risk"
    if action_upper == "MISSING":
        return "accent"
    return "neutral"


def render_top_ideas(ideas: list[dict[str, object]], key_prefix: str) -> str | None:
    if not ideas:
        st.info("No standout ideas in this snapshot.")
        return None

    selected_ticker = None
    cols = st.columns(len(ideas))
    for idx, (col, idea) in enumerate(zip(cols, ideas)):
        badge_class = _badge_class(str(idea.get("action", "")))
        with col:
            st.markdown(
                f"""
                <div class="ims-card ims-card--accent ims-card--idea ims-card--dashboard">
                    <div class="ims-kicker">{idea.get("title", "")}</div>
                    <div class="ims-idea-stock">{idea.get("stock", "")}</div>
                    <div style="margin: 0.22rem 0 0.14rem 0;">
                        <span class="ims-badge ims-badge--{badge_class}">{idea.get("action", "")}</span>
                    </div>
                    <div class="ims-idea-metric">{idea.get("metric", "")}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            ticker = str(idea.get("ticker", "")).strip()
            if ticker and idea.get("action") != "Missing":
                card_label = f"Open {idea.get('stock', ticker)}"
                if st.button(card_label, key=f"{key_prefix}_idea_{idx}_{ticker}", use_container_width=True):
                    selected_ticker = ticker
    return selected_ticker
