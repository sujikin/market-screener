from screener import run_screener
import pandas as pd
import os

def load_prev_close_map(filename):
    if not os.path.exists(filename):
        return {}
    try:
        df_prev = pd.read_csv(filename)
    except Exception:
        return {}
    if "Ticker" not in df_prev.columns:
        return {}
    if "Adj_Close" in df_prev.columns:
        df_prev = df_prev.dropna(subset=["Ticker", "Adj_Close"])
        return dict(zip(df_prev["Ticker"].astype(str), df_prev["Adj_Close"].astype(float)))
    if "Close" not in df_prev.columns:
        return {}
    df_prev = df_prev.dropna(subset=["Ticker", "Close"])
    return dict(zip(df_prev["Ticker"].astype(str), df_prev["Close"].astype(float)))

def main():
    print("Starting nightly market scans...")

    # -------- NIFTY50 --------
    print("Processing NIFTY50...")
    prev_close_nifty50 = load_prev_close_map("latest_scan_nifty50.csv")
    df_nifty50 = run_screener(
        strategy="contra",
        universe="nifty50",
        custom_tickers="",
        prev_close_map=prev_close_nifty50
    )

    df_nifty50.to_csv("latest_scan_nifty50.csv", index=False)
    print(f"Saved latest_scan_nifty50.csv ({len(df_nifty50)} stocks)")
    print("Price cache updated at price_cache_nifty50.csv")

    # -------- NIFTYNEXT50 --------
    print("Processing NIFTYNEXT50...")
    prev_close_niftynext50 = load_prev_close_map("latest_scan_niftynext50.csv")
    df_niftynext50 = run_screener(
        strategy="contra",
        universe="niftynext50",
        custom_tickers="",
        prev_close_map=prev_close_niftynext50
    )

    df_niftynext50.to_csv("latest_scan_niftynext50.csv", index=False)
    print(f"Saved latest_scan_niftynext50.csv ({len(df_niftynext50)} stocks)")
    print("Price cache updated at price_cache_niftynext50.csv")

    # -------- NIFTY500 --------
    print("Processing NIFTY500...")
    prev_close_nifty500 = load_prev_close_map("latest_scan_nifty500.csv")
    df_nifty500 = run_screener(
        strategy="contra",
        universe="nifty500",
        custom_tickers="",
        prev_close_map=prev_close_nifty500
    )

    df_nifty500.to_csv("latest_scan_nifty500.csv", index=False)
    print(f"Saved latest_scan_nifty500.csv ({len(df_nifty500)} stocks)")
    print("Price cache updated at price_cache_nifty500.csv")

    print("All scans completed.")


if __name__ == "__main__":
    main()
