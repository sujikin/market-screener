from __future__ import annotations

import streamlit as st


def render_header_guide() -> None:
    with st.popover("Guide", use_container_width=True):
        st.markdown("### Quick Guide")
        st.markdown(
            """
            - Use `Market Monitor` for daily cached snapshots of `Nifty 50` and `Nifty Next 50`.
            - Use `Custom Scan` for live ticker checks that may download fresh chart data.
            - Select a row in the table to update the stock detail panel.
            - `Coverage` tells you how many index members were fully screened in the snapshot.
            """
        )
        st.caption("The long-form project notes remain in `README.md`, but the app no longer replaces the whole page with it.")


def render_learn_section() -> None:
    with st.expander("How To Read This", expanded=False):
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
            - The monitor tab stays cache-only so one page does not silently mix snapshot data with live downloads.
            """
        )
