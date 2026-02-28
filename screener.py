import pandas as pd
import yfinance as yf
import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry
from io import StringIO
import os
import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    filename='screener.log',
    filemode='a'
)
root_logger = logging.getLogger("")
has_console_handler = any(
    isinstance(handler, logging.StreamHandler) and not isinstance(handler, logging.FileHandler)
    for handler in root_logger.handlers
)
if not has_console_handler:
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    console.setFormatter(formatter)
    root_logger.addHandler(console)

# Locks for thread-safe cache writes
cache_locks = {}  # universe -> Lock mapping

def get_cache_lock(universe):
    """Get or create a lock for a universe's cache file."""
    if universe not in cache_locks:
        cache_locks[universe] = Lock()
    return cache_locks[universe]

RSI_PERIOD = 14
RSI_ATTRACTIVE = 40
RSI_OVERBOUGHT = 60
LOOKBACK_PERIOD = "1y"

OVERSOLD_RSI = 30
VOLUME_SPIKE_MULT = 1.5
MAX_DAILY_MOVE = 0.2
YF_DOWNLOAD_TIMEOUT_SECONDS = 30

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
    """Extract OHLCV series from yfinance data. Returns 7 values for candlestick support."""
    if isinstance(raw.columns, pd.MultiIndex):
        cols = raw.columns.get_level_values(0)
        if "Close" not in cols or "Volume" not in cols:
            return None, None, None, None, None, None, None
        # Extract OHLC data
        open_series = raw["Open"].iloc[:, 0] if "Open" in cols else None
        high_series = raw["High"].iloc[:, 0] if "High" in cols else None
        low_series = raw["Low"].iloc[:, 0] if "Low" in cols else None
        close_series = raw["Close"].iloc[:, 0]
        # Use "Adj Close" if available, otherwise fall back to "Close"
        if "Adj Close" in cols:
            adj_close_series = raw["Adj Close"].iloc[:, 0]
        else:
            adj_close_series = close_series.copy()
        volume_series = raw["Volume"].iloc[:, 0]
        split_series = raw["Stock Splits"].iloc[:, 0] if "Stock Splits" in cols else None
    else:
        if "Close" not in raw.columns or "Volume" not in raw.columns:
            return None, None, None, None, None, None, None
        # Extract OHLC data
        open_series = raw["Open"] if "Open" in raw.columns else None
        high_series = raw["High"] if "High" in raw.columns else None
        low_series = raw["Low"] if "Low" in raw.columns else None
        close_series = raw["Close"]
        # Use "Adj Close" if available, otherwise fall back to "Close"
        if "Adj Close" in raw.columns:
            adj_close_series = raw["Adj Close"]
        else:
            adj_close_series = close_series.copy()
        volume_series = raw["Volume"]
        split_series = raw["Stock Splits"] if "Stock Splits" in raw.columns else None

    return open_series, high_series, low_series, close_series, adj_close_series, volume_series, split_series

