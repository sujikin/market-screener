from __future__ import annotations

from datetime import date

import pandas as pd

from screener import RSI_ATTRACTIVE, RSI_OVERBOUGHT, compute_macd, compute_rsi
from services.models import DetailView
from services.presentation import action_description, action_family_for


def _safe_float(value) -> float | None:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if pd.isna(numeric):
        return None
    return numeric


def _coerce_history(hist: pd.DataFrame | None) -> pd.DataFrame:
    if hist is None or hist.empty:
        return pd.DataFrame()
    df = hist.copy()
    if "Close" not in df.columns:
        return pd.DataFrame()
    if not isinstance(df.index, pd.DatetimeIndex):
        if "Date" in df.columns:
            df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
            df = df.dropna(subset=["Date"]).set_index("Date")
        else:
            return pd.DataFrame()
    df = df.sort_index()
    df["Close"] = pd.to_numeric(df["Close"], errors="coerce")
    if "Adj_Close" in df.columns:
        df["Adj_Close"] = pd.to_numeric(df["Adj_Close"], errors="coerce")
    if "Volume" in df.columns:
        df["Volume"] = pd.to_numeric(df["Volume"], errors="coerce")
    return df.dropna(subset=["Close"])


def analyze_price_history(hist: pd.DataFrame | None) -> dict[str, object]:
    df = _coerce_history(hist)
    if df.empty:
        return {}

    close = df["Close"]
    volume = pd.to_numeric(df.get("Volume"), errors="coerce") if "Volume" in df.columns else None
    adj_close = pd.to_numeric(df.get("Adj_Close"), errors="coerce") if "Adj_Close" in df.columns else close

    df["RSI"] = compute_rsi(close)
    df["DMA50"] = close.rolling(min(50, len(df))).mean()
    df["DMA200"] = close.rolling(min(200, len(df))).mean()
    _, _, hist_series = compute_macd(close)
    df["MACD_HIST"] = hist_series
    if volume is not None:
        df["AVG_VOL_20"] = volume.rolling(20).mean()

    latest = df.iloc[-1]
    prev = df.iloc[-2] if len(df) > 1 else latest

    lookback_points = min(252, len(df))
    first_price = _safe_float(adj_close.iloc[-lookback_points]) if lookback_points else None
    current_price = _safe_float(latest["Close"])
    return_1y = None
    if first_price and current_price is not None and first_price > 0:
        return_1y = ((current_price - first_price) / first_price) * 100

    volume_ratio = None
    if "AVG_VOL_20" in df.columns:
        avg_vol = _safe_float(latest["AVG_VOL_20"])
        current_vol = _safe_float(latest.get("Volume"))
        if avg_vol and current_vol is not None and avg_vol > 0:
            volume_ratio = current_vol / avg_vol

    latest_date = latest.name.date() if isinstance(latest.name, pd.Timestamp) else None
    return {
        "close": current_price,
        "rsi": _safe_float(latest.get("RSI")),
        "volume_ratio": volume_ratio,
        "return_1y": return_1y,
        "history_days": int(len(df)),
        "data_date": latest_date if isinstance(latest_date, date) else None,
        "dma50": _safe_float(latest.get("DMA50")),
        "dma200": _safe_float(latest.get("DMA200")),
        "momentum_improving": _safe_float(latest.get("MACD_HIST")) is not None
        and _safe_float(prev.get("MACD_HIST")) is not None
        and float(latest["MACD_HIST"]) > float(prev["MACD_HIST"]),
        "momentum_weakening": _safe_float(latest.get("MACD_HIST")) is not None
        and _safe_float(prev.get("MACD_HIST")) is not None
        and float(latest["MACD_HIST"]) < float(prev["MACD_HIST"]),
    }


def build_factor_chips(action: str, metrics: dict[str, object]) -> list[str]:
    chips: list[str] = []
    rsi = _safe_float(metrics.get("rsi"))
    close = _safe_float(metrics.get("close"))
    dma50 = _safe_float(metrics.get("dma50"))
    dma200 = _safe_float(metrics.get("dma200"))
    volume_ratio = _safe_float(metrics.get("volume_ratio"))
    history_days = int(metrics.get("history_days") or 0)

    if rsi is not None:
        if rsi < 30:
            chips.append("RSI < 30")
        elif rsi < RSI_ATTRACTIVE:
            chips.append("RSI < 40")
        elif rsi > RSI_OVERBOUGHT:
            chips.append("RSI > 60")

    if close is not None and dma50 is not None:
        chips.append("Below 50DMA" if close < dma50 else "Above 50DMA")

    if close is not None and dma200 is not None:
        chips.append("Below 200DMA" if close < dma200 else "Above 200DMA")

    if metrics.get("momentum_improving"):
        chips.append("MACD improving")
    elif metrics.get("momentum_weakening"):
        chips.append("MACD weakening")

    if volume_ratio is not None:
        if volume_ratio >= 1.5:
            chips.append("Volume > 1.5x 20D Avg")
        elif volume_ratio > 1:
            chips.append("Volume > 20D Avg")

    if history_days and history_days < 200:
        chips.append("Limited history")

    if action == "HOLD" and not chips:
        chips.append("No dominant signal")

    return chips


