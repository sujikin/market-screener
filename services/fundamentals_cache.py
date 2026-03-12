from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from services.fundamentals_provider import fetch_experimental_fundamentals


FUNDAMENTALS_CACHE_FILE_MAP = {
    "nifty50": "fundamentals_cache_nifty50.json",
    "niftynext50": "fundamentals_cache_niftynext50.json",
}


def _coerce_base_path(base_path: str | Path = ".") -> Path:
    return Path(base_path)


def _cache_path(universe_key: str, base_path: str | Path = ".") -> Path:
    return _coerce_base_path(base_path) / FUNDAMENTALS_CACHE_FILE_MAP[universe_key]


def build_fundamentals_cache(
    universe_key: str,
    tickers: list[str],
    *,
    max_workers: int = 6,
) -> dict[str, object]:
    normalized_tickers = sorted({str(ticker).strip().upper() for ticker in tickers if str(ticker).strip()})
    entries: dict[str, dict[str, object]] = {}

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(fetch_experimental_fundamentals, ticker): ticker
            for ticker in normalized_tickers
        }
        for future in as_completed(futures):
            ticker = futures[future]
            try:
                metrics, status = future.result()
            except Exception as exc:
                metrics, status = {}, f"Experimental fundamentals cache generation failed: {exc}"
            entries[ticker] = {
                "metrics": metrics,
                "status": status,
            }

    return {
        "version": 1,
        "universe_key": universe_key,
        "provider": "yfinance_experimental",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "tickers": entries,
    }


def write_fundamentals_cache(
    universe_key: str,
    payload: dict[str, object],
    base_path: str | Path = ".",
) -> Path:
    path = _cache_path(universe_key, base_path)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def load_fundamentals_cache(universe_key: str, base_path: str | Path = ".") -> dict[str, object]:
    path = _cache_path(universe_key, base_path)
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def get_fundamentals_payload_for_ticker(
    cache_payload: dict[str, object] | None,
    ticker: str,
) -> tuple[dict[str, object], str]:
    if not cache_payload:
        return {}, "Nightly fundamentals cache is unavailable for this universe."

    tickers = cache_payload.get("tickers", {})
    if not isinstance(tickers, dict):
        return {}, "Nightly fundamentals cache is unreadable."

    entry = tickers.get(str(ticker).strip().upper(), {})
    if not isinstance(entry, dict):
        return {}, "Nightly fundamentals cache entry is unreadable."

    metrics = entry.get("metrics", {})
    if not isinstance(metrics, dict):
        metrics = {}

    status = str(entry.get("status", "")).strip()
    if not status:
        status = "Nightly fundamentals cache did not include a status message."
    return metrics, status
