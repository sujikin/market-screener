from __future__ import annotations

import streamlit as st


def render_header_guide() -> None:
    with st.popover("Guide", width="stretch"):
        st.markdown("### Quick Guide")
        st.markdown(
            """
            - Use `Market Monitor` for daily cached snapshots of `Nifty 50` and `Nifty Next 50`.
            - Use `Custom Scan` for ad hoc ticker checks that may fetch live chart or fundamentals data.
            - Use `Columns` when you want extra fields beyond the core explorer view.
            - The selected row in the explorer drives the stock detail section below.
            - `Coverage` tells you how many index members were fully screened in the snapshot.
            """
        )


def render_learn_section() -> None:
    with st.expander("How To Read This", expanded=False):
        st.markdown("#### Using the workspace")
        st.markdown(
            """
            - `Market Monitor` is snapshot-only, so the table and chart stay aligned to the cached daily files.
            - `Custom Scan` is more flexible and may fall back to live downloads when local cache data is unavailable.
            - The explorer starts with core columns only. Use `Columns` to reveal optional metrics when needed.
            - Selecting a row updates the detail section for that stock.
            """
        )

        st.markdown("#### Action meanings")
        st.markdown(
            """
            - `OVERSOLD` and `CONTRA BUY` mean weakness is still visible, but momentum is improving.
            - `BUY` and `BUILD` mean the trend is more constructive.
            - `SELL`, `EXIT`, and `SHORT` mean momentum is weakening or already weak.
            - `HOLD` means the engine does not see a strong technical edge today.
            """
        )

        st.markdown("#### Why stocks can be missing")
        st.markdown(
            """
            - Newer index entrants may not have enough history for the full signal set.
            - Cached chart data may be missing for some names in older snapshots.
            - A stock can also fail screening even when history exists.
            """
        )

        st.markdown("#### Freshness and trust")
        st.markdown(
            """
            - `Market Data` is the last trading date in the cached history.
            - `Generated` is when this local snapshot file was produced.
            """
        )

        st.markdown("#### Fundamentals and price range")
        st.markdown(
            """
            - The fundamentals source line above the card rail tells you where the numbers came from and the latest statement date when available.
            - `52W High` and `52W Low` in `Technical Snapshot` are derived from the loaded price history.
            - `ROE` uses net income over average equity.
            - `ROCE` uses EBIT over average capital employed.
            - `P/E Ratio` uses trailing PE when available, otherwise forward PE.
            """
        )
