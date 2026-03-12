import re

import pandas as pd


REQUIRED_SCAN_COLUMNS = ("Stock", "Ticker")
INVALID_TICKER_VALUES = {"", "NAN", "NONE", "NULL", "N/A"}
MERGE_MARKER_PREFIXES = ("<<<<<<<", "=======", ">>>>>>>")
VALID_TICKER_RE = re.compile(r"^[A-Z0-9][A-Z0-9&.\-]*(?:\.(?:NS|BO))?$")


def validate_scan_dataframe(df: pd.DataFrame):
    missing = [col for col in REQUIRED_SCAN_COLUMNS if col not in df.columns]
    return len(missing) == 0, missing


def normalize_ticker(value) -> str:
    return str(value).strip().upper()


def is_valid_ticker(value) -> bool:
    ticker = normalize_ticker(value)
    if ticker in INVALID_TICKER_VALUES:
        return False
    if any(ticker.startswith(prefix) for prefix in MERGE_MARKER_PREFIXES):
        return False
    return bool(VALID_TICKER_RE.fullmatch(ticker))
