import streamlit as st
import pandas as pd
import yfinance as yf
from datetime import date, datetime
import os
import plotly.graph_objects as go
from screener import load_price_df_from_cache, run_screener, parse_universe

st.set_page_config(page_title="Indian Market Screener", layout="wide")

# ================= SESSION STATE =================
if "show_help" not in st.session_state:
    st.session_state.show_help = False

if "df" not in st.session_state:
    st.session_state.df = None

if "chart_symbol" not in st.session_state:
    st.session_state.chart_symbol = None

if "scan_info" not in st.session_state:
    st.session_state.scan_info = None

if "universe" not in st.session_state:
    st.session_state.universe = "nifty50"

if "custom_tickers" not in st.session_state:
    st.session_state.custom_tickers = ""

if "is_custom_universe" not in st.session_state:
    st.session_state.is_custom_universe = False

# ================= CACHED CHART DATA =================
@st.cache_data(show_spinner=False)
def fetch_chart_data(ticker, universe, cache_version):
    _ = cache_version  # part of cache key to invalidate when local cache file changes

    # Try to load from cache first
    cached_data = load_price_df_from_cache(ticker, universe)
    if cached_data is not None and not cached_data.empty:
        return cached_data
    
    # Fall back to yfinance if cache miss
    return yf.download(ticker, period="1y", interval="1d", progress=False)

def get_cache_version(universe):
    cache_file = f"price_cache_{universe}.csv"
    try:
        return os.path.getmtime(cache_file)
    except OSError:
        return 0

# ================= HELP PAGE =================
if st.session_state.show_help:
    col1, col2, col3 = st.columns([0.85, 0.10, 0.05])
    with col2:
        st.markdown("<div style='padding-top: 8px; text-align: center;'></div>", unsafe_allow_html=True)
        if st.button("✕", key="close_help_btn"):
            st.session_state.show_help = False
            st.rerun()
    
    # Add red styling for close button
    st.markdown("""
        <style>
        button[key="close_help_btn"] {
            color: red !important;
            font-size: 18px !important;
        }
        </style>
        """, unsafe_allow_html=True)

    try:
        with open("README.md", "r", encoding="utf-8") as f:
            st.markdown(f.read())
    except FileNotFoundError:
        st.error("README.md not found!")

    st.stop()

# ================= MAIN PAGE =================
col1, col2, col3 = st.columns([0.85, 0.10, 0.05])
with col1:
    st.title("Indian Market Screener")
with col2:
    st.markdown("<div style='padding-top: 12px; text-align: center;'></div>", unsafe_allow_html=True)
    if st.button("❓", key="help_btn"):
        st.session_state.show_help = True
        st.rerun()

# Add red styling for help button
st.markdown("""
    <style>
    button[key="help_btn"] {
        color: red !important;
        font-size: 20px !important;
    }
    </style>
    """, unsafe_allow_html=True)

with st.sidebar:
    st.header("Controls")

    universe = st.selectbox("Universe", ["nifty50", "niftynext50", "custom"], 
                           index=["nifty50", "niftynext50", "custom"].index(st.session_state.universe) if st.session_state.universe in ["nifty50", "niftynext50", "custom"] else 0)
    st.session_state.universe = universe

    # Show custom ticker input only when custom universe is selected
    if universe == "custom":
        st.session_state.is_custom_universe = True
        custom_tickers = st.text_area(
            "Custom Tickers",
            value=st.session_state.custom_tickers,
            height=80,
            placeholder="Enter ticker symbols (one per line or comma-separated).\nExample: RELIANCE.NS\nTCS.NS\nINFY.NS",
            help="Enter NSE ticker symbols"
        )
        st.session_state.custom_tickers = custom_tickers

        if st.button("Run Screener", type="primary"):
            if not custom_tickers.strip():
                st.error("Please enter at least one ticker symbol")
            else:
                with st.spinner("Running screener..."):
                    try:
                        # Convert multiline/comma-separated input to comma-separated string
                        tickers_input = custom_tickers.replace('\n', ',')
                        
                        # Run the screener
                        df_result = run_screener(
                            strategy="contra",
                            universe="custom",
                            custom_tickers=tickers_input,
                            max_workers=10,
                            batch_size=10
                        )
                        
                        if df_result.empty:
                            st.error("No results found. Please check your ticker symbols and try again.")
                        else:
                            st.session_state.df = df_result
                            st.session_state.chart_symbol = None
                            st.session_state.scan_info = f"Custom scan run at: {datetime.now().strftime('%Y-%m-%d %I:%M %p')}"
                            st.session_state.is_custom_universe = True
                            st.success(f"Screener completed! Found {len(df_result)} stocks matching criteria.")
                    except Exception as e:
                        st.error(f"Error running screener: {str(e)}")
    else:
        st.session_state.is_custom_universe = False
        if st.button("Load Latest Scan", type="primary"):
            if universe == "nifty50":
                filename = "latest_scan_nifty50.csv"
            elif universe == "niftynext50":
                filename = "latest_scan_niftynext50.csv"
            else:
                st.error("Invalid universe selected")
                st.stop()

            if os.path.exists(filename):
                st.session_state.df = pd.read_csv(filename)
                st.session_state.chart_symbol = None  # Reset chart symbol for new data

                # get file modified time as scan date
                ts = os.path.getmtime(filename)
                scan_time = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %I:%M %p")

                st.session_state.scan_info = f"Data as of: {scan_time}"
                st.success("Loaded")
            else:
                st.error("Scan file not found. Please run nightly_scan.py first.")

