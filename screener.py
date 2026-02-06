import pandas as pd
import yfinance as yf
import requests
from io import StringIO

RSI_PERIOD = 14
RSI_ATTRACTIVE = 40
RSI_OVERBOUGHT = 60
LOOKBACK_PERIOD = "1y"

OVERSOLD_RSI = 30
VOLUME_SPIKE_MULT = 1.5
MAX_DAILY_MOVE = 0.2

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

# ---------------- DATA FETCH ----------------

def extract_series(raw):
    if isinstance(raw.columns, pd.MultiIndex):
        cols = raw.columns.get_level_values(0)
        if "Close" not in cols or "Volume" not in cols or "Adj Close" not in cols:
            return None, None, None, None
        close_series = raw["Close"].iloc[:, 0]
        adj_close_series = raw["Adj Close"].iloc[:, 0]
        volume_series = raw["Volume"].iloc[:, 0]
        split_series = raw["Stock Splits"].iloc[:, 0] if "Stock Splits" in cols else None
    else:
        if "Close" not in raw.columns or "Volume" not in raw.columns or "Adj Close" not in raw.columns:
            return None, None, None, None
        close_series = raw["Close"]
        adj_close_series = raw["Adj Close"]
        volume_series = raw["Volume"]
        split_series = raw["Stock Splits"] if "Stock Splits" in raw.columns else None

    return close_series, adj_close_series, volume_series, split_series

def build_price_df(close_series, adj_close_series, volume_series, split_series):
    df = pd.DataFrame({
        "Close": close_series,
        "Adj Close": adj_close_series,
        "Volume": volume_series
    })

    if split_series is not None:
        df["Split"] = split_series
    else:
        df["Split"] = 0.0

    return df.dropna()

def download_price_df(ticker, retries=1):
    for attempt in range(retries + 1):
        try:
            raw = yf.download(
                ticker,
                period=LOOKBACK_PERIOD,
                interval="1d",
                actions=True,
                auto_adjust=False,
                progress=False
            )
        except Exception:
            continue

        if raw is None or raw.empty:
            continue

        close_series, adj_close_series, volume_series, split_series = extract_series(raw)
        if close_series is None:
            continue

        df = build_price_df(close_series, adj_close_series, volume_series, split_series)
        if len(df) < 2:
            continue

        close = float(df["Close"].iloc[-1])
        prev_close = float(df["Close"].iloc[-2])
        adj_close = float(df["Adj Close"].iloc[-1])
        prev_adj_close = float(df["Adj Close"].iloc[-2])
        last_split = float(df["Split"].iloc[-1]) if "Split" in df else 0.0

        change_ratio = (
            abs(adj_close - prev_adj_close) / prev_adj_close
            if prev_adj_close > 0 else 0.0
        )

        if change_ratio > MAX_DAILY_MOVE and last_split == 0.0 and attempt < retries:
            continue

        return df

    return None

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
    symbols = {}

    for _, row in df.iterrows():
        sym = str(row["Symbol"]).strip().upper()
        name = row["Company Name"]
        symbols[name] = sym + ".NS"

    return symbols

def parse_universe(universe, custom_tickers):
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

# ---------------- MAIN SCREENER ----------------

def run_screener(strategy, universe, custom_tickers, prev_close_map=None):
    tickers = parse_universe(universe, custom_tickers)

    if strategy == "contra":
        strategy_func = contra_strategy
        priority = ["OVERSOLD", "CONTRA BUY", "BUY", "BUILD", "WAIT"]
    else:
        strategy_func = reverse_strategy
        priority = ["SELL", "EXIT", "SHORT", "HOLD"]

    results = []

    for name, ticker in tickers.items():
        df = download_price_df(ticker, retries=1)
        if df is None:
            continue

        if len(df) < 200:
            continue

        if prev_close_map and ticker in prev_close_map:
            prev_close_csv = float(prev_close_map[ticker])
            last_split = float(df["Split"].iloc[-1]) if "Split" in df.columns else 0.0
            if prev_close_csv > 0:
                change_ratio_csv = abs(float(df["Adj Close"].iloc[-1]) - prev_close_csv) / prev_close_csv
                if change_ratio_csv > MAX_DAILY_MOVE and last_split == 0.0:
                    df_retry = download_price_df(ticker, retries=0)
                    if df_retry is None:
                        continue
                    df = df_retry

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
        adj_close = float(latest["Adj Close"])
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
            round(adj_close, 2),
            round(rsi, 2),
            round(volume_ratio, 2),
            action,
            round(ret_pct, 2)
        ])

    df_out = pd.DataFrame(results, columns=[
        "Stock", "Ticker", "Close", "Adj_Close", "RSI", "Vol_Spike", "Action", "1Y_Return_%"
    ])

    df_out["Rank"] = df_out["Action"].apply(
        lambda x: priority.index(x) + 1 if x in priority else 99
    )

    df_out["Rank"] = df_out["Rank"] - df_out["Rank"].min() + 1
    df_out = df_out.sort_values(["Rank", "RSI"]).reset_index(drop=True)

    return df_out