def build_explanation(stock: str, action: str, metrics: dict[str, object], factor_chips: list[str]) -> str:
    base = action_description(action)
    rsi = _safe_float(metrics.get("rsi"))
    return_1y = _safe_float(metrics.get("return_1y"))
    volume_ratio = _safe_float(metrics.get("volume_ratio"))

    notes: list[str] = []
    if rsi is not None:
        notes.append(f"RSI is {rsi:.1f}")
    if volume_ratio is not None and volume_ratio >= 1.1:
        notes.append(f"volume is {volume_ratio:.2f}x the 20-day average")
    if return_1y is not None:
        notes.append(f"1Y return is {return_1y:.1f}%")

    sentence = f"{stock} is flagged as {action}. {base}"
    if notes:
        sentence += " Right now, " + ", ".join(notes) + "."
    elif factor_chips:
        sentence += " Signals: " + ", ".join(factor_chips[:3]) + "."
    return sentence


def build_fundamental_snapshot(row: pd.Series) -> tuple[dict[str, object], str]:
    field_map = {
        "ROE": ["ROE", "ROE_%", "Return_on_Equity"],
        "ROCE": ["ROCE", "ROCE_%", "Return_on_Capital_Employed"],
        "Debt / Equity": ["Debt_Equity", "Debt/Equity", "Debt_to_Equity"],
        "Operating Margin": ["OPM", "Operating_Margin", "Operating_Margin_%"],
        "Sales Growth": ["Sales_Growth", "Sales_Growth_%"],
        "Profit Growth": ["Profit_Growth", "Profit_Growth_%"],
    }

    fundamentals: dict[str, object] = {}
    has_live_value = False
    for display_label, candidates in field_map.items():
        value = None
        for candidate in candidates:
            if candidate in row.index:
                value = _safe_float(row.get(candidate))
                if value is None:
                    value = row.get(candidate)
                break
        if value not in (None, ""):
            has_live_value = True
        fundamentals[display_label] = value

    if has_live_value:
        status = "Fundamental fields are present in the loaded dataset. Source labeling should be tightened before using them in ranking."
    else:
        status = "Fundamental source not connected yet. This section is a placeholder for a later safe data integration."

    return fundamentals, status


def build_detail_view(
    row: pd.Series,
    hist: pd.DataFrame | None,
    *,
    chart_source: str,
    fundamental_payload: tuple[dict[str, object], str] | None = None,
) -> DetailView:
    metrics = analyze_price_history(hist)

    if not metrics:
        metrics = {
            "close": _safe_float(row.get("Close")),
            "rsi": _safe_float(row.get("RSI")),
            "volume_ratio": _safe_float(row.get("Vol_Spike")),
            "return_1y": _safe_float(row.get("1Y_Return_%")),
            "history_days": 0,
            "data_date": None,
            "dma50": None,
            "dma200": None,
            "momentum_improving": False,
            "momentum_weakening": False,
        }

    action = str(row.get("Action", "HOLD"))
    chips = build_factor_chips(action, metrics)
    explanation = build_explanation(str(row.get("Stock", row.get("Ticker", "This stock"))), action, metrics, chips)

    stats = {
        "Close": metrics.get("close"),
        "RSI": metrics.get("rsi"),
        "Volume vs 20D Avg": metrics.get("volume_ratio"),
        "1Y Return": metrics.get("return_1y"),
        "History Days": metrics.get("history_days"),
        "Data Date": metrics.get("data_date"),
        "Chart Source": chart_source,
    }
    if fundamental_payload is None:
        fundamental_stats, fundamental_status = build_fundamental_snapshot(row)
    else:
        fundamental_stats, fundamental_status = fundamental_payload
        if not fundamental_stats:
            fundamental_stats, fallback_status = build_fundamental_snapshot(row)
            if not fundamental_status:
                fundamental_status = fallback_status

    return DetailView(
        ticker=str(row.get("Ticker", "")),
        stock=str(row.get("Stock", row.get("Ticker", ""))),
        action=action,
        action_family=action_family_for(action),
        explanation=explanation,
        factor_chips=chips,
        stats=stats,
        fundamental_stats=fundamental_stats,
        fundamental_status=fundamental_status,
        chart_df=_coerce_history(hist),
        chart_source=chart_source,
    )
