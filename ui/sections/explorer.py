from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pandas as pd
import streamlit as st

SELECT_COLUMN = "Select"


def normalize_selected_ticker(display_df: pd.DataFrame, selected_ticker: str | None) -> str | None:
    if display_df.empty or "Ticker" not in display_df.columns:
        return None

    tickers = display_df["Ticker"].astype(str).tolist()
    if not tickers:
        return None
    if selected_ticker in tickers:
        return selected_ticker
    return tickers[0]


def build_explorer_editor_df(display_df: pd.DataFrame, selected_ticker: str | None) -> pd.DataFrame:
    editor_df = display_df.copy()
    if SELECT_COLUMN in editor_df.columns:
        editor_df = editor_df.drop(columns=[SELECT_COLUMN])

    normalized_ticker = normalize_selected_ticker(editor_df, selected_ticker)
    if normalized_ticker is None:
        editor_df.insert(0, SELECT_COLUMN, False)
        return editor_df

    editor_df.insert(0, SELECT_COLUMN, editor_df["Ticker"].astype(str) == normalized_ticker)
    return editor_df


def resolve_selected_ticker(
    edited_df: pd.DataFrame,
    previous_selected_ticker: str | None,
    editor_state: Mapping[str, Any] | None = None,
) -> str | None:
    normalized_previous = normalize_selected_ticker(edited_df, previous_selected_ticker)
    if edited_df.empty or "Ticker" not in edited_df.columns or SELECT_COLUMN not in edited_df.columns:
        return normalized_previous

    edited_rows = editor_state.get("edited_rows") if editor_state is not None else None
    if isinstance(edited_rows, dict):
        true_edits: list[int] = []
        for row_idx, row_edits in edited_rows.items():
            if not isinstance(row_edits, dict):
                continue
            if row_edits.get(SELECT_COLUMN):
                try:
                    true_edits.append(int(row_idx))
                except (TypeError, ValueError):
                    continue
        if true_edits:
            chosen_index = true_edits[-1]
            if 0 <= chosen_index < len(edited_df):
                return str(edited_df.iloc[chosen_index]["Ticker"])

    selected_rows = edited_df[edited_df[SELECT_COLUMN].fillna(False).astype(bool)]
    if selected_rows.empty:
        return normalized_previous
    if len(selected_rows) == 1:
        return str(selected_rows.iloc[0]["Ticker"])

    selected_tickers = selected_rows["Ticker"].astype(str).tolist()
    if normalized_previous in selected_tickers:
        return normalized_previous
    return selected_tickers[0]


def selection_needs_normalization(edited_df: pd.DataFrame, selected_ticker: str | None) -> bool:
    if edited_df.empty or SELECT_COLUMN not in edited_df.columns or "Ticker" not in edited_df.columns:
        return False

    selected_rows = edited_df[edited_df[SELECT_COLUMN].fillna(False).astype(bool)]
    if len(selected_rows) != 1:
        return True
    return str(selected_rows.iloc[0]["Ticker"]) != str(selected_ticker)


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
    editor_df = build_explorer_editor_df(display_df, selected_ticker)
    column_order = [SELECT_COLUMN] + [column for column in column_order if column in editor_df.columns]
    disabled_columns = [column for column in editor_df.columns if column != SELECT_COLUMN]

    edited_df = st.data_editor(
        editor_df,
        width="stretch",
        height=height,
        hide_index=True,
        key=key,
        disabled=disabled_columns,
        column_config={
            SELECT_COLUMN: st.column_config.CheckboxColumn("Pick", width="small"),
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
    resolved_ticker = resolve_selected_ticker(edited_df, selected_ticker, st.session_state.get(key))
    return edited_df, resolved_ticker