def build_price_df(open_series, high_series, low_series, close_series, adj_close_series, volume_series, split_series):
    """Build price DataFrame with OHLCV data for candlestick charting support."""
    df_data = {
        "Close": close_series,
        "Adj_Close": adj_close_series,
        "Volume": volume_series
    }
    
    # Include OHLC data if available
    if open_series is not None:
        df_data["Open"] = open_series
    if high_series is not None:
        df_data["High"] = high_series
    if low_series is not None:
        df_data["Low"] = low_series
    
    df = pd.DataFrame(df_data)

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
    except (pd.errors.EmptyDataError, pd.errors.ParserError, UnicodeDecodeError) as e:
        logging.warning(f"Cache file {cache_file} is unreadable: {e}")
        return None
    except Exception as e:
        logging.warning(f"Failed to read cache file {cache_file}: {e}")
        return None

    try:
        required_cols = {"Ticker", "Date"}
        if cache_df.empty or not required_cols.issubset(cache_df.columns):
            logging.warning(
                f"Cache file {cache_file} missing required columns. "
                f"Expected {sorted(required_cols)}, found {sorted(cache_df.columns.tolist())}."
            )
            return None

        # Filter for the specific ticker
        ticker_data = cache_df[cache_df["Ticker"] == ticker].copy()
        if ticker_data.empty:
            return None

        # Convert Date to datetime and set as index
        ticker_data["Date"] = pd.to_datetime(ticker_data["Date"])
        ticker_data = ticker_data.sort_values("Date")
        ticker_data.set_index("Date", inplace=True)

        # Standardize column name for compatibility (rename old 'Adj Close' to 'Adj_Close')
        if "Adj Close" in ticker_data.columns and "Adj_Close" not in ticker_data.columns:
            ticker_data = ticker_data.rename(columns={"Adj Close": "Adj_Close"})

        # Drop ticker column since we don't need it anymore
        ticker_data = ticker_data.drop(columns=["Ticker"], errors="ignore")

        return ticker_data
    except Exception as e:
        logging.warning(f"Failed to load cache for {ticker}: {e}")
        return None

def save_price_df_to_cache(ticker, df, universe):
    """Save price data to cache CSV file using atomic write with thread safety"""
    cache_file = f"price_cache_{universe}.csv"
    cache_lock = get_cache_lock(universe)
    
    try:
        with cache_lock:
            # Reset index to make Date a column
            df_to_save = df.reset_index()
            df_to_save["Date"] = pd.to_datetime(df_to_save["Date"]).dt.strftime("%Y-%m-%d")
            df_to_save["Ticker"] = ticker
            
            # Load existing cache
            if os.path.exists(cache_file):
                try:
                    cache_df = pd.read_csv(cache_file)
                    if cache_df.empty or "Ticker" not in cache_df.columns:
                        # Corrupted cache - start fresh
                        cache_df = pd.DataFrame()
                    else:
                        # Remove old data for this ticker
                        cache_df = cache_df[cache_df["Ticker"] != ticker]
                except (pd.errors.EmptyDataError, pd.errors.ParserError, UnicodeDecodeError) as e:
                    logging.warning(f"Existing cache file {cache_file} is unreadable, rebuilding it: {e}")
                    cache_df = pd.DataFrame()
                except Exception as e:
                    logging.warning(f"Failed to read existing cache file {cache_file}, rebuilding it: {e}")
                    # Cache is corrupted - start fresh
                    cache_df = pd.DataFrame()
            else:
                cache_df = pd.DataFrame()
            
            # Append new data
            if not cache_df.empty:
                cache_df = pd.concat([cache_df, df_to_save], ignore_index=True)
            else:
                cache_df = df_to_save
            
            # Reorder columns to include OHLC data
            cols = ["Ticker", "Date", "Open", "High", "Low", "Close", "Adj_Close", "Volume"]
            if "Split" in cache_df.columns:
                cols.append("Split")
            cache_df = cache_df[[c for c in cols if c in cache_df.columns]]
            
            # Use atomic write: write to temp file first, then rename
            temp_file = cache_file + ".tmp"
            cache_df.to_csv(temp_file, index=False)
            # Atomic rename (overwrites destination)
            if os.path.exists(cache_file):
                os.remove(cache_file)
            os.rename(temp_file, cache_file)
    except Exception as e:
        logging.warning(f"Failed to save cache for {ticker}: {e}")
        # Clean up temp file if it exists
        try:
            temp_file = cache_file + ".tmp"
            if os.path.exists(temp_file):
                os.remove(temp_file)
        except Exception:
            pass

