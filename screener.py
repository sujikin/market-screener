import pandas as pd
import yfinance as yf
import requests
from io import StringIO
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

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

def load_price_df_from_cache(ticker, universe):
    """Load price data from cache CSV file"""
    cache_file = f"price_cache_{universe}.csv"
    if not os.path.exists(cache_file):
        return None
    
    try:
        cache_df = pd.read_csv(cache_file)
        # Filter for the specific ticker
        ticker_data = cache_df[cache_df["Ticker"] == ticker].copy()
        if ticker_data.empty:
            return None
        
        # Convert Date to datetime and set as index
        ticker_data["Date"] = pd.to_datetime(ticker_data["Date"])
        ticker_data = ticker_data.sort_values("Date")
        ticker_data.set_index("Date", inplace=True)
        
        # Drop ticker column since we don't need it anymore
        ticker_data = ticker_data.drop(columns=["Ticker"])
        
        return ticker_data
    except Exception:
        return None

def save_price_df_to_cache(ticker, df, universe):
    """Save price data to cache CSV file"""
    cache_file = f"price_cache_{universe}.csv"
    
    try:
        # Reset index to make Date a column
        df_to_save = df.reset_index()
        df_to_save["Date"] = pd.to_datetime(df_to_save["Date"]).dt.strftime("%Y-%m-%d")
        df_to_save["Ticker"] = ticker
        
        # Load existing cache
        if os.path.exists(cache_file):
            cache_df = pd.read_csv(cache_file)
            # Remove old data for this ticker
            cache_df = cache_df[cache_df["Ticker"] != ticker]
            # Append new data
            cache_df = pd.concat([cache_df, df_to_save], ignore_index=True)
        else:
            cache_df = df_to_save
        
        # Reorder columns
        cols = ["Ticker", "Date", "Close", "Adj Close", "Volume"]
        if "Split" in cache_df.columns:
            cols.append("Split")
        cache_df = cache_df[cols]
        
        cache_df.to_csv(cache_file, index=False)
    except Exception:
        pass  # Silently fail cache write to not break the screener

