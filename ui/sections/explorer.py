from __future__ import annotations

import streamlit as st


def render_explorer_table(display_df, *, key: str, height: int = 360, column_order: list[str] | None = None):
    if column_order is None:
        column_order = [
            "Stock",
            "Ticker",
            "Action",
            "Priority",
            "RSI",
            "Vol_Spike",
            "1Y_Return_%",
            "Close",
            "History_Days",
        ]
    column_order = [column for column in column_order if column in display_df.columns]

    return st.dataframe(
        display_df,
        width="stretch",
        height=height,
        hide_index=True,
        key=key,
        on_select="rerun",
        selection_mode="single-row",
        column_config={
            "Stock": st.column_config.TextColumn("Stock", width="large"),
            "Ticker": st.column_config.TextColumn("Ticker", width="medium"),
            "Action": st.column_config.TextColumn("Action", width="small"),
            "Priority": st.column_config.NumberColumn("Priority", format="%d", width="small"),
            "RSI": st.column_config.NumberColumn("RSI", format="%.1f", width="small"),
            "Vol_Spike": st.column_config.NumberColumn("Volume vs 20D Avg", format="%.2f x", width="small"),
            "1Y_Return_%": st.column_config.NumberColumn("1Y Return", format="%.1f%%", width="small"),
            "Close": st.column_config.NumberColumn("Close", format="%.2f", width="small"),
            "History_Days": st.column_config.NumberColumn("History Days", format="%d", width="small"),
        },
        column_order=column_order,
    )