def load_full_cache(universe):
    """Load the entire price cache CSV into memory once."""
    cache_file = f"price_cache_{universe}.csv"
    if not os.path.exists(cache_file):
        return None
    try:
        cache_df = pd.read_csv(cache_file)
    except (pd.errors.EmptyDataError, pd.errors.ParserError, UnicodeDecodeError) as e:
        logging.warning(f"Full cache file {cache_file} is unreadable: {e}")
        return None
    except Exception as e:
        logging.warning(f"Failed to read full cache for {universe}: {e}")
        return None

    required_cols = {"Ticker", "Date"}
    if cache_df.empty or not required_cols.issubset(cache_df.columns):
        logging.warning(
            f"Full cache file {cache_file} missing required columns. "
            f"Expected {sorted(required_cols)}, found {sorted(cache_df.columns.tolist())}."
        )
        return None

    # Standardize column names for compatibility (rename old 'Adj Close' to 'Adj_Close')
    if "Adj Close" in cache_df.columns and "Adj_Close" not in cache_df.columns:
        cache_df = cache_df.rename(columns={"Adj Close": "Adj_Close"})
    return cache_df

def _lookup_ticker_in_cache(ticker, full_cache_df):
    """Look up a single ticker from an already-loaded cache DataFrame."""
    if full_cache_df is None or full_cache_df.empty:
        return None
    if "Ticker" not in full_cache_df.columns or "Date" not in full_cache_df.columns:
        return None
    ticker_data = full_cache_df[full_cache_df["Ticker"] == ticker].copy()
    if ticker_data.empty:
        return None
    ticker_data["Date"] = pd.to_datetime(ticker_data["Date"])
    ticker_data = ticker_data.sort_values("Date")
    ticker_data.set_index("Date", inplace=True)
    
    # Standardize column name for compatibility (rename old 'Adj Close' to 'Adj_Close')
    if "Adj Close" in ticker_data.columns and "Adj_Close" not in ticker_data.columns:
        ticker_data = ticker_data.rename(columns={"Adj Close": "Adj_Close"})
    
    ticker_data = ticker_data.drop(columns=["Ticker"], errors="ignore")
    return ticker_data

def save_cache_bulk(new_data, universe, existing_cache_df=None):
    """Save multiple tickers' price data to cache in a single write using atomic operation."""
    cache_file = f"price_cache_{universe}.csv"
    cache_lock = get_cache_lock(universe)
    
    try:
        with cache_lock:
            if existing_cache_df is not None and not existing_cache_df.empty:
                cache_df = existing_cache_df[~existing_cache_df["Ticker"].isin(new_data.keys())].copy()
            else:
                cache_df = pd.DataFrame()

            new_frames = []
            for ticker, df in new_data.items():
                df_to_save = df.reset_index()
                df_to_save["Date"] = pd.to_datetime(df_to_save["Date"]).dt.strftime("%Y-%m-%d")
                df_to_save["Ticker"] = ticker
                new_frames.append(df_to_save)

            if new_frames:
                new_df = pd.concat(new_frames, ignore_index=True)
                if not cache_df.empty:
                    cache_df = pd.concat([cache_df, new_df], ignore_index=True)
                else:
                    cache_df = new_df

            if cache_df.empty:
                return

            cols = ["Ticker", "Date", "Open", "High", "Low", "Close", "Adj_Close", "Volume"]
            if "Split" in cache_df.columns:
                cols.append("Split")
            cache_df = cache_df[[c for c in cols if c in cache_df.columns]]

            # Use atomic write: write to temp file first, then rename
            temp_file = cache_file + ".tmp"
            cache_df.to_csv(temp_file, index=False)
            # Atomic rename (overwrites destination)
            if os.path.exists(cache_file):
                os.remove(cache_file)
            os.rename(temp_file, cache_file)
    except Exception as e:
        logging.warning(f"Failed to save bulk cache: {e}")
        # Clean up temp file if it exists
        try:
            temp_file = cache_file + ".tmp"
            if os.path.exists(temp_file):
                os.remove(temp_file)
        except Exception:
            pass

