from __future__ import annotations

from datetime import date, datetime

import pandas as pd

from services.models import UniverseSnapshot

ACTION_FAMILY_MAP = {
    "OVERSOLD": "opportunity",
    "CONTRA BUY": "opportunity",
    "BUY": "opportunity",
    "BUILD": "opportunity",
    "SELL": "risk",
    "EXIT": "risk",
    "SHORT": "risk",
    "HOLD": "neutral",
}

ACTION_FAMILY_LABELS = {
    "opportunity": "Opportunities",
    "risk": "Risk",
    "neutral": "Neutral",
}

ACTION_DESCRIPTIONS = {
    "OVERSOLD": "Deeply weak and stretched, but momentum is trying to recover.",
    "CONTRA BUY": "Below major averages, but selling pressure is easing.",
    "BUY": "Momentum is improving from a constructive base.",
    "BUILD": "Trend is already constructive and still improving.",
    "SELL": "Extended strength is starting to weaken.",
    "EXIT": "Below the long trend line and momentum is softening.",
    "SHORT": "Below key averages with momentum still deteriorating.",
    "HOLD": "No strong directional setup right now.",
}

OPPORTUNITY_ACTIONS = {"OVERSOLD", "CONTRA BUY", "BUY", "BUILD"}
RISK_ACTIONS = {"SELL", "EXIT", "SHORT"}


def _safe_numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def action_family_for(action: str | None) -> str:
    return ACTION_FAMILY_MAP.get(str(action).strip().upper(), "neutral")


def action_description(action: str | None) -> str:
    return ACTION_DESCRIPTIONS.get(str(action).strip().upper(), ACTION_DESCRIPTIONS["HOLD"])


def format_datetime_label(value: datetime | None) -> str:
    if value is None:
        return "Unavailable"
    if value.tzinfo is not None:
        value = value.astimezone().replace(tzinfo=None)
    return value.strftime("%d %b %Y, %I:%M %p")


def format_date_label(value: date | None) -> str:
    if value is None:
        return "Unavailable"
    return value.strftime("%d %b %Y")


def build_truth_bar_data(snapshot: UniverseSnapshot) -> dict[str, object]:
    return {
        "universe_label": snapshot.universe_label,
        "mode_label": "Daily Snapshot" if snapshot.mode == "snapshot" else snapshot.mode,
        "market_data_label": format_date_label(snapshot.market_data_date),
        "generated_at_label": format_datetime_label(snapshot.generated_at),
        "coverage_label": f"{snapshot.screened_count} / {snapshot.constituent_count}",
        "missing_count": snapshot.missing_count,
        "is_stale": snapshot.is_stale,
    }


def build_missing_constituents_df(snapshot: UniverseSnapshot) -> pd.DataFrame:
    rows = [
        {
            "Stock": item.stock,
            "Ticker": item.ticker,
            "Reason": item.reason.replace("_", " ").title(),
            "History_Days": item.history_days,
        }
        for item in snapshot.missing_constituents
    ]
    return pd.DataFrame(rows)


def build_overview_cards(snapshot: UniverseSnapshot) -> list[dict[str, object]]:
    df = snapshot.screened_df
    rsi_series = _safe_numeric(df["RSI"]) if "RSI" in df.columns else pd.Series(dtype=float)
    volume_series = _safe_numeric(df["Vol_Spike"]) if "Vol_Spike" in df.columns else pd.Series(dtype=float)

    opportunity_count = int(df["Action"].isin(OPPORTUNITY_ACTIONS).sum()) if "Action" in df.columns else 0
    risk_count = int(df["Action"].isin(RISK_ACTIONS).sum()) if "Action" in df.columns else 0
    neutral_count = int((df["Action"] == "HOLD").sum()) if "Action" in df.columns else 0
    median_rsi = float(rsi_series.median()) if not rsi_series.dropna().empty else None
    high_volume_count = int((volume_series >= 1.5).sum()) if not volume_series.empty else 0
    coverage_pct = (
        (snapshot.screened_count / snapshot.constituent_count) * 100
        if snapshot.constituent_count
        else None
    )

    return [
        {
            "title": "Opportunities",
            "value": str(opportunity_count),
            "caption": "Constructive or contrarian setups",
            "tone": "positive",
        },
        {
            "title": "Risk / Weakness",
            "value": str(risk_count),
            "caption": "Setups showing deterioration",
            "tone": "negative",
        },
        {
            "title": "Neutral",
            "value": str(neutral_count),
            "caption": "No clear setup",
            "tone": "neutral",
        },
        {
            "title": "Median RSI",
            "value": f"{median_rsi:.1f}" if median_rsi is not None else "NA",
            "caption": "Center of current momentum",
            "tone": "accent",
        },
        {
            "title": "High Volume",
            "value": str(high_volume_count),
            "caption": "Above 1.5x 20-day average",
            "tone": "accent",
        },
        {
            "title": "Coverage",
            "value": f"{snapshot.screened_count} / {snapshot.constituent_count}",
            "caption": f"{coverage_pct:.0f}% of constituents screened" if coverage_pct is not None else "No universe count",
            "tone": "neutral",
        },
    ]


def _row_metric_text(row: pd.Series, metric_key: str) -> str:
    if metric_key == "RSI":
        return f"RSI {float(row['RSI']):.1f}"
    if metric_key == "Vol_Spike":
        return f"Vol {float(row['Vol_Spike']):.2f}x"
    if metric_key == "1Y_Return_%":
        return f"1Y {float(row['1Y_Return_%']):.1f}%"
    return ""


