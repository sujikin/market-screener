import pandas as pd


REQUIRED_SCAN_COLUMNS = ("Stock", "Ticker")


def validate_scan_dataframe(df: pd.DataFrame):
    missing = [col for col in REQUIRED_SCAN_COLUMNS if col not in df.columns]
    return len(missing) == 0, missing
