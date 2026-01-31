import pandas as pd
import yfinance as yf
import requests
from io import StringIO
from datetime import datetime
import streamlit as st

RSI_PERIOD = 14
RSI_OVERSOLD = 30
RSI_ATTRACTIVE = 40
RSI_OVERBOUGHT = 60
LOOKBACK_PERIOD = "1y"

# ================= RSI =================
def compute_rsi(series, period=RSI_PERIOD):
    delta = series.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = -delta.clip(upper=0).rolling(period).mean()
    rs = gain / (loss + 1e-10)
    return 100 - (100 / (1 + rs))

# ================= Strategies =================
def contra_strategy(close, rsi, dma50, dma200):
    if (close < dma50 < dma200) and (rsi < RSI_ATTRACTIVE):
        return "CONTRA BUY"
    elif (close > dma200) and (rsi < RSI_ATTRACTIVE):
        return "BUY"
    elif (close > dma50 > dma200):
        return "BUILD"
    else:
        return "WAIT"

def reverse_strategy(close, rsi, dma50, dma200):
    if (close > dma50 > dma200) and (rsi > RSI_OVERBOUGHT):
        return "SELL"
    elif (close < dma200) and (rsi > RSI_ATTRACTIVE):
        return "EXIT"
    elif (close < dma50 < dma200):
        return "SHORT"
    else:
        return "HOLD"

# ================= NSE Universe =================
@st.cache_data(ttl=604800)  # Cache for 7 days (NSE lists rarely change)
def fetch_nse_universe(which):
    if which == "nifty50":
        url = "https://nsearchives.nseindia.com/content/indices/ind_nifty50list.csv"
    elif which == "niftynext50":
        url = "https://nsearchives.nseindia.com/content/indices/ind_niftynext50list.csv"
    else:
        raise ValueError("Invalid NSE universe")

    headers = {"User-Agent": "Mozilla/5.0"}
    r = requests.get(url, headers=headers, timeout=15)
    r.raise_for_status()

    df = pd.read_csv(StringIO(r.text))

    if "Symbol" not in df.columns:
        raise RuntimeError("NSE CSV missing Symbol column")

    symbols = {}
    for _, row in df.iterrows():
        sym = str(row["Symbol"]).strip().upper()
        name = row["Company Name"] if "Company Name" in df.columns else sym
        symbols[name] = sym + ".NS"

    return symbols

def parse_universe(universe, custom_tickers=None):
    if universe == "nifty50":
        return fetch_nse_universe("nifty50")
    if universe == "niftynext50":
        return fetch_nse_universe("niftynext50")
    if universe == "custom":
        tickers = {}
        for t in custom_tickers.split(","):
            t = t.strip().upper()
            if t:
                tickers[t] = t + ".NS"
        return tickers
    raise ValueError("Invalid universe")

# ================= MAIN LOGIC =================
@st.cache_data(ttl=86400)  # Cache for 24 hours (1 day)
def run_screener(strategy="contra", universe="nifty50", custom_tickers=None):
    tickers = parse_universe(universe, custom_tickers)

    if strategy == "contra":
        strategy_func = contra_strategy
        priority = ["CONTRA BUY", "BUY", "BUILD", "WAIT"]
    else:
        strategy_func = reverse_strategy
        priority = ["SELL", "EXIT", "SHORT", "HOLD"]

    results = []

    for name, ticker in tickers.items():
        try:
            data = yf.download(ticker, period=LOOKBACK_PERIOD, progress=False)
        except Exception:
            continue

        if data.empty:
            continue

        data["RSI"] = compute_rsi(data["Close"])
        data["50DMA"] = data["Close"].rolling(50).mean()
        data["200DMA"] = data["Close"].rolling(200).mean()
        data = data.dropna()

        if data.empty:
            continue

        close  = data["Close"].iloc[-1].item()
        rsi    = data["RSI"].iloc[-1].item()
        dma50  = data["50DMA"].iloc[-1].item()
        dma200 = data["200DMA"].iloc[-1].item()

        action = strategy_func(close, rsi, dma50, dma200)

        first_price = data["Close"].iloc[0].item()
        ret_pct = round((close - first_price) / first_price * 100, 2)

        results.append([
            name, ticker, round(close,2), round(rsi,2),
            action, ret_pct
        ])

    df = pd.DataFrame(results, columns=[
        "Stock","Ticker","Close","RSI","Action","1Y_Return_%"
    ])

    df["Rank"] = df["Action"].apply(lambda x: priority.index(x) if x in priority else 99)
    df = df.sort_values(["Rank","RSI"]).reset_index(drop=True)

    return df