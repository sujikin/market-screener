from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd

from app_utils import is_valid_ticker, normalize_ticker, validate_scan_dataframe
from services.models import MissingConstituent, UniverseSnapshot


UNIVERSE_LABELS = {
    "nifty50": "Nifty 50",
    "niftynext50": "Nifty Next 50",
}

SNAPSHOT_FILE_MAP = {
    "nifty50": "latest_scan_nifty50.csv",
    "niftynext50": "latest_scan_niftynext50.csv",
}

CACHE_FILE_MAP = {
    "nifty50": "price_cache_nifty50.csv",
    "niftynext50": "price_cache_niftynext50.csv",
}

META_FILE_MAP = {
    "nifty50": "snapshot_meta_nifty50.json",
    "niftynext50": "snapshot_meta_niftynext50.json",
}


def _coerce_base_path(base_path: str | Path = ".") -> Path:
    return Path(base_path)


def _normalize_ticker(value: str) -> str:
    return normalize_ticker(value)


def _sanitize_ticker_frame(df: pd.DataFrame, ticker_column: str = "Ticker") -> pd.DataFrame:
    if df.empty or ticker_column not in df.columns:
        return df.copy()

    cleaned = df.copy()
    cleaned[ticker_column] = cleaned[ticker_column].map(_normalize_ticker)
    return cleaned.loc[cleaned[ticker_column].map(is_valid_ticker)].copy()


def _sanitize_constituent_map(constituent_map: dict[str, str] | None) -> dict[str, str] | None:
    if not constituent_map:
        return None

    cleaned = {}
    for stock, ticker in constituent_map.items():
        normalized = _normalize_ticker(ticker)
        if not is_valid_ticker(normalized):
            continue
        stock_name = str(stock).strip() or normalized
        cleaned[stock_name] = normalized
    return cleaned or None


def _sanitize_missing_constituent_items(items: list[dict] | None) -> list[dict]:
    cleaned = []
    for item in items or []:
        ticker = _normalize_ticker(item.get("ticker", ""))
        if not is_valid_ticker(ticker):
            continue
        cleaned.append(
            {
                "ticker": ticker,
                "stock": str(item.get("stock", "")).strip() or ticker,
                "reason": str(item.get("reason", "screening_failed")),
                "history_days": int(item.get("history_days", 0)),
            }
        )
    return cleaned


def _metadata_needs_refresh(metadata: dict | None, scan_df: pd.DataFrame) -> bool:
    if metadata is None:
        return True

    clean_missing = _sanitize_missing_constituent_items(metadata.get("missing_constituents", []))
    if len(clean_missing) != len(metadata.get("missing_constituents", [])):
        return True

    expected_screened = int(len(scan_df))
    expected_constituents = expected_screened + len(clean_missing)
    if int(metadata.get("screened_count", expected_screened)) != expected_screened:
        return True
    if int(metadata.get("constituent_count", expected_constituents)) != expected_constituents:
        return True
    return False


def _min_history_days(universe_key: str) -> int:
    return 50 if universe_key == "custom" else 200


def _snapshot_path(universe_key: str, base_path: str | Path = ".") -> Path:
    return _coerce_base_path(base_path) / SNAPSHOT_FILE_MAP[universe_key]


def _cache_path(universe_key: str, base_path: str | Path = ".") -> Path:
    return _coerce_base_path(base_path) / CACHE_FILE_MAP[universe_key]


def _meta_path(universe_key: str, base_path: str | Path = ".") -> Path:
    return _coerce_base_path(base_path) / META_FILE_MAP[universe_key]


def load_scan_df(universe_key: str, base_path: str | Path = ".") -> pd.DataFrame:
    path = _snapshot_path(universe_key, base_path)
    if not path.exists():
        raise FileNotFoundError(f"Snapshot file not found: {path}")

    df = pd.read_csv(path)
    ok, missing = validate_scan_dataframe(df)
    if not ok:
        raise ValueError(f"Snapshot file {path} missing required columns: {', '.join(missing)}")
    return _sanitize_ticker_frame(df)