def download_price_batch(tickers, retries=1, universe=None, use_cache=True, cache_df=None):
    """Download multiple tickers in a single batch call for efficiency.
    
    If a ticker fails (no data found), automatically retry with alternate exchange suffix:
    - tickers without suffix or with .NS will retry with .BO
    - tickers with .BO will retry with .NS
    """
    results = {}  # ticker -> DataFrame mapping
    
    # Try cache first for all tickers
    tickers_to_fetch = []
    for ticker in tickers:
        if use_cache:
            if cache_df is not None:
                cached = _lookup_ticker_in_cache(ticker, cache_df)
            elif universe:
                cached = load_price_df_from_cache(ticker, universe)
            else:
                cached = None
            if cached is not None and len(cached) >= 2:
                # Check for stale cache (older than 5 days)
                last_date = cached.index[-1]
                if (pd.Timestamp.now() - last_date).days < 5:
                    results[ticker] = cached
                    continue
                # If stale, fall through to fetch logic (treat as cache miss)
        tickers_to_fetch.append(ticker)
    
    if not tickers_to_fetch:
        return results
    
    tickers_needing_retry = set(tickers_to_fetch)  # Track tickers that need alternate suffix retry
    
    for attempt in range(retries + 1):
        try:
            # Download all tickers in batch (much faster than individual calls)
            raw = yf.download(
                tickers_to_fetch,
                period=LOOKBACK_PERIOD,
                interval="1d",
                actions=True,
                auto_adjust=False,
                progress=False,
                timeout=YF_DOWNLOAD_TIMEOUT_SECONDS,
            )
        except Exception as e:
            logging.warning(f"Batch download attempt {attempt} failed: {e}")
            continue
        
        if raw is None or raw.empty:
            logging.warning(f"Batch download returned empty result for attempt {attempt}")
            continue
        
        # Clear tickers that we're about to process (they don't need retry if they succeed)
        tickers_that_succeeded_this_attempt = set()
        
        # Process each ticker from the batch result
        for ticker in list(tickers_to_fetch):  # Use list() to avoid modification during iteration
            if ticker in results:
                tickers_needing_retry.discard(ticker)  # Don't retry if we already have it
                continue  # Skip tickers that already succeeded
                
            try:
                if len(tickers_to_fetch) == 1:
                    ticker_data = raw
                else:
                    # Multi-ticker batch: extract this ticker's columns
                    try:
                        ticker_data = raw[raw.columns[raw.columns.get_level_values(1) == ticker]]
                    except (KeyError, IndexError, AttributeError):
                        logging.debug(f"Failed to extract data for {ticker} from batch result")
                        continue
                    
                    if ticker_data.empty:
                        logging.debug(f"No data found for {ticker} in batch")
                        continue
                
                open_series, high_series, low_series, close_series, adj_close_series, volume_series, split_series = extract_series(ticker_data)
                if close_series is None:
                    logging.debug(f"Failed to extract OHLCV series for {ticker}")
                    continue
                
                df = build_price_df(open_series, high_series, low_series, close_series, adj_close_series, volume_series, split_series)
                if len(df) < 2:
                    logging.debug(f"Insufficient data for {ticker} (only {len(df)} rows)")
                    continue
                
                close = float(df["Close"].iloc[-1])
                prev_close = float(df["Close"].iloc[-2])
                adj_close = float(df["Adj_Close"].iloc[-1])
                prev_adj_close = float(df["Adj_Close"].iloc[-2])
                last_split = float(df["Split"].iloc[-1]) if "Split" in df else 0.0
                
                change_ratio = (
                    abs(adj_close - prev_adj_close) / prev_adj_close
                    if prev_adj_close > 0 else 0.0
                )
                
                if change_ratio > MAX_DAILY_MOVE and last_split == 0.0 and attempt < retries:
                    logging.debug(f"Large daily move detected for {ticker} ({change_ratio:.2%}), will retry")
                    continue
                
                # Note: Per-ticker cache saves are skipped because bulk saves happen
                # in run_screener after all batches complete. This avoids race conditions
                # from concurrent writes to the same cache file.
                
                results[ticker] = df
                tickers_that_succeeded_this_attempt.add(ticker)
                tickers_needing_retry.discard(ticker)  # Don't retry if we succeeded
            except Exception as e:
                logging.debug(f"Error processing ticker {ticker} in batch: {e}")
                continue
        
        # If we got all results, return them
        if not tickers_needing_retry or len(results) >= len(tickers_to_fetch):
            break
    
    # ===== RETRY LOGIC: Try alternate suffixes for failed tickers =====
    # If a ticker failed (no data), try with alternate exchange suffix
    # E.g., NSDL.NS -> retry as NSDL.BO, or vice versa
    if tickers_needing_retry and retries > 0:
        retries_with_alternates = []
        alternate_to_original = {}  # Maps alternate ticker to original ticker
        
        for ticker in tickers_needing_retry:
            alternate = None
            if ticker.endswith(".NS"):
                # Try with .BO instead
                alternate = ticker[:-3] + ".BO"
            elif ticker.endswith(".BO"):
                # Try with .NS instead
                alternate = ticker[:-3] + ".NS"
            else:
                # If no suffix, try .BO (BSE) as alternate
                alternate = ticker + ".BO"
            
            if alternate and alternate not in results:
                retries_with_alternates.append(alternate)
                alternate_to_original[alternate] = ticker  # Track mapping
                logging.debug(f"Will retry {ticker} as {alternate}")
        
        # Retry the alternate versions
        if retries_with_alternates:
            try:
                logging.info(f"Retrying {len(retries_with_alternates)} failed tickers with alternate exchange suffixes")
                alt_raw = yf.download(
                    retries_with_alternates,
                    period=LOOKBACK_PERIOD,
                    interval="1d",
                    actions=True,
                    auto_adjust=False,
                    progress=False,
                    timeout=YF_DOWNLOAD_TIMEOUT_SECONDS,
                )
                
                if alt_raw is not None and not alt_raw.empty:
                    # Process alternate ticker results
                    for alt_ticker in retries_with_alternates:
                        original_ticker = alternate_to_original.get(alt_ticker)
                        if original_ticker in results:
                            continue

                        try:
                            if len(retries_with_alternates) == 1:
                                ticker_data = alt_raw
                            else:
                                try:
                                    ticker_data = alt_raw[alt_raw.columns[alt_raw.columns.get_level_values(1) == alt_ticker]]
                                except (KeyError, IndexError, AttributeError):
                                    continue
                                
                                if ticker_data.empty:
                                    continue
                            
                            open_series, high_series, low_series, close_series, adj_close_series, volume_series, split_series = extract_series(ticker_data)
                            if close_series is None:
                                continue
                            
                            df = build_price_df(open_series, high_series, low_series, close_series, adj_close_series, volume_series, split_series)
                            if len(df) < 2:
                                continue
                            
                            # Store under ORIGINAL ticker name so run_screener can find it
                            original_ticker = alternate_to_original[alt_ticker]
                            results[original_ticker] = df
                            logging.info(f"Successfully fetched {original_ticker} using alternate suffix {alt_ticker}")
                        except Exception as e:
                            logging.debug(f"Alternate retry for {alt_ticker} also failed: {e}")
                            continue
            except Exception as e:
                logging.debug(f"Batch retry with alternate suffixes failed: {e}")
    
    # Log summary of still-failed tickers
    final_failed = tickers_needing_retry - set(results.keys())
    if final_failed:
        logging.debug(f"Still unable to fetch data for {len(final_failed)} tickers: {', '.join(sorted(final_failed)[:10])}")
    
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
                progress=False,
                timeout=YF_DOWNLOAD_TIMEOUT_SECONDS,
            )
        except Exception:
            continue

        if raw is None or raw.empty:
            continue

        open_series, high_series, low_series, close_series, adj_close_series, volume_series, split_series = extract_series(raw)
        if close_series is None:
            continue

        df = build_price_df(open_series, high_series, low_series, close_series, adj_close_series, volume_series, split_series)
        if len(df) < 2:
            continue

        close = float(df["Close"].iloc[-1])
        prev_close = float(df["Close"].iloc[-2])
        adj_close = float(df["Adj_Close"].iloc[-1])
        prev_adj_close = float(df["Adj_Close"].iloc[-2])
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

