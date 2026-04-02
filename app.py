import os
from datetime import datetime

import pandas as pd
import streamlit as st
import yfinance as yf

from screener import load_price_df_from_cache, run_screener
from services.fundamentals_cache import get_fundamentals_payload_for_ticker, load_fundamentals_cache
from services.detail_analysis import build_detail_view
from services.fundamentals_provider import fetch_experimental_fundamentals
from services.models import UniverseSnapshot
from services.presentation import (
    apply_explorer_filters,
    build_explorer_df,
    build_overview_cards,
    build_top_ideas,
)
from services.scan_repository import load_grouped_cache, load_index_snapshot
from ui.sections.details import render_detail_chart, render_detail_summary
from ui.sections.explorer import normalize_selected_ticker, render_explorer_table, resolve_selected_ticker
from ui.sections.learn import render_header_guide, render_learn_section
from ui.sections.overview import render_overview_cards
from ui.sections.top_ideas import render_top_ideas
from ui.sections.truth_bar import render_truth_bar
from ui.theme import inject_theme


st.set_page_config(page_title="Indian Market Screener", layout="wide")
inject_theme()

DEFAULT_MONITOR_COLUMNS = ["Stock", "Ticker", "Action", "RSI", "Vol_Spike", "1Y_Return_%"]
MONITOR_OPTIONAL_COLUMNS = ["Priority", "Close", "History_Days"]
DEFAULT_CUSTOM_COLUMNS = ["Stock", "Ticker", "Action", "RSI", "Vol_Spike", "1Y_Return_%"]
CUSTOM_OPTIONAL_COLUMNS = ["Priority", "Close"]


if "selected_universe_key" not in st.session_state:
    st.session_state.selected_universe_key = "nifty50"

if "monitor_selected_ticker" not in st.session_state:
    st.session_state.monitor_selected_ticker = None

if "custom_tickers" not in st.session_state:
    st.session_state.custom_tickers = ""

if "custom_df" not in st.session_state:
    st.session_state.custom_df = None

if "custom_run_at" not in st.session_state:
    st.session_state.custom_run_at = None

if "custom_selected_ticker" not in st.session_state:
    st.session_state.custom_selected_ticker = None


@st.cache_data(show_spinner=False)
def fetch_chart_data_with_source(ticker, universe, cache_version):
    _ = cache_version
    cached_data = load_price_df_from_cache(ticker, universe)
    if cached_data is not None and not cached_data.empty:
        return cached_data, "Local Cache"

    live_df = yf.download(ticker, period="1y", interval="1d", progress=False)
    return live_df, "Live Download"


@st.cache_data(show_spinner=False)
def fetch_chart_data(ticker, universe, cache_version):
    hist, _ = fetch_chart_data_with_source(ticker, universe, cache_version)
    return hist


@st.cache_data(show_spinner=False, ttl=21600)
def load_experimental_fundamentals(ticker):
    return fetch_experimental_fundamentals(ticker)


@st.cache_data(show_spinner=False)
def load_cached_fundamentals(universe_key, fundamentals_version):
    _ = fundamentals_version
    return load_fundamentals_cache(universe_key)


def get_cache_version(universe):
    cache_file = f"price_cache_{universe}.csv"
    try:
        return os.path.getmtime(cache_file)
    except OSError:
        return 0


def get_file_version(filename):
    try:
        return os.path.getmtime(filename)
    except OSError:
        return 0


@st.cache_data(show_spinner=False)
def load_snapshot(universe_key, scan_version, cache_version, meta_version):
    _ = (scan_version, cache_version, meta_version)
    return load_index_snapshot(universe_key)


@st.cache_data(show_spinner=False)
def load_cached_chart_data(universe_key, cache_version):
    _ = cache_version
    return load_grouped_cache(universe_key)


def clear_custom_results():
    st.session_state.custom_df = None
    st.session_state.custom_run_at = None
    st.session_state.custom_selected_ticker = None


def build_history_days_lookup(grouped_cache):
    return {str(ticker).upper(): int(len(hist)) for ticker, hist in grouped_cache.items()}


def build_custom_explorer_df(df):
    custom_df = df.copy()
    custom_df["Priority"] = pd.to_numeric(custom_df.get("Rank"), errors="coerce").fillna(99)
    custom_df["RSI"] = pd.to_numeric(custom_df.get("RSI"), errors="coerce")
    custom_df["Vol_Spike"] = pd.to_numeric(custom_df.get("Vol_Spike"), errors="coerce")
    custom_df["1Y_Return_%"] = pd.to_numeric(custom_df.get("1Y_Return_%"), errors="coerce")
    custom_df["History_Days"] = 0
    custom_df["Limited_History"] = False
    return custom_df.sort_values(["Priority", "RSI", "Stock"], na_position="last").reset_index(drop=True)