def load_cache_df(universe_key: str, base_path: str | Path = ".") -> pd.DataFrame:
    path = _cache_path(universe_key, base_path)
    if not path.exists():
        return pd.DataFrame()

    df = pd.read_csv(path)
    if "Adj Close" in df.columns and "Adj_Close" not in df.columns:
        df = df.rename(columns={"Adj Close": "Adj_Close"})
    if "Date" in df.columns:
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    return _sanitize_ticker_frame(df)


def load_grouped_cache(universe_key: str, base_path: str | Path = ".") -> dict[str, pd.DataFrame]:
    cache_df = load_cache_df(universe_key, base_path)
    if cache_df.empty or "Ticker" not in cache_df.columns or "Date" not in cache_df.columns:
        return {}

    grouped = {}
    for ticker, ticker_df in cache_df.groupby("Ticker"):
        ticker_df = ticker_df.copy().sort_values("Date").set_index("Date")
        grouped[_normalize_ticker(ticker)] = ticker_df.drop(columns=["Ticker"], errors="ignore")
    return grouped


def build_market_data_date(cache_df: pd.DataFrame) -> date | None:
    if cache_df.empty or "Date" not in cache_df.columns:
        return None
    valid_dates = pd.to_datetime(cache_df["Date"], errors="coerce").dropna()
    if valid_dates.empty:
        return None
    return valid_dates.max().date()


def _history_days_by_ticker(cache_df: pd.DataFrame) -> dict[str, int]:
    cache_df = _sanitize_ticker_frame(cache_df)
    if cache_df.empty or "Ticker" not in cache_df.columns:
        return {}
    history = cache_df.groupby("Ticker").size()
    return {_normalize_ticker(ticker): int(count) for ticker, count in history.items()}


def _derive_missing_reason(history_days: int, min_history_days: int) -> str:
    if history_days <= 0:
        return "missing_cache_data"
    if history_days < min_history_days:
        return "insufficient_history"
    return "screening_failed"


def build_missing_constituents(
    universe_key: str,
    scan_df: pd.DataFrame,
    cache_df: pd.DataFrame,
    constituent_map: dict[str, str] | None = None,
) -> list[dict]:
    scan_df = _sanitize_ticker_frame(scan_df)
    cache_df = _sanitize_ticker_frame(cache_df)
    constituent_map = _sanitize_constituent_map(constituent_map)

    scan_tickers = set()
    if "Ticker" in scan_df.columns:
        scan_tickers = {_normalize_ticker(ticker) for ticker in scan_df["Ticker"].dropna().tolist()}

    if constituent_map:
        ticker_to_stock = {
            _normalize_ticker(ticker): str(stock).strip()
            for stock, ticker in constituent_map.items()
            if str(ticker).strip()
        }
        constituent_tickers = set(ticker_to_stock.keys())
    elif not cache_df.empty and "Ticker" in cache_df.columns:
        constituent_tickers = {_normalize_ticker(ticker) for ticker in cache_df["Ticker"].dropna().tolist()}
        ticker_to_stock = {ticker: ticker for ticker in constituent_tickers}
    else:
        constituent_tickers = scan_tickers
        ticker_to_stock = {ticker: ticker for ticker in constituent_tickers}

    history_map = _history_days_by_ticker(cache_df)
    min_history_days = _min_history_days(universe_key)

    missing = []
    for ticker in sorted(constituent_tickers - scan_tickers):
        history_days = history_map.get(ticker, 0)
        missing.append(
            {
                "ticker": ticker,
                "stock": ticker_to_stock.get(ticker, ticker),
                "reason": _derive_missing_reason(history_days, min_history_days),
                "history_days": history_days,
            }
        )
    return missing


