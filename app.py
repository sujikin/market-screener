import streamlit as st
import pandas as pd
import yfinance as yf
from datetime import date, datetime
import os

st.set_page_config(page_title="📊 Indian Market Screener", layout="wide")

# ================= SESSION STATE =================
if "show_help" not in st.session_state:
    st.session_state.show_help = False

if "df" not in st.session_state:
    st.session_state.df = None

if "chart_symbol" not in st.session_state:
    st.session_state.chart_symbol = None

if "scan_info" not in st.session_state:
    st.session_state.scan_info = None

# ================= CACHED CHART DATA =================
@st.cache_data(show_spinner=False)
def fetch_chart_data(ticker, cache_day):
    return yf.download(ticker, period="1y", interval="1d", progress=False)

# ================= HELP PAGE =================
if st.session_state.show_help:
    col1, col2 = st.columns([0.95, 0.05])
    with col2:
        if st.button("✕"):
            st.session_state.show_help = False
            st.rerun()

    try:
        with open("README.md", "r", encoding="utf-8") as f:
            st.markdown(f.read())
    except FileNotFoundError:
        st.error("README.md not found!")

    st.stop()

# ================= MAIN PAGE =================
col1, col2 = st.columns([0.95, 0.05])
with col1:
    st.title("📈 Indian Market Screener")
with col2:
    if st.button("❓"):
        st.session_state.show_help = True
        st.rerun()

with st.sidebar:
    st.header("⚙️ Controls")

    universe = st.selectbox("Universe", ["nifty50", "niftynext50"])

    if st.button("📂 Load Latest Scan"):
        if universe == "nifty50":
            filename = "latest_scan_nifty50.csv"
        else:
            filename = "latest_scan_niftynext50.csv"

        if os.path.exists(filename):
            st.session_state.df = pd.read_csv(filename)

            # get file modified time as scan date
            ts = os.path.getmtime(filename)
            scan_time = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %I:%M %p")

            st.session_state.scan_info = f"Data as of: {scan_time}"
            st.success("Loaded")
        else:
            st.error("Scan file not found. Please run nightly_scan.py first.")

if st.session_state.df is None:
    st.info("Select universe and click **Load Latest Scan**.")
    st.stop()

df = st.session_state.df

if df.empty:
    st.warning("Scan file is empty.")
    st.stop()

# -------- Results --------
if st.session_state.scan_info:
    st.info(f"📋 Screener Results as of: {st.session_state.scan_info.replace('Data as of: ', '')}")
else:
    st.info("📋 Screener Results")

# ================= STOCK FILTER =================
filter_text = st.text_input("🔍 Filter by Stock name")

if filter_text:
    df_filtered = df[df["Stock"].str.contains(filter_text, case=False, na=False)]
else:
    df_filtered = df

st.dataframe(df_filtered, width="stretch")

# -------- Chart Viewer --------
st.subheader("📈 Chart Viewer")

symbols = df_filtered["Ticker"].tolist()

if not symbols:
    st.warning("No stocks match your filter.")
    st.stop()

if st.session_state.chart_symbol not in symbols:
    st.session_state.chart_symbol = symbols[0]

chart_symbol = st.selectbox(
    "Select stock",
    symbols,
    index=symbols.index(st.session_state.chart_symbol)
)

st.session_state.chart_symbol = chart_symbol

hist = fetch_chart_data(chart_symbol, cache_day=date.today())

if hist is None or hist.empty:
    st.error(f"No historical data for {chart_symbol}")
    st.stop()

# ===== Handle MultiIndex columns =====
if isinstance(hist.columns, pd.MultiIndex):
    if "Close" in hist.columns.get_level_values(0):
        close_series = hist["Close"].iloc[:, 0]
    else:
        st.error("No Close column found.")
        st.stop()
else:
    if "Close" not in hist.columns:
        st.error("No Close column found.")
        st.stop()
    close_series = hist["Close"]

close_series = pd.to_numeric(close_series, errors="coerce").dropna()

plot_df = close_series.to_frame(name="Close").reset_index()
plot_df["Date"] = pd.to_datetime(plot_df["Date"])

st.line_chart(plot_df.set_index("Date")["Close"])