def build_top_ideas(snapshot: UniverseSnapshot) -> list[dict[str, object]]:
    df = snapshot.screened_df.copy()
    if df.empty:
        return []

    if "RSI" in df.columns:
        df["RSI"] = _safe_numeric(df["RSI"])
    if "Vol_Spike" in df.columns:
        df["Vol_Spike"] = _safe_numeric(df["Vol_Spike"])
    if "1Y_Return_%" in df.columns:
        df["1Y_Return_%"] = _safe_numeric(df["1Y_Return_%"])
    if "Rank" in df.columns:
        df["Rank"] = _safe_numeric(df["Rank"])

    ideas: list[dict[str, object]] = []
    used_tickers: set[str] = set()

    def add_card(title: str, candidates: pd.DataFrame, metric_key: str, fallback_note: str) -> None:
        nonlocal ideas
        if candidates.empty:
            return
        for _, row in candidates.iterrows():
            ticker = str(row["Ticker"])
            if ticker in used_tickers:
                continue
            used_tickers.add(ticker)
            ideas.append(
                {
                    "title": title,
                    "stock": row["Stock"],
                    "ticker": ticker,
                    "action": row["Action"],
                    "metric": _row_metric_text(row, metric_key),
                    "note": fallback_note,
                }
            )
            return

    add_card(
        "Best Contrarian",
        df[df["Action"].isin(["OVERSOLD", "CONTRA BUY"])].sort_values(["Rank", "RSI", "Vol_Spike"]),
        "RSI",
        "Lowest-momentum recovery setup",
    )
    add_card(
        "Strongest Trend",
        df[df["Action"].isin(["BUY", "BUILD"])].sort_values(["1Y_Return_%", "Vol_Spike"], ascending=[False, False]),
        "1Y_Return_%",
        "Most durable constructive trend",
    )
    volume_candidates = df[~df["Action"].isin(RISK_ACTIONS)]
    if volume_candidates.empty:
        volume_candidates = df
    add_card(
        "Volume Shock",
        volume_candidates.sort_values(["Vol_Spike", "Rank"], ascending=[False, True]),
        "Vol_Spike",
        "Largest move versus normal activity",
    )
    add_card(
        "Highest Risk",
        df[df["Action"].isin(RISK_ACTIONS)].sort_values(["Vol_Spike", "RSI"], ascending=[False, False]),
        "Vol_Spike",
        "Weak setup with pressure still visible",
    )

    limited_history = sorted(
        (
            item
            for item in snapshot.missing_constituents
            if item.reason in {"insufficient_history", "missing_cache_data"}
        ),
        key=lambda item: (item.history_days, item.stock),
    )
    if limited_history:
        item = limited_history[0]
        ideas.append(
            {
                "title": "Limited History",
                "stock": item.stock,
                "ticker": item.ticker,
                "action": "Missing",
                "metric": f"{item.history_days} sessions",
                "note": "Not fully screened in this snapshot",
            }
        )

    return ideas[:5]


def build_explorer_df(
    snapshot: UniverseSnapshot,
    history_days_by_ticker: dict[str, int] | None = None,
) -> pd.DataFrame:
    df = snapshot.screened_df.copy()
    if df.empty:
        return df

    history_days_by_ticker = history_days_by_ticker or {}
    df["Priority"] = _safe_numeric(df["Rank"]) if "Rank" in df.columns else 99
    df["RSI"] = _safe_numeric(df["RSI"]) if "RSI" in df.columns else pd.Series(dtype=float)
    df["Vol_Spike"] = _safe_numeric(df["Vol_Spike"]) if "Vol_Spike" in df.columns else pd.Series(dtype=float)
    df["1Y_Return_%"] = _safe_numeric(df["1Y_Return_%"]) if "1Y_Return_%" in df.columns else pd.Series(dtype=float)
    df["Action_Family"] = df["Action"].map(action_family_for)
    df["History_Days"] = df["Ticker"].map(lambda ticker: int(history_days_by_ticker.get(str(ticker).upper(), 0)))
    df["Limited_History"] = df["History_Days"].gt(0) & df["History_Days"].lt(200)
    df["RSI_Zone"] = pd.cut(
        df["RSI"],
        bins=[-1, 30, 40, 60, 101],
        labels=["Below 30", "30-40", "40-60", "Above 60"],
    )
    return df.sort_values(["Priority", "RSI", "Stock"], na_position="last").reset_index(drop=True)


def apply_explorer_filters(
    explorer_df: pd.DataFrame,
    *,
    search_text: str = "",
    family_filter: str = "All",
    action_filters: list[str] | None = None,
    rsi_zone: str = "Any",
    volume_spike_only: bool = False,
    positive_return_only: bool = False,
    limited_history_only: bool = False,
) -> pd.DataFrame:
    df = explorer_df.copy()
    if df.empty:
        return df

    if search_text.strip():
        mask = (
            df["Stock"].astype(str).str.contains(search_text, case=False, na=False)
            | df["Ticker"].astype(str).str.contains(search_text, case=False, na=False)
        )
        df = df[mask]

    if family_filter != "All":
        target_family = family_filter.lower().rstrip("s")
        if target_family == "opportunitie":
            target_family = "opportunity"
        df = df[df["Action_Family"] == target_family]

    if action_filters:
        df = df[df["Action"].isin(action_filters)]

    if rsi_zone != "Any":
        df = df[df["RSI_Zone"] == rsi_zone]

    if volume_spike_only:
        df = df[df["Vol_Spike"] >= 1.5]

    if positive_return_only:
        df = df[df["1Y_Return_%"] > 0]

    if limited_history_only:
        df = df[df["Limited_History"]]

    return df.reset_index(drop=True)