def build_snapshot_meta(
    universe_key: str,
    scan_df: pd.DataFrame,
    cache_df: pd.DataFrame,
    constituent_map: dict[str, str] | None = None,
    generated_at: datetime | None = None,
) -> dict:
    scan_df = _sanitize_ticker_frame(scan_df)
    cache_df = _sanitize_ticker_frame(cache_df)
    constituent_map = _sanitize_constituent_map(constituent_map)

    if generated_at is None:
        generated_at = datetime.now(timezone.utc)

    if generated_at.tzinfo is None:
        generated_at = generated_at.replace(tzinfo=timezone.utc)

    missing_constituents = build_missing_constituents(
        universe_key,
        scan_df,
        cache_df,
        constituent_map=constituent_map,
    )

    if constituent_map:
        constituent_count = len(
            {_normalize_ticker(ticker) for ticker in constituent_map.values() if str(ticker).strip()}
        )
    elif not cache_df.empty and "Ticker" in cache_df.columns:
        constituent_count = int(cache_df["Ticker"].astype(str).str.strip().str.upper().nunique())
    elif "Ticker" in scan_df.columns:
        constituent_count = int(scan_df["Ticker"].astype(str).str.strip().str.upper().nunique())
    else:
        constituent_count = 0

    action_counts = {}
    if "Action" in scan_df.columns:
        action_counts = {str(action): int(count) for action, count in scan_df["Action"].value_counts().items()}

    market_data_date = build_market_data_date(cache_df)

    return {
        "version": 1,
        "universe_key": universe_key,
        "universe_label": UNIVERSE_LABELS.get(universe_key, universe_key),
        "mode": "snapshot",
        "generated_at": generated_at.isoformat(),
        "market_data_date": market_data_date.isoformat() if market_data_date else None,
        "screened_count": int(len(scan_df)),
        "constituent_count": int(constituent_count),
        "action_counts": action_counts,
        "missing_constituents": missing_constituents,
    }


def write_snapshot_meta(universe_key: str, metadata: dict, base_path: str | Path = ".") -> Path:
    path = _meta_path(universe_key, base_path)
    path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return path


def load_snapshot_meta(universe_key: str, base_path: str | Path = ".") -> dict | None:
    path = _meta_path(universe_key, base_path)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value)


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    return date.fromisoformat(value)


def _is_snapshot_stale(market_data_date: date | None, reference_date: date | None = None) -> bool:
    if market_data_date is None:
        return True
    if reference_date is None:
        reference_date = date.today()
    return (reference_date - market_data_date).days > 3


def load_index_snapshot(universe_key: str, base_path: str | Path = ".") -> UniverseSnapshot:
    scan_df = load_scan_df(universe_key, base_path)
    cache_df = load_cache_df(universe_key, base_path)
    metadata = load_snapshot_meta(universe_key, base_path)
    if _metadata_needs_refresh(metadata, scan_df):
        metadata = build_snapshot_meta(universe_key, scan_df, cache_df)

    missing_constituents = [
        MissingConstituent(
            ticker=item["ticker"],
            stock=item["stock"],
            reason=item["reason"],
            history_days=int(item.get("history_days", 0)),
        )
        for item in _sanitize_missing_constituent_items(metadata.get("missing_constituents", []))
    ]

    constituent_map = {
        str(row["Stock"]).strip(): _normalize_ticker(row["Ticker"])
        for _, row in scan_df[["Stock", "Ticker"]].iterrows()
    }
    for item in missing_constituents:
        constituent_map.setdefault(item.stock, item.ticker)

    market_data_date = _parse_date(metadata.get("market_data_date"))
    return UniverseSnapshot(
        universe_key=universe_key,
        universe_label=metadata.get("universe_label", UNIVERSE_LABELS.get(universe_key, universe_key)),
        mode=metadata.get("mode", "snapshot"),
        generated_at=_parse_datetime(metadata.get("generated_at")),
        market_data_date=market_data_date,
        screened_df=scan_df,
        constituent_map=constituent_map,
        coverage_count=int(metadata.get("screened_count", len(scan_df))),
        constituent_count=int(metadata.get("constituent_count", len(constituent_map))),
        missing_constituents=missing_constituents,
        action_counts={str(key): int(value) for key, value in metadata.get("action_counts", {}).items()},
        is_stale=_is_snapshot_stale(market_data_date),
    )
