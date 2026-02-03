import pandas as pd
import yfinance as yf
import requests
from io import StringIO
import streamlit as st
from datetime import date
import numpy as np

RSI_PERIOD = 14
RSI_ATTRACTIVE = 40
RSI_OVERBOUGHT = 60
LOOKBACK_PERIOD = "1y"

OVERSOLD_RSI = 30
VOLUME_SPIKE_MULT = 1.5

# ---------------- INDICATORS ----------------

def compute_rsi(series, period=RSI_PERIOD):
    delta = series.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = -delta.clip(upper=0).rolling(period).mean()
    rs = gain / (loss + 1e-10)
    return 100 - (100 / (1 + rs))

def compute_macd(series, fast=12, slow=26, signal=9):
    ema_fast = series.ewm(span=fast, adjust=False).mean()
    ema_slow = series.ewm(span=slow, adjust=False).mean()
    macd = ema_fast - ema_slow
    signal_line = macd.ewm(span=signal, adjust=False).mean()
    hist = macd - signal_line
    return macd, signal_line, hist

# ---------------- STRATEGIES ----------------

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

# ---------------- UNIVERSE ----------------

@st.cache_data(show_spinner=False)
def fetch_nse_universe(which, cache_day):
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
    symbols = {}

    for _, row in df.iterrows():
        sym = str(row["Symbol"]).strip().upper()
        name = row["Company Name"]
        symbols[name] = sym + ".NS"

    return symbols

def parse_universe(universe, custom_tickers, cache_day):
    if universe == "nifty50":
        return fetch_nse_universe("nifty50", cache_day)
    if universe == "niftynext50":
        return fetch_nse_universe("niftynext50", cache_day)
    if universe == "custom":
        tickers = {}
        for t in custom_tickers.split(","):
            t = t.strip().upper()
            if t:
                tickers[t] = t + ".NS"
        return tickers
    raise ValueError("Invalid universe")

# ---------------- MAIN SCREENER ----------------

@st.cache_data(show_spinner=False)
def run_screener(strategy, universe, custom_tickers, cache_day):
    tickers = parse_universe(universe, custom_tickers, cache_day)

    if strategy == "contra":
        strategy_func = contra_strategy
        priority = ["OVERSOLD", "CONTRA BUY", "BUY", "BUILD", "WAIT"]
    else:
        strategy_func = reverse_strategy
        priority = ["SELL", "EXIT", "SHORT", "HOLD"]

    results = []

    for name, ticker in tickers.items():
        try:
            raw = yf.download(ticker, period=LOOKBACK_PERIOD, progress=False)
        except Exception:
            continue

        if raw is None or raw.empty:
            continue

        if isinstance(raw.columns, pd.MultiIndex):
            if "Close" not in raw.columns.get_level_values(0):
                continue
            close_series = raw["Close"].iloc[:, 0]
            volume_series = raw["Volume"].iloc[:, 0]
        else:
            if "Close" not in raw.columns or "Volume" not in raw.columns:
                continue
            close_series = raw["Close"]
            volume_series = raw["Volume"]

        df = pd.DataFrame({
            "Close": close_series,
            "Volume": volume_series
        }).dropna()

        if len(df) < 50:
            continue

        df["RSI"] = compute_rsi(df["Close"])
        df["50DMA"] = df["Close"].rolling(50).mean()
        df["200DMA"] = df["Close"].rolling(200).mean()
        df["MACD"], df["Signal"], df["Hist"] = compute_macd(df["Close"])
        df["AvgVol20"] = df["Volume"].rolling(20).mean()

        df = df.dropna()
        if len(df) < 2:
            continue

        latest = df.iloc[-1]
        prev = df.iloc[-2]

        close = float(latest["Close"])
        rsi = float(latest["RSI"])
        dma50 = float(latest["50DMA"])
        dma200 = float(latest["200DMA"])

        volume_ratio = float(latest["Volume"]) / float(latest["AvgVol20"])

        is_oversold = (
            rsi < OVERSOLD_RSI and
            float(latest["Volume"]) > VOLUME_SPIKE_MULT * float(latest["AvgVol20"]) and
            close < dma50 and
            latest["Hist"] > prev["Hist"]
        )

        if is_oversold:
            action = "OVERSOLD"
        else:
            action = strategy_func(close, rsi, dma50, dma200)

        first_price = float(df["Close"].iloc[0])
        ret_pct = (close - first_price) / first_price * 100

        results.append([
            name, ticker,
            round(close, 2),
            round(rsi, 2),
            round(volume_ratio, 2),
            action,
            round(ret_pct, 2)
        ])

    df_out = pd.DataFrame(results, columns=[
        "Stock", "Ticker", "Close", "RSI", "Vol_Spike", "Action", "1Y_Return_%"
    ])

    df_out["Rank"] = df_out["Action"].apply(
        lambda x: priority.index(x) + 1 if x in priority else 99
    )

    df_out["Rank"] = df_out["Rank"] - df_out["Rank"].min() + 1
    df_out = df_out.sort_values(["Rank", "RSI"]).reset_index(drop=True)

    return df_out
