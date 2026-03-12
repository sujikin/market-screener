from __future__ import annotations

from functools import lru_cache

import pandas as pd
import yfinance as yf


def _numeric_series(frame: pd.DataFrame | None, aliases: list[str]) -> pd.Series:
    if frame is None or frame.empty:
        return pd.Series(dtype=float)
    for alias in aliases:
        if alias in frame.index:
            series = pd.to_numeric(frame.loc[alias], errors="coerce").dropna()
            if not series.empty:
                return series.sort_index(ascending=False)
    return pd.Series(dtype=float)


def _value_at(series: pd.Series, index: int) -> float | None:
    if len(series) <= index:
        return None
    value = series.iloc[index]
    if pd.isna(value):
        return None
    return float(value)


def _ratio_percent(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None or denominator == 0:
        return None
    return (numerator / denominator) * 100


def _growth_percent(current: float | None, previous: float | None) -> float | None:
    if current is None or previous is None or previous == 0:
        return None
    return ((current - previous) / abs(previous)) * 100


def _average_non_null(current: float | None, previous: float | None) -> float | None:
    values = [value for value in [current, previous] if value is not None]
    if not values:
        return None
    return sum(values) / len(values)


def build_experimental_fundamentals_from_frames(
    income_stmt: pd.DataFrame | None,
    balance_sheet: pd.DataFrame | None,
) -> tuple[dict[str, object], str]:
    net_income_series = _numeric_series(
        income_stmt,
        [
            "Net Income Common Stockholders",
            "Net Income From Continuing Operation Net Minority Interest",
            "Net Income",
        ],
    )
    revenue_series = _numeric_series(income_stmt, ["Total Revenue", "Operating Revenue"])
    operating_income_series = _numeric_series(income_stmt, ["Operating Income", "EBIT"])
    ebit_series = _numeric_series(income_stmt, ["EBIT", "Operating Income"])

    equity_series = _numeric_series(
        balance_sheet,
        ["Stockholders Equity", "Total Equity Gross Minority Interest"],
    )
    debt_series = _numeric_series(balance_sheet, ["Total Debt"])
    invested_capital_series = _numeric_series(balance_sheet, ["Invested Capital"])
    current_assets_series = _numeric_series(balance_sheet, ["Current Assets"])
    current_liabilities_series = _numeric_series(balance_sheet, ["Current Liabilities"])

    net_income_current = _value_at(net_income_series, 0)
    net_income_previous = _value_at(net_income_series, 1)
    revenue_current = _value_at(revenue_series, 0)
    revenue_previous = _value_at(revenue_series, 1)
    operating_income_current = _value_at(operating_income_series, 0)
    ebit_current = _value_at(ebit_series, 0)
    equity_current = _value_at(equity_series, 0)
    equity_previous = _value_at(equity_series, 1)
    total_debt_current = _value_at(debt_series, 0)

    invested_capital_current = _value_at(invested_capital_series, 0)
    invested_capital_previous = _value_at(invested_capital_series, 1)

    if invested_capital_current is None and equity_current is not None:
        invested_capital_current = equity_current + (total_debt_current or 0)
    if invested_capital_previous is None and equity_previous is not None:
        debt_previous = _value_at(debt_series, 1) or 0
        invested_capital_previous = equity_previous + debt_previous

    if invested_capital_current is None:
        current_assets = _value_at(current_assets_series, 0)
        current_liabilities = _value_at(current_liabilities_series, 0)
        if current_assets is not None and current_liabilities is not None:
            invested_capital_current = current_assets - current_liabilities

    if invested_capital_previous is None:
        prev_assets = _value_at(current_assets_series, 1)
        prev_liabilities = _value_at(current_liabilities_series, 1)
        if prev_assets is not None and prev_liabilities is not None:
            invested_capital_previous = prev_assets - prev_liabilities

    avg_equity = _average_non_null(equity_current, equity_previous)
    avg_capital_employed = _average_non_null(invested_capital_current, invested_capital_previous)

    metrics = {
        "ROE": _ratio_percent(net_income_current, avg_equity),
        "ROCE": _ratio_percent(ebit_current, avg_capital_employed),
        "Debt / Equity": (total_debt_current / equity_current) if total_debt_current is not None and equity_current not in (None, 0) else None,
        "Operating Margin": _ratio_percent(operating_income_current, revenue_current),
        "Sales Growth": _growth_percent(revenue_current, revenue_previous),
        "Profit Growth": _growth_percent(net_income_current, net_income_previous),
    }

    as_of = ""
    if not net_income_series.empty:
        latest_column = net_income_series.index[0]
        if hasattr(latest_column, "date"):
            as_of = str(latest_column.date())
        else:
            as_of = str(latest_column)

    non_null_metrics = sum(value is not None for value in metrics.values())
    if non_null_metrics == 0:
        status = "Experimental fundamentals via yfinance are unavailable for this ticker right now."
    else:
        status = (
            "Experimental fundamentals via yfinance / Yahoo annual statements."
            + (f" As of {as_of}." if as_of else "")
            + " ROE uses net income over average equity; ROCE uses EBIT over average capital employed."
        )

    return metrics, status


@lru_cache(maxsize=256)
def fetch_experimental_fundamentals(ticker: str) -> tuple[dict[str, object], str]:
    normalized = str(ticker).strip().upper()
    if not normalized:
        return {}, "Experimental fundamentals are unavailable because no ticker was provided."

    try:
        yf_ticker = yf.Ticker(normalized)
        income_stmt = yf_ticker.income_stmt
        balance_sheet = yf_ticker.balance_sheet
        return build_experimental_fundamentals_from_frames(income_stmt, balance_sheet)
    except Exception as exc:
        return {}, f"Experimental fundamentals via yfinance failed: {exc}"
