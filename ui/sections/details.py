from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from services.models import DetailView


def _action_badge_class(action_family: str) -> str:
    if action_family == "opportunity":
        return "opportunity"
    if action_family == "risk":
        return "risk"
    return "neutral"


def _format_stat_value(label: str, value: object) -> str:
    if value is None:
        return "NA"
    if label == "Close":
        return f"{float(value):.2f}"
    if label == "RSI":
        return f"{float(value):.1f}"
    if label == "Volume vs 20D Avg":
        return f"{float(value):.2f}x"
    if label == "1Y Return":
        return f"{float(value):.1f}%"
    return str(value)


def _format_fundamental_value(value: object) -> str:
    if value in (None, "", "NA"):
        return "NA"
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return str(value)
    return f"{numeric:.1f}%"


def _format_fundamental_display(label: str, value: object) -> str:
    if value in (None, "", "NA"):
        return "NA"
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return str(value)
    if label in {"Debt / Equity", "P/E Ratio"}:
        return f"{numeric:.2f}x"
    return f"{numeric:.1f}%"


def render_detail_summary(detail_view: DetailView) -> None:
    st.markdown(
        f"""
        <div class="ims-card ims-card--accent">
            <div class="ims-kicker">Selected Stock</div>
            <div class="ims-detail-title">{detail_view.stock}</div>
            <div class="ims-subtle">{detail_view.ticker}</div>
            <div style="margin: 0.6rem 0;">
                <span class="ims-badge ims-badge--{_action_badge_class(detail_view.action_family)}">{detail_view.action}</span>
            </div>
            <div class="ims-detail-copy">{detail_view.explanation}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if detail_view.factor_chips:
        chips_html = "".join(f'<span class="ims-chip">{chip}</span>' for chip in detail_view.factor_chips)
        st.markdown(f'<div class="ims-chip-row">{chips_html}</div>', unsafe_allow_html=True)

    stats = list(detail_view.stats.items())
    st.markdown("#### Technical Snapshot")
    stat_cols = st.columns(3)
    for idx, (label, value) in enumerate(stats):
        with stat_cols[idx % 3]:
            st.markdown(
                f"""
                <div class="ims-card ims-card--compact">
                    <div class="ims-kicker">{label}</div>
                    <div class="ims-stat-value">{_format_stat_value(label, value)}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    st.markdown("#### Fundamental Snapshot")
    if detail_view.fundamental_status:
        st.caption(detail_view.fundamental_status)

    fundamentals = list(detail_view.fundamental_stats.items())
    fundamental_cols = st.columns(3)
    for idx, (label, value) in enumerate(fundamentals):
        with fundamental_cols[idx % 3]:
            st.markdown(
                f"""
                    <div class="ims-card ims-card--compact">
                        <div class="ims-kicker">{label}</div>
                        <div class="ims-stat-value">{_format_fundamental_display(label, value)}</div>
                    </div>
                """,
                unsafe_allow_html=True,
            )


def _trim_history(hist: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    if hist.empty:
        return hist
    periods = {"3M": 63, "6M": 126, "1Y": 252}
    return hist.tail(periods.get(timeframe, 252)).copy()


def render_detail_chart(
    hist: pd.DataFrame,
    detail_view: DetailView,
    *,
    timeframe: str,
    show_mas: bool,
    key_prefix: str,
) -> None:
    if hist.empty:
        st.info("No chart data available for this selection.")
        return

    plot_df = hist.copy().sort_index()
    plot_df["Close"] = pd.to_numeric(plot_df["Close"], errors="coerce")
    plot_df = plot_df.dropna(subset=["Close"])
    if plot_df.empty:
        st.info("No chart data available for this selection.")
        return

    indicator_series = (
        pd.to_numeric(plot_df["Adj_Close"], errors="coerce")
        if "Adj_Close" in plot_df.columns
        else plot_df["Close"]
    )
    plot_df["DMA50"] = indicator_series.rolling(min(50, len(plot_df))).mean()
    plot_df["DMA200"] = indicator_series.rolling(min(200, len(plot_df))).mean()
    plot_df = _trim_history(plot_df, timeframe)

    has_ohlc = all(col in plot_df.columns for col in ["Open", "High", "Low", "Close"])
    fig = go.Figure()

    if has_ohlc:
        fig.add_trace(
            go.Candlestick(
                x=plot_df.index,
                open=plot_df["Open"],
                high=plot_df["High"],
                low=plot_df["Low"],
                close=plot_df["Close"],
                name=detail_view.ticker,
            )
        )
    else:
        fig.add_trace(
            go.Scatter(
                x=plot_df.index,
                y=plot_df["Close"],
                mode="lines",
                name=detail_view.ticker,
                line={"color": "#1d4ed8", "width": 2.4},
            )
        )

    if show_mas:
        fig.add_trace(
            go.Scatter(
                x=plot_df.index,
                y=plot_df["DMA50"],
                mode="lines",
                name="50DMA",
                line={"color": "#d97706", "width": 1.5},
            )
        )
        if plot_df["DMA200"].notna().any():
            fig.add_trace(
                go.Scatter(
                    x=plot_df.index,
                    y=plot_df["DMA200"],
                    mode="lines",
                    name="200DMA",
                    line={"color": "#475569", "width": 1.5},
                )
            )

    fig.update_layout(
        title=f"{detail_view.ticker} | {timeframe} view",
        template="plotly_white",
        height=430,
        margin={"l": 16, "r": 16, "t": 56, "b": 16},
        hovermode="x unified",
        xaxis_title="Date",
        yaxis_title="Price (INR)",
        showlegend=show_mas,
    )
    st.plotly_chart(fig, use_container_width=True, key=f"{key_prefix}_chart")
