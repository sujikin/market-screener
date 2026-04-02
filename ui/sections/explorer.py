from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pandas as pd
import streamlit as st


def normalize_selected_ticker(display_df: pd.DataFrame, selected_ticker: str | None) -> str | None:
    if display_df.empty or "Ticker" not in display_df.columns:
        return None

    tickers = display_df["Ticker"].astype(str).tolist()
    if not tickers:
        return None
    if selected_ticker in tickers:
        return selected_ticker
    return tickers[0]


def build_dataframe_selection_state(
    display_df: pd.DataFrame,
    selected_ticker: str | None,
) -> dict[str, object]:
    normalized_ticker = normalize_selected_ticker(display_df, selected_ticker)
    rows: list[int] = []
    if normalized_ticker is not None and "Ticker" in display_df.columns:
        tickers = display_df["Ticker"].astype(str).tolist()
        if normalized_ticker in tickers:
            rows = [tickers.index(normalized_ticker)]

    return {
        "selection": {
            "rows": rows,
            "columns": [],
            "cells": [],
        }
    }


def _extract_selected_rows(selection_state: object | None) -> list[int]:
    if selection_state is None:
        return []

    selection: object | None = None
    if hasattr(selection_state, "selection"):
        selection = getattr(selection_state, "selection")
    elif isinstance(selection_state, Mapping):
        selection = selection_state.get("selection")

    if selection is None:
        return []

    if hasattr(selection, "rows"):
        rows = getattr(selection, "rows")
    elif isinstance(selection, Mapping):
        rows = selection.get("rows")
    else:
        rows = None

    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, int)]


def sync_dataframe_selection_state(
    display_df: pd.DataFrame,
    *,
    key: str,
    selected_ticker: str | None,
) -> dict[str, object]:
    desired_state = build_dataframe_selection_state(display_df, selected_ticker)
    desired_rows = _extract_selected_rows(desired_state)
    current_rows = _extract_selected_rows(st.session_state.get(key))
    if current_rows != desired_rows:
        st.session_state[key] = desired_state
    return desired_state


def resolve_selected_ticker(
    display_df: pd.DataFrame,
    selection_state: object | None,
    fallback_ticker: str | None,
) -> str | None:
    normalized_fallback = normalize_selected_ticker(display_df, fallback_ticker)
    rows = _extract_selected_rows(selection_state)
    if not rows:
        return normalized_fallback

    selected_index = rows[0]
    if 0 <= selected_index < len(display_df):
        return str(display_df.iloc[selected_index]["Ticker"])
    return normalized_fallback


def render_explorer_table(
    display_df,
    *,
    key: str,
    selected_ticker: str | None = None,
    height: int = 360,
    column_order: list[str] | None = None,
):
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

    selection_default = sync_dataframe_selection_state(
        display_df,
        key=key,
        selected_ticker=selected_ticker,
    )
    column_order = [column for column in column_order if column in display_df.columns]

    return st.dataframe(
        display_df,
        width="stretch",
        height=height,
        hide_index=True,
        key=key,
        on_select="rerun",
        selection_mode="single-row-required",
        selection_default=selection_default,
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