def load_universe_from_local_scan(which):
    """Fallback universe from latest scan CSV when NSE endpoint is unavailable."""
    fallback_file_map = {
        "nifty50": "latest_scan_nifty50.csv",
        "niftynext50": "latest_scan_niftynext50.csv",
    }
    fallback_file = fallback_file_map.get(which)
    if not fallback_file or not os.path.exists(fallback_file):
        return {}

    try:
        df = pd.read_csv(fallback_file)
    except Exception as e:
        logging.warning(f"Failed to read fallback universe file {fallback_file}: {e}")
        return {}

    if "Ticker" not in df.columns:
        logging.warning(f"Fallback universe file {fallback_file} is missing 'Ticker' column.")
        return {}

    symbols = {}
    if "Stock" in df.columns:
        rows = df.dropna(subset=["Ticker", "Stock"])
        for _, row in rows.iterrows():
            ticker = str(row["Ticker"]).strip().upper()
            if not ticker:
                continue
            if "." not in ticker:
                ticker = f"{ticker}.NS"
            stock_name = str(row["Stock"]).strip() or ticker
            symbols[stock_name] = ticker
    else:
        tickers = (
            df["Ticker"]
            .astype(str)
            .str.strip()
            .str.upper()
            .replace("", pd.NA)
            .dropna()
            .unique()
            .tolist()
        )
        for ticker in tickers:
            if "." not in ticker:
                ticker = f"{ticker}.NS"
            symbols[ticker] = ticker
    return symbols

