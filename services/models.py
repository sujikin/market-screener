from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

import pandas as pd


@dataclass(frozen=True)
class MissingConstituent:
    ticker: str
    stock: str
    reason: str
    history_days: int = 0


@dataclass
class UniverseSnapshot:
    universe_key: str
    universe_label: str
    mode: str
    generated_at: datetime | None
    market_data_date: date | None
    screened_df: pd.DataFrame
    constituent_map: dict[str, str] = field(default_factory=dict)
    coverage_count: int = 0
    constituent_count: int = 0
    missing_constituents: list[MissingConstituent] = field(default_factory=list)
    action_counts: dict[str, int] = field(default_factory=dict)
    is_stale: bool = False

    @property
    def screened_count(self) -> int:
        return self.coverage_count

    @property
    def missing_count(self) -> int:
        return len(self.missing_constituents)


@dataclass
class DetailView:
    ticker: str
    stock: str
    action: str
    action_family: str
    explanation: str
    factor_chips: list[str] = field(default_factory=list)
    stats: dict[str, object] = field(default_factory=dict)
    fundamental_stats: dict[str, object] = field(default_factory=dict)
    fundamental_status: str = ""
    chart_df: pd.DataFrame = field(default_factory=pd.DataFrame)
    chart_source: str = "Unavailable"
