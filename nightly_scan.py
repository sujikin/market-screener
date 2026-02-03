from screener import run_screener
from datetime import date
import pandas as pd

print("Starting nightly market scans...")

# -------- NIFTY50 --------
df_nifty50 = run_screener(
    strategy="contra",
    universe="nifty50",
    custom_tickers="",
    cache_day=date.today()
)

df_nifty50.to_csv("latest_scan_nifty50.csv", index=False)
print("Saved latest_scan_nifty50.csv")

# -------- NIFTYNEXT50 --------
df_niftynext50 = run_screener(
    strategy="contra",
    universe="niftynext50",
    custom_tickers="",
    cache_day=date.today()
)

df_niftynext50.to_csv("latest_scan_niftynext50.csv", index=False)
print("Saved latest_scan_niftynext50.csv")

print("All scans completed.")