def fetch_nse_universe(which):
    if which == "nifty50":
        url = "https://nsearchives.nseindia.com/content/indices/ind_nifty50list.csv"
    elif which == "niftynext50":
        url = "https://nsearchives.nseindia.com/content/indices/ind_niftynext50list.csv"
    else:
        raise ValueError("Invalid NSE universe")

    headers = {"User-Agent": "Mozilla/5.0"}
    session = requests.Session()
    retry = Retry(
        total=4,
        connect=4,
        read=4,
        backoff_factor=1.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=frozenset(["GET"]),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)

    try:
        r = session.get(url, headers=headers, timeout=(10, 45))
        r.raise_for_status()

        df = pd.read_csv(StringIO(r.text))
        if "Symbol" not in df.columns or "Company Name" not in df.columns:
            raise ValueError("NSE CSV missing expected columns.")

        symbols = {}
        for _, row in df.iterrows():
            sym = str(row["Symbol"]).strip().upper()
            name = row["Company Name"]
            # Filter out dummy/test tickers that don't have real data
            if sym in ("DUMMYHDLVR", "DUMMYBRLK"):
                logging.warning(f"Skipping test ticker: {sym}")
                continue
            symbols[name] = sym + ".NS"

        if symbols:
            return symbols
        raise ValueError("NSE CSV parsed but no symbols were found.")
    except (requests.exceptions.RequestException, ValueError, KeyError) as e:
        logging.warning(f"Failed to fetch NSE universe '{which}' from network: {e}")
        fallback_symbols = load_universe_from_local_scan(which)
        if fallback_symbols:
            logging.warning(
                f"Using local fallback universe from latest scan file for '{which}' "
                f"({len(fallback_symbols)} tickers)."
            )
            return fallback_symbols
        raise RuntimeError(
            f"Unable to fetch NSE universe '{which}' and no local fallback is available."
        ) from e
    finally:
        session.close()