if st.session_state.df is None:
    st.info("Select a universe and click **Load Latest Scan** (for Nifty indices) or **Run Screener** (for custom tickers).")
    st.stop()

df = st.session_state.df

if df.empty:
    st.warning("Scan file is empty.")
    st.stop()

# -------- Results --------
if st.session_state.scan_info:
    st.info(f"Screener Results as of: {st.session_state.scan_info.replace('Data as of: ', '')}")
else:
    st.info("Screener Results")

# ================= STOCK FILTER =================
filter_text = st.text_input("Filter by Stock name")

if filter_text:
    df_filtered = df[df["Stock"].str.contains(filter_text, case=False, na=False)]
else:
    df_filtered = df

df_display = df_filtered.drop(columns=["Adj_Close"], errors="ignore")
st.dataframe(df_display, width="stretch", hide_index=True)

# -------- Chart Viewer --------
st.subheader("Chart Viewer")

symbols = df_filtered["Ticker"].tolist()

if not symbols:
    st.warning("No stocks match your filter.")
    st.stop()

if st.session_state.chart_symbol not in symbols:
    st.session_state.chart_symbol = symbols[0]

def on_chart_symbol_change():
    st.session_state.chart_symbol = st.session_state.chart_selector

chart_symbol = st.selectbox(
    "Select stock",
    symbols,
    index=symbols.index(st.session_state.chart_symbol),
    key="chart_selector",
    on_change=on_chart_symbol_change
)

st.session_state.chart_symbol = chart_symbol

cache_version = get_cache_version(st.session_state.universe)
hist = fetch_chart_data(chart_symbol, st.session_state.universe, cache_version)

if hist is None or hist.empty:
    st.error(f"No historical data for {chart_symbol}")
    st.stop()

# ===== Prepare OHLC data for candlestick chart =====
# Check if we have OHLC data in the dataframe
has_ohlc = all(col in hist.columns for col in ["Open", "High", "Low", "Close"]) if not isinstance(hist.columns, pd.MultiIndex) else False

if isinstance(hist.columns, pd.MultiIndex):
    # Handle MultiIndex columns from yfinance batch mode
    cols = hist.columns.get_level_values(0)
    if all(col in cols for col in ["Open", "High", "Low", "Close"]):
        open_series = hist["Open"].iloc[:, 0]
        high_series = hist["High"].iloc[:, 0]
        low_series = hist["Low"].iloc[:, 0]
        close_series = hist["Close"].iloc[:, 0]
        has_ohlc = True
    elif "Close" in cols:
        close_series = hist["Close"].iloc[:, 0]
    else:
        st.error("No Close column found.")
        st.stop()
else:
    # Handle flat columns from cache or single ticker
    if has_ohlc:
        open_series = hist["Open"]
        high_series = hist["High"]
        low_series = hist["Low"]
        close_series = hist["Close"]
    else:
        if "Close" not in hist.columns:
            st.error("No Close column found.")
            st.stop()
        close_series = hist["Close"]

# Create candlestick chart if we have OHLC data, otherwise line chart
if has_ohlc:
    # Prepare data for candlestick chart
    df_chart = pd.DataFrame({
        "Date": hist.index if not isinstance(hist.index, pd.DatetimeIndex) else hist.index,
        "Open": open_series.values,
        "High": high_series.values,
        "Low": low_series.values,
        "Close": close_series.values
    })
    df_chart["Date"] = pd.to_datetime(df_chart["Date"])
    df_chart = df_chart.sort_values("Date")
    
    # Create candlestick figure
    fig = go.Figure(data=[go.Candlestick(
        x=df_chart["Date"],
        open=df_chart["Open"],
        high=df_chart["High"],
        low=df_chart["Low"],
        close=df_chart["Close"],
        name=chart_symbol
    )])
    
    fig.update_layout(
        title=f"{chart_symbol} - Last 1 Year Candlestick Chart",
        yaxis_title="Stock Price (₹)",
        xaxis_title="Date",
        template="plotly_white",
        height=600,
        hovermode="x unified"
    )
    
    st.plotly_chart(fig, use_container_width=True)
else:
    # Fallback to line chart if no OHLC data
    close_series = pd.to_numeric(close_series, errors="coerce").dropna()
    plot_df = close_series.to_frame(name="Close").reset_index()
    plot_df["Date"] = pd.to_datetime(plot_df["Date"])
    st.line_chart(plot_df.set_index("Date")["Close"])