def download_price_batch(tickers, retries=1, universe=None, use_cache=True):
    """Download multiple tickers in a single batch call for efficiency"""
    results = {}  # ticker -> DataFrame mapping
    
    # Try cache first for all tickers
    tickers_to_fetch = []
    for ticker in tickers:
        if use_cache and universe:
            cached_df = load_price_df_from_cache(ticker, universe)
            if cached_df is not None and len(cached_df) >= 2:
                results[ticker] = cached_df
                continue
        tickers_to_fetch.append(ticker)
    
    if not tickers_to_fetch:
        return results
    
    for attempt in range(retries + 1):
        try:
            # Download all tickers in batch (much faster than individual calls)
            raw = yf.download(
                tickers_to_fetch,
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
        
        # Process each ticker from the batch result
        for ticker in tickers_to_fetch:
            try:
                if len(tickers_to_fetch) == 1:
                    ticker_data = raw
                else:
                    ticker_data = raw[raw.columns[raw.columns.get_level_values(1) == ticker]]
                    if ticker_data.empty:
                        continue
                
                close_series, adj_close_series, volume_series, split_series = extract_series(ticker_data)
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
                
                # Save to cache if universe is provided
                if universe:
                    save_price_df_to_cache(ticker, df, universe)
                
                results[ticker] = df
            except Exception:
                continue
        
        # If we got results, return them
        if results:
            return results
    
    return results

def download_price_df(ticker, retries=1, universe=None, use_cache=True):
    # Try to load from cache first if use_cache is True
    if use_cache and universe:
        cached_df = load_price_df_from_cache(ticker, universe)
        if cached_df is not None and len(cached_df) >= 2:
            return cached_df
    
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

        # Save to cache if universe is provided
        if universe:
            save_price_df_to_cache(ticker, df, universe)

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
    elif which == "nifty500":
        url = "https://nsearchives.nseindia.com/content/indices/ind_nifty500list.csv"
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
    if universe == "nifty500":
        return fetch_nse_universe("nifty500")
    if universe == "custom":
        tickers = {}
        for t in custom_tickers.split(","):
            t = t.strip().upper()
            if t:
                # If ticker already has .NS or .BO suffix, use it as-is
                if t.endswith(".NS") or t.endswith(".BO"):
                    tickers[t] = t
                else:
                    # Otherwise append .NS
                    tickers[t] = t + ".NS"
        return tickers
    raise ValueError("Invalid universe")

# ---------------- MAIN SCREENER ----------------

def _process_ticker(name, ticker, universe, prev_close_map):
    """Process a single ticker and return results if applicable"""
    df = download_price_df(ticker, retries=1, universe=universe, use_cache=True)
    if df is None:
        return None

    if len(df) < 200:
        return None

    if prev_close_map and ticker in prev_close_map:
        prev_close_csv = float(prev_close_map[ticker])
        last_split = float(df["Split"].iloc[-1]) if "Split" in df.columns else 0.0
        if prev_close_csv > 0:
            change_ratio_csv = abs(float(df["Adj Close"].iloc[-1]) - prev_close_csv) / prev_close_csv
            if change_ratio_csv > MAX_DAILY_MOVE and last_split == 0.0:
                df_retry = download_price_df(ticker, retries=0, universe=universe, use_cache=False)
                if df_retry is None:
                    return None
                df = df_retry

    df["RSI"] = compute_rsi(df["Close"])
    df["50DMA"] = df["Close"].rolling(50).mean()
    df["200DMA"] = df["Close"].rolling(200).mean()
    df["MACD"], df["Signal"], df["Hist"] = compute_macd(df["Close"])
    df["AvgVol20"] = df["Volume"].rolling(20).mean()

    df = df.dropna()
    if len(df) < 2:
        return None

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
        action = "WAIT"  # Default, will be updated below
        if (close < dma50 < dma200) and (rsi < RSI_ATTRACTIVE):
            action = "CONTRA BUY"
        elif (close > dma200) and (rsi < RSI_ATTRACTIVE):
            action = "BUY"
        elif (close > dma50 > dma200):
            action = "BUILD"
        elif (close > dma50 > dma200) and (rsi > RSI_OVERBOUGHT):
            action = "SELL"
        elif (close < dma200) and (rsi > RSI_ATTRACTIVE):
            action = "EXIT"
        elif (close < dma50 < dma200):
            action = "SHORT"
        elif (close > dma50 > dma200) and (rsi > RSI_OVERBOUGHT):
            action = "SELL"
        else:
            if (close > dma50 > dma200) and (rsi > RSI_OVERBOUGHT):
                action = "SELL"
            else:
                action = "HOLD"

    first_price = float(df["Close"].iloc[0])
    ret_pct = (close - first_price) / first_price * 100

    return [
        name, ticker,
        round(close, 2),
        round(adj_close, 2),
        round(rsi, 2),
        round(volume_ratio, 2),
        action,
        round(ret_pct, 2)
    ]

def run_screener(strategy, universe, custom_tickers, prev_close_map=None, max_workers=10, batch_size=50):
    tickers_dict = parse_universe(universe, custom_tickers)
    tickers_list = list(tickers_dict.keys())
    ticker_symbols = list(tickers_dict.values())

    if strategy == "contra":
        strategy_func = contra_strategy
        priority = ["OVERSOLD", "CONTRA BUY", "BUY", "BUILD", "WAIT"]
    else:
        strategy_func = reverse_strategy
        priority = ["SELL", "EXIT", "SHORT", "HOLD"]

    results = []

    # Create batches of tickers for efficient downloading
    batches = [ticker_symbols[i:i + batch_size] for i in range(0, len(ticker_symbols), batch_size)]
    batch_names = [tickers_list[i:i + batch_size] for i in range(0, len(tickers_list), batch_size)]

    # Use ThreadPoolExecutor for parallel batch downloads
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit batch download tasks
        futures = {
            executor.submit(download_price_batch, batch, 1, universe, True): idx
            for idx, batch in enumerate(batches)
        }

        # Collect results as batches complete
        for future in as_completed(futures):
            try:
                batch_results = future.result()
                # batch_results is a dict of {ticker -> DataFrame}
                for ticker_symbol, df in batch_results.items():
                    # Find the corresponding name
                    idx = ticker_symbols.index(ticker_symbol)
                    name = tickers_list[idx]
                    
                    # Process this ticker
                    if df is None:
                        continue
                    if len(df) < 200:
                        continue

                    if prev_close_map and ticker_symbol in prev_close_map:
                        prev_close_csv = float(prev_close_map[ticker_symbol])
                        last_split = float(df["Split"].iloc[-1]) if "Split" in df.columns else 0.0
                        if prev_close_csv > 0:
                            change_ratio_csv = abs(float(df["Adj Close"].iloc[-1]) - prev_close_csv) / prev_close_csv
                            if change_ratio_csv > MAX_DAILY_MOVE and last_split == 0.0:
                                df_retry = download_price_df(ticker_symbol, retries=0, universe=universe, use_cache=False)
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
                        action = "WAIT"
                        if (close < dma50 < dma200) and (rsi < RSI_ATTRACTIVE):
                            action = "CONTRA BUY"
                        elif (close > dma200) and (rsi < RSI_ATTRACTIVE):
                            action = "BUY"
                        elif (close > dma50 > dma200):
                            action = "BUILD"
                        elif (close > dma50 > dma200) and (rsi > RSI_OVERBOUGHT):
                            action = "SELL"
                        elif (close < dma200) and (rsi > RSI_ATTRACTIVE):
                            action = "EXIT"
                        elif (close < dma50 < dma200):
                            action = "SHORT"
                        elif (close > dma50 > dma200) and (rsi > RSI_OVERBOUGHT):
                            action = "SELL"
                        else:
                            if (close > dma50 > dma200) and (rsi > RSI_OVERBOUGHT):
                                action = "SELL"
                            else:
                                action = "HOLD"

                    first_price = float(df["Close"].iloc[0])
                    ret_pct = (close - first_price) / first_price * 100

                    results.append([
                        name, ticker_symbol,
                        round(close, 2),
                        round(adj_close, 2),
                        round(rsi, 2),
                        round(volume_ratio, 2),
                        action,
                        round(ret_pct, 2)
                    ])
            except Exception as e:
                continue

    df_out = pd.DataFrame(results, columns=[
        "Stock", "Ticker", "Close", "Adj_Close", "RSI", "Vol_Spike", "Action", "1Y_Return_%"
    ])

    if df_out.empty:
        return df_out

    df_out["Rank"] = df_out["Action"].apply(
        lambda x: priority.index(x) + 1 if x in priority else 99
    )

    df_out["Rank"] = df_out["Rank"] - df_out["Rank"].min() + 1
    df_out = df_out.sort_values(["Rank", "RSI"]).reset_index(drop=True)

    return df_out
