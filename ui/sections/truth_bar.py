from __future__ import annotations

import streamlit as st

from services.models import UniverseSnapshot
from services.presentation import build_missing_constituents_df, build_truth_bar_data


def _render_metric_card(label: str, value: str, accent: str = "neutral") -> None:
    st.markdown(
        f"""
        <div class="ims-card ims-card--compact ims-card--{accent}">
            <div class="ims-kicker">{label}</div>
            <div class="ims-value">{value}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_truth_bar(snapshot: UniverseSnapshot) -> None:
    truth_data = build_truth_bar_data(snapshot)
    cols = st.columns([1.3, 1, 1, 1, 1])
    with cols[0]:
        _render_metric_card("Universe", str(truth_data["universe_label"]), "accent")
    with cols[1]:
        _render_metric_card("Mode", str(truth_data["mode_label"]))
    with cols[2]:
        _render_metric_card("Market Data", str(truth_data["market_data_label"]))
    with cols[3]:
        _render_metric_card("Generated", str(truth_data["generated_at_label"]))
    with cols[4]:
        _render_metric_card("Coverage", str(truth_data["coverage_label"]))

    if truth_data["is_stale"]:
        st.warning(
            f"Snapshot data is stale. Latest market data date is {truth_data['market_data_label']}."
        )

    if snapshot.action_counts:
        action_summary = " | ".join(
            f"{action}: {count}" for action, count in sorted(snapshot.action_counts.items())
        )
        st.caption(f"Action mix: {action_summary}")

    if truth_data["missing_count"] > 0:
        missing_df = build_missing_constituents_df(snapshot)
        with st.expander(f"Missing constituents ({truth_data['missing_count']})", expanded=False):
            st.dataframe(missing_df, width="stretch", hide_index=True)