def parse_universe(universe, custom_tickers):
    if universe == "nifty50":
        return fetch_nse_universe("nifty50")
    if universe == "niftynext50":
        return fetch_nse_universe("niftynext50")
    if universe == "custom":
        tickers = {}
        # Basic validation regex or check
        for t in custom_tickers.split(","):
            t = t.strip().upper()
            if not t:
                continue
            # Basic validation: ensure it looks like a ticker (alphanumeric + dot + suffix)
            if not re.match(r'^[A-Z0-9\.-]+$', t):
                logging.warning(f"Skipping invalid custom ticker: {t}")
                continue
            
            # If ticker already has .NS or .BO suffix, use it as-is
            if t.endswith(".NS") or t.endswith(".BO"):
                tickers[t] = t
            else:
                # Default to .NS (NSE), but will auto-retry with .BO (BSE) if not found
                tickers[t] = t + ".NS"
                logging.debug(f"Added custom ticker: {t} (will try as {t}.NS, then .BO if needed)")
        if not tickers:
            logging.error("No valid custom tickers found.")
        return tickers
    raise ValueError("Invalid universe")

# ---------------- MAIN SCREENER ----------------

def _process_ticker(name, ticker, df, universe, prev_close_map):
    """Process a single ticker with its price DataFrame and return results if applicable"""
    if df is None:
        return None
    
    # For custom universe stocks, be more lenient with data requirements (e.g., newly listed stocks, BSE stocks)
    # For indices (nifty50, niftynext50), require at least 200 days of data
    min_data_points = 50 if universe == "custom" else 200
    
    if len(df) < min_data_points:
        logging.debug(f"Insufficient data for {ticker}: {len(df)} records (minimum {min_data_points} required)")
        return None

    df = df.copy()  # Work on a copy to avoid mutating the caller's DataFrame
    
    # Standardize column names for compatibility (rename old 'Adj Close' to 'Adj_Close')
    if "Adj Close" in df.columns and "Adj_Close" not in df.columns:
        df = df.rename(columns={"Adj Close": "Adj_Close"})
    
    # Debug: check what columns we have
    if "Adj_Close" not in df.columns:
        logging.error(f"Missing 'Adj_Close' column for {ticker}. Available columns: {list(df.columns)}")
        return None

    if prev_close_map and ticker in prev_close_map:
        prev_close_csv = float(prev_close_map[ticker])
        last_split = float(df["Split"].iloc[-1]) if "Split" in df.columns else 0.0
        if prev_close_csv > 0:
            change_ratio_csv = abs(float(df["Adj_Close"].iloc[-1]) - prev_close_csv) / prev_close_csv
            if change_ratio_csv > MAX_DAILY_MOVE and last_split == 0.0:
                df_retry = download_price_df(ticker, retries=0, universe=universe, use_cache=False)
                if df_retry is None:
                    return None
                df = df_retry

    raw_close = pd.to_numeric(df["Close"], errors="coerce").dropna()
    if len(raw_close) < 2:
        return None
    lookback_points = min(252, len(raw_close))
    first_price = float(raw_close.iloc[-lookback_points])
    if first_price <= 0:
        return None

    df["RSI"] = compute_rsi(df["Close"])
    
    # For stocks with insufficient data, use available period for moving averages
    dma50_period = min(50, len(df))
    dma200_period = min(200, len(df))
    
    df["50DMA"] = df["Close"].rolling(dma50_period).mean()
    df["200DMA"] = df["Close"].rolling(dma200_period).mean()
    df["MACD"], df["Signal"], df["Hist"] = compute_macd(df["Close"])
    df["AvgVol20"] = df["Volume"].rolling(20).mean()

    if len(df) < 2:
        return None

    latest = df.iloc[-1]
    prev = df.iloc[-2]

    required_latest = ["Close", "Adj_Close", "RSI", "50DMA", "200DMA", "Volume", "AvgVol20", "Hist"]
    if any(pd.isna(latest[col]) for col in required_latest):
        logging.debug(f"Latest row has incomplete indicator data for {ticker}")
        return None
    if pd.isna(prev["Hist"]):
        return None

    close = float(latest["Close"])
    adj_close = float(latest["Adj_Close"])
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

    # Classify action — more specific conditions checked first to prevent shadowing
    
    # Momentum helpers
    momentum_improving = latest["Hist"] > prev["Hist"]
    momentum_weakening = latest["Hist"] < prev["Hist"]

    if is_oversold:
        # OVERSOLD already checks momentum in is_oversold definition (line 475)
        action = "OVERSOLD"
    elif (close > dma50 > dma200) and (rsi > RSI_OVERBOUGHT) and momentum_weakening:
        action = "SELL"
    elif (close < dma50 < dma200) and (rsi < RSI_ATTRACTIVE) and momentum_improving:
        action = "CONTRA BUY"
    elif (close > dma200) and (rsi < RSI_ATTRACTIVE) and momentum_improving:
        action = "BUY"
    elif (close < dma200) and (rsi > RSI_ATTRACTIVE) and momentum_weakening:
        action = "EXIT"
    elif (close > dma50 > dma200) and momentum_improving:
        action = "BUILD"
    elif (close < dma50 < dma200) and momentum_weakening:
        action = "SHORT"
    else:
        action = "HOLD"

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
    ticker_symbols = list(tickers_dict.values())
    symbol_to_name = {symbol: name for name, symbol in tickers_dict.items()}

    if strategy == "contra":
        priority = ["OVERSOLD", "CONTRA BUY", "BUY", "BUILD", "SELL", "EXIT", "SHORT", "HOLD"]
    else:
        priority = ["SELL", "EXIT", "SHORT", "OVERSOLD", "CONTRA BUY", "BUY", "BUILD", "HOLD"]

    results = []
    all_price_data = {}  # Collect all DataFrames for bulk cache save

    # Load price cache once for efficient lookups
    cache_df = load_full_cache(universe)

    # Create batches of tickers for efficient downloading
    batches = [ticker_symbols[i:i + batch_size] for i in range(0, len(ticker_symbols), batch_size)]

    # Use ThreadPoolExecutor for parallel batch downloads
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit batch download tasks
        futures = {
            executor.submit(download_price_batch, batch, 1, universe, True, cache_df): idx
            for idx, batch in enumerate(batches)
        }

        # Collect results as batches complete
        for future in as_completed(futures):
            try:
                batch_results = future.result()
                for ticker_symbol, df in batch_results.items():
                    all_price_data[ticker_symbol] = df
                    name = symbol_to_name.get(ticker_symbol, ticker_symbol)
                    result = _process_ticker(name, ticker_symbol, df, universe, prev_close_map)
                    if result:
                        results.append(result)
            except Exception as e:
                import traceback
                logging.error(f"Error processing batch result: {e}")
                logging.error(traceback.format_exc())
                continue

    # Bulk save all price data to cache (single write instead of per-ticker)
    if universe and all_price_data:
        try:
            save_cache_bulk(all_price_data, universe, cache_df)
        except Exception as e:
            logging.warning(f"Failed to save bulk cache in run_screener: {e}")
            pass

    df_out = pd.DataFrame(results, columns=[
        "Stock", "Ticker", "Close", "Adj_Close", "RSI", "Vol_Spike", "Action", "1Y_Return_%"
    ])

    if df_out.empty:
        return df_out

    df_out["Rank"] = df_out["Action"].apply(
        lambda x: priority.index(x) + 1 if x in priority else 99
    )

    df_out = df_out.sort_values(["Rank", "RSI"]).reset_index(drop=True)

    return df_out