def sync_selected_ticker(df, state_key):
    selected_ticker = normalize_selected_ticker(df, st.session_state.get(state_key))
    st.session_state[state_key] = selected_ticker
    return selected_ticker


def selected_row_from_state(df, state_key):
    selected_ticker = sync_selected_ticker(df, state_key)
    if selected_ticker is None:
        return None

    selected_rows = df[df["Ticker"] == selected_ticker]
    return None if selected_rows.empty else selected_rows.iloc[0]


def render_hero_panel(title, copy):
    st.markdown(
        f"""
        <div class="ims-hero">
            <div class="ims-kicker">Product View</div>
            <div class="ims-hero-title">{title}</div>
            <div class="ims-hero-copy">{copy}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_page_header():
    st.markdown(
        """
        <div class="ims-page-header">
            <div class="ims-page-title">Indian Market Screener</div>
            <div class="ims-page-copy">
                Daily technical monitor for major Indian index names, plus an advanced custom scan tab.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_empty_state(title, copy):
    st.markdown(
        f"""
        <div class="ims-empty">
            <div class="ims-empty-title">{title}</div>
            <div class="ims-empty-copy">{copy}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def reset_monitor_filters(universe_key):
    default_keys = {
        f"{universe_key}_search_text": "",
        f"{universe_key}_family_filter": "All",
        f"{universe_key}_actions_filter": [],
        f"{universe_key}_rsi_filter": "Any",
        f"{universe_key}_volume_only": False,
        f"{universe_key}_positive_return_only": False,
        f"{universe_key}_limited_history_only": False,
        f"{universe_key}_visible_columns": DEFAULT_MONITOR_COLUMNS.copy(),
    }
    for key, value in default_keys.items():
        st.session_state[key] = value


def reset_custom_search():
    st.session_state["custom_search_text"] = ""
    st.session_state["custom_visible_columns"] = DEFAULT_CUSTOM_COLUMNS.copy()


def render_column_selector(
    *,
    key: str,
    default_columns: list[str],
    optional_columns: list[str],
) -> list[str]:
    available_columns = default_columns + optional_columns
    widget_key = f"{key}__widget"
    reset_notice_key = f"{key}__reset_notice"
    if key not in st.session_state:
        st.session_state[key] = default_columns.copy()
    else:
        st.session_state[key] = [column for column in available_columns if column in st.session_state[key]]

    persisted_columns = st.session_state[key].copy()
    widget_columns = [column for column in available_columns if column in st.session_state.get(widget_key, [])]
    if widget_key not in st.session_state or widget_columns != persisted_columns:
        st.session_state[widget_key] = persisted_columns.copy()

    def sync_visible_columns() -> None:
        selected_columns = [column for column in available_columns if column in st.session_state.get(widget_key, [])]
        if not selected_columns:
            selected_columns = default_columns.copy()
            st.session_state[reset_notice_key] = True
        st.session_state[widget_key] = selected_columns
        st.session_state[key] = selected_columns

    with st.popover("Columns", width="content"):
        st.multiselect(
            "Visible columns",
            options=available_columns,
            key=widget_key,
            on_change=sync_visible_columns,
        )
        if st.session_state.pop(reset_notice_key, False):
            st.info("At least one column is required. Reverting to the default set.")

        st.caption("Core fields stay visible by default. Add optional metrics only when you need them.")

    return [column for column in available_columns if column in st.session_state[key]]


def render_monitor_filters(explorer_df: pd.DataFrame, universe_key: str) -> pd.DataFrame:
    st.markdown("### Signal Explorer")
    cols = st.columns([1.35, 1.0, 1.25, 1.0, 0.8, 0.8, 0.95])
    search_text = cols[0].text_input(
        "Search",
        placeholder="Find stock or ticker",
        key=f"{universe_key}_search_text",
    )
    family_filter = cols[1].selectbox(
        "View",
        options=["All", "Opportunities", "Risk", "Neutral"],
        key=f"{universe_key}_family_filter",
    )
    action_filters = cols[2].multiselect(
        "Actions",
        options=sorted(explorer_df["Action"].astype(str).unique().tolist()),
        key=f"{universe_key}_actions_filter",
    )
    rsi_zone = cols[3].selectbox(
        "RSI Zone",
        options=["Any", "Below 30", "30-40", "40-60", "Above 60"],
        key=f"{universe_key}_rsi_filter",
    )
    volume_spike_only = cols[4].checkbox("High volume", key=f"{universe_key}_volume_only")
    positive_return_only = cols[5].checkbox("Positive 1Y", key=f"{universe_key}_positive_return_only")
    limited_history_only = cols[6].checkbox("Limited history", key=f"{universe_key}_limited_history_only")

    filtered_df = apply_explorer_filters(
        explorer_df,
        search_text=search_text,
        family_filter=family_filter,
        action_filters=action_filters,
        rsi_zone=rsi_zone,
        volume_spike_only=volume_spike_only,
        positive_return_only=positive_return_only,
        limited_history_only=limited_history_only,
    )
    st.caption(f"Showing {len(filtered_df)} of {len(explorer_df)} screened names.")
    return filtered_df


def render_monitor_dashboard(
    snapshot: UniverseSnapshot,
    selected_universe: str,
    cache_version: float,
    fundamentals_cache: dict[str, object],
) -> None:
    grouped_cache = load_cached_chart_data(selected_universe, cache_version)
    history_days_by_ticker = build_history_days_lookup(grouped_cache)
    explorer_df = build_explorer_df(snapshot, history_days_by_ticker)

    render_truth_bar(snapshot)
    st.caption(
        "The monitor tab uses local snapshot files only. Charts do not silently fall back to live downloads."
    )

    st.markdown("### Market Pulse")
    render_overview_cards(build_overview_cards(snapshot))

    st.markdown("### Standout Setups")
    idea_ticker = render_top_ideas(build_top_ideas(snapshot), "monitor")
    if idea_ticker:
        st.session_state.monitor_selected_ticker = idea_ticker
        st.rerun()

    filtered_df = render_monitor_filters(explorer_df, selected_universe)
    if filtered_df.empty:
        render_empty_state(
            "No stocks match the current filters.",
            "Try clearing the action or RSI filters, or switch back to `All` view to restore the full snapshot.",
        )
        if st.button("Clear monitor filters", key=f"{selected_universe}_clear_filters"):
            reset_monitor_filters(selected_universe)
            st.rerun()
        render_learn_section()
        return

    controls_left, controls_right = st.columns([0.82, 0.18])
    with controls_left:
        st.caption("The explorer keeps only the core fields visible by default. Add optional metrics from `Columns` when needed.")
    with controls_right:
        visible_columns = render_column_selector(
            key=f"{selected_universe}_visible_columns",
            default_columns=DEFAULT_MONITOR_COLUMNS,
            optional_columns=MONITOR_OPTIONAL_COLUMNS,
        )

    current_selected_ticker = sync_selected_ticker(filtered_df, "monitor_selected_ticker")
    selection_event = render_explorer_table(
        filtered_df,
        key=f"monitor_table_{selected_universe}",
        selected_ticker=current_selected_ticker,
        height=340,
        column_order=visible_columns,
    )
    st.session_state.monitor_selected_ticker = resolve_selected_ticker(
        filtered_df,
        selection_event,
        current_selected_ticker,
    )
    st.caption("Select a row in the table to update the stock detail below. One row always stays selected.")

    selected_row = selected_row_from_state(filtered_df, "monitor_selected_ticker")
    if selected_row is None:
        st.warning("No stock is available to inspect.")
        render_learn_section()
        return

    selected_ticker = str(selected_row["Ticker"])
    hist = grouped_cache.get(selected_ticker)
    fundamentals = get_fundamentals_payload_for_ticker(fundamentals_cache, selected_ticker)
    detail_view = build_detail_view(
        selected_row,
        hist,
        chart_source="Cached Snapshot",
        fundamental_payload=fundamentals,
    )

    st.markdown("### Stock Detail")
    st.caption("The detail section follows the selected row and uses the same snapshot date as the table.")
    render_detail_summary(detail_view)
    control_cols = st.columns([1.6, 0.8], gap="large")
    timeframe = control_cols[0].radio(
        "Timeframe",
        options=["3M", "6M", "1Y"],
        index=2,
        horizontal=True,
        key=f"monitor_timeframe_{selected_universe}",
    )
    show_mas = control_cols[1].checkbox(
        "Show moving averages",
        value=True,
        key=f"monitor_show_mas_{selected_universe}",
    )
    render_detail_chart(
        detail_view.chart_df,
        detail_view,
        timeframe=timeframe,
        show_mas=show_mas,
        key_prefix=f"monitor_{selected_ticker}",
    )

    render_learn_section()


def render_monitor_tab():
    universe_options = ["nifty50", "niftynext50"]
    top_left, top_right = st.columns([1.45, 0.95], gap="large")
    with top_left:
        render_hero_panel(
            "Market Monitor",
            "Use the snapshot workspace to inspect cached Nifty 50 and Nifty Next 50 signals without mixing in live chart fallbacks.",
        )
    with top_right:
        st.markdown(
            """
            <div class="ims-control-stack">
                <div class="ims-kicker">Universe</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        universe_options = ["nifty50", "niftynext50"]
        current_index = universe_options.index(st.session_state.selected_universe_key)
        selected_universe = st.radio(
            "Universe",
            options=universe_options,
            index=current_index,
            horizontal=True,
            format_func=lambda key: "Nifty 50" if key == "nifty50" else "Nifty Next 50",
            label_visibility="collapsed",
            key="monitor_universe_selector",
        )
        st.caption("Switch between the two local index snapshots.")

    if selected_universe != st.session_state.selected_universe_key:
        st.session_state.monitor_selected_ticker = None
    st.session_state.selected_universe_key = selected_universe

    scan_version = get_file_version(f"latest_scan_{selected_universe}.csv")
    cache_version = get_cache_version(selected_universe)
    meta_version = get_file_version(f"snapshot_meta_{selected_universe}.json")
    fundamentals_version = get_file_version(f"fundamentals_cache_{selected_universe}.json")

    try:
        snapshot = load_snapshot(selected_universe, scan_version, cache_version, meta_version)
    except Exception as exc:
        st.error(f"Unable to load {selected_universe} snapshot: {exc}")
        return

    if snapshot.screened_df.empty:
        render_empty_state(
            "This snapshot is empty.",
            "The local scan file loaded, but it did not contain any screened names. Check the nightly output before relying on this universe.",
        )
        return

    fundamentals_cache = load_cached_fundamentals(selected_universe, fundamentals_version)
    render_monitor_dashboard(snapshot, selected_universe, cache_version, fundamentals_cache)


def render_custom_tab():
    top_left, top_right = st.columns([1.45, 0.95], gap="large")
    with top_left:
        render_hero_panel(
            "Custom Scan",
            "Live ticker checks for names outside the daily snapshot, using the same explorer-detail workflow after the scan completes.",
        )
    with top_right:
        st.markdown(
            """
            <div class="ims-card ims-card--compact ims-card--accent">
                <div class="ims-kicker">Mode</div>
                <div class="ims-stat-value">Live Input</div>
                <div class="ims-subtle">This tab may download fresh chart data when cache data is unavailable.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    custom_tickers = st.text_area(
        "Custom Tickers",
        value=st.session_state.custom_tickers,
        height=100,
        placeholder="Enter ticker symbols (one per line or comma-separated).\nExample: RELIANCE.NS\nTCS.NS\nINFY.NS",
        help="Enter NSE or BSE ticker symbols",
        key="custom_ticker_input",
    )
    st.session_state.custom_tickers = custom_tickers

    if st.button("Run Screener", key="custom_run_btn", type="primary"):
        if not custom_tickers.strip():
            clear_custom_results()
            st.error("Please enter at least one ticker symbol.")
        else:
            with st.spinner("Running screener..."):
                try:
                    tickers_input = custom_tickers.replace("\n", ",")
                    df_result = run_screener(
                        strategy="contra",
                        universe="custom",
                        custom_tickers=tickers_input,
                        max_workers=10,
                        batch_size=10,
                        use_cache=False,
                    )
                    if df_result.empty:
                        clear_custom_results()
                        st.error("No results found. Please check your ticker symbols and try again.")
                    else:
                        st.session_state.custom_df = df_result
                        st.session_state.custom_run_at = datetime.now()
                        st.session_state.custom_selected_ticker = None
                        st.success(f"Screener completed. Found {len(df_result)} matching stocks.")
                except Exception as exc:
                    clear_custom_results()
                    st.error(f"Error running screener: {exc}")

    if st.session_state.custom_df is None:
        render_empty_state(
            "No live custom scan has been run yet.",
            "Try a short list like `RELIANCE.NS`, `TCS.NS`, `INFY.NS`, or paste one ticker per line. This tab is best for ad hoc checks, not the daily index monitor.",
        )
        return

    results_df = st.session_state.custom_df
    summary_cols = st.columns(3)
    with summary_cols[0]:
        st.markdown(
            """
            <div class="ims-card ims-card--accent">
                <div class="ims-kicker">Mode</div>
                <div class="ims-stat-value">Live Custom Session</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with summary_cols[1]:
        run_label = (
            st.session_state.custom_run_at.strftime("%d %b %Y, %I:%M %p")
            if st.session_state.custom_run_at
            else "Unavailable"
        )
        st.markdown(
            f"""
            <div class="ims-card ims-card--compact">
                <div class="ims-kicker">Run At</div>
                <div class="ims-stat-value">{run_label}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with summary_cols[2]:
        st.markdown(
            f"""
            <div class="ims-card ims-card--compact">
                <div class="ims-kicker">Results</div>
                <div class="ims-stat-value">{len(results_df)}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    st.caption("Custom scans may use live downloads for charts when cache data is unavailable.")

    explorer_df = build_custom_explorer_df(results_df)
    search_text = st.text_input("Search", placeholder="Find stock or ticker", key="custom_search_text")
    if search_text:
        mask = (
            explorer_df["Stock"].astype(str).str.contains(search_text, case=False, na=False)
            | explorer_df["Ticker"].astype(str).str.contains(search_text, case=False, na=False)
        )
        filtered_df = explorer_df[mask].reset_index(drop=True)
    else:
        filtered_df = explorer_df

    if filtered_df.empty:
        render_empty_state(
            "No custom results match the current search.",
            "Clear the search input to restore the last run, or run a new batch of tickers.",
        )
        if st.button("Clear custom search", key="clear_custom_search"):
            reset_custom_search()
            st.rerun()
        return

    controls_left, controls_right = st.columns([0.82, 0.18])
    with controls_left:
        st.caption("The explorer keeps only the core fields visible by default. Add optional metrics from `Columns` when needed.")
    with controls_right:
        visible_columns = render_column_selector(
            key="custom_visible_columns",
            default_columns=DEFAULT_CUSTOM_COLUMNS,
            optional_columns=CUSTOM_OPTIONAL_COLUMNS,
        )

    current_selected_ticker = sync_selected_ticker(filtered_df, "custom_selected_ticker")
    selection_event = render_explorer_table(
        filtered_df,
        key="custom_table",
        selected_ticker=current_selected_ticker,
        height=340,
        column_order=visible_columns,
    )
    st.session_state.custom_selected_ticker = resolve_selected_ticker(
        filtered_df,
        selection_event,
        current_selected_ticker,
    )
    st.caption("Select a row in the table to update the stock detail below. One row always stays selected.")

    selected_row = selected_row_from_state(filtered_df, "custom_selected_ticker")
    if selected_row is None:
        st.warning("No stock is available to inspect.")
        return

    selected_ticker = str(selected_row["Ticker"])
    hist, chart_source = fetch_chart_data_with_source(selected_ticker, "custom", get_cache_version("custom"))
    fundamentals = load_experimental_fundamentals(selected_ticker)
    detail_view = build_detail_view(
        selected_row,
        hist,
        chart_source=chart_source,
        fundamental_payload=fundamentals,
    )

    st.markdown("### Stock Detail")
    st.caption(f"The detail section follows the selected row. Chart source for this selection: {chart_source}.")
    render_detail_summary(detail_view)
    control_cols = st.columns([1.6, 0.8], gap="large")
    timeframe = control_cols[0].radio(
        "Timeframe",
        options=["3M", "6M", "1Y"],
        index=2,
        horizontal=True,
        key="custom_timeframe",
    )
    show_mas = control_cols[1].checkbox(
        "Show moving averages",
        value=True,
        key="custom_show_mas",
    )
    render_detail_chart(
        detail_view.chart_df,
        detail_view,
        timeframe=timeframe,
        show_mas=show_mas,
        key_prefix=f"custom_{selected_ticker}",
    )

    render_learn_section()


header_col, help_col = st.columns([0.84, 0.16], vertical_alignment="top")
with header_col:
    render_page_header()
with help_col:
    st.markdown("<div style='padding-top: 8px;'></div>", unsafe_allow_html=True)
    render_header_guide()


monitor_tab, custom_tab = st.tabs(["Market Monitor", "Custom Scan"])
with monitor_tab:
    render_monitor_tab()

with custom_tab:
    render_custom_tab()
