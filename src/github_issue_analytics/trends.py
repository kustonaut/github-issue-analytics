"""WoW trend analysis and historical snapshot storage.

Stores weekly metric snapshots and computes week-over-week deltas
with configurable retention. Computes week-over-week deltas with configurable retention.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class TrendPoint:
    """A single weekly metric snapshot."""

    date: str
    metrics: dict[str, float]


@dataclass
class TrendDelta:
    """Week-over-week delta for a single metric."""

    name: str
    current: float
    previous: float
    delta: float
    direction: str  # ↑, ↓, →
    is_improvement: bool

    @property
    def delta_pct(self) -> float:
        """Delta as percentage of previous value."""
        return (self.delta / self.previous * 100) if self.previous != 0 else 0.0


@dataclass
class TrendAnalysis:
    """Complete WoW trend analysis across all metrics."""

    current_date: str
    previous_date: str | None
    deltas: list[TrendDelta]
    streak_weeks: int = 0  # consecutive weeks of SHS improvement
    snapshots_count: int = 0

    @property
    def improved(self) -> list[TrendDelta]:
        return [d for d in self.deltas if d.is_improvement]

    @property
    def regressed(self) -> list[TrendDelta]:
        return [d for d in self.deltas if not d.is_improvement and d.direction != "→"]


# Metrics where LOWER is better (inverse scoring)
LOWER_IS_BETTER = {
    "cpt_median",
    "cpt_p90",
    "escalation_rate",
    "ttfr_no_response_pct",
    "ttc_untriaged_pct",
    "dsat",
    "stale_count",
    "unassigned_pct",
}


class TrendStore:
    """Persistent store for weekly metric snapshots.

    Data is stored as a JSON file with an array of TrendPoint entries.
    Each entry has a date (ISO format) and a dict of metric values.

    Usage::

        store = TrendStore(Path("./metrics_history"))
        store.add_snapshot(metrics_result)

        analysis = store.analyze()
        for d in analysis.improved:
            print(f"✅ {d.name}: {d.delta:+.1f}")
    """

    def __init__(self, history_dir: str | Path, max_weeks: int = 52):
        """Init trend store.

        Args:
            history_dir: Directory for snapshot JSON files.
            max_weeks: Maximum snapshots to retain.
        """
        self.history_dir = Path(history_dir)
        self.history_dir.mkdir(parents=True, exist_ok=True)
        self.max_weeks = max_weeks
        self._history_file = self.history_dir / "trend_history.json"

    def _load(self) -> list[TrendPoint]:
        """Load all snapshots from disk."""
        if not self._history_file.exists():
            return []

        with open(self._history_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        return [TrendPoint(date=d["date"], metrics=d["metrics"]) for d in data]

    def _save(self, snapshots: list[TrendPoint]):
        """Save snapshots to disk, enforcing retention limit."""
        # Keep only max_weeks
        snapshots = snapshots[-self.max_weeks :]

        with open(self._history_file, "w", encoding="utf-8") as f:
            json.dump(
                [{"date": s.date, "metrics": s.metrics} for s in snapshots],
                f,
                indent=2,
            )

    def add_snapshot(
        self,
        metrics_result: Any,  # MetricsResult, kept as Any for loose coupling
        date: str | None = None,
    ):
        """Add a new weekly snapshot from a MetricsResult.

        Args:
            metrics_result: A MetricsResult object with computed metrics.
            date: Override date (ISO format). Defaults to today.
        """
        date = date or datetime.now(timezone.utc).strftime("%Y-%m-%d")

        snapshot_metrics = {
            "total_open": metrics_result.total_open,
            "total_closed_recent": metrics_result.total_closed_recent,
            "cpt_median": metrics_result.cpt.median,
            "cpt_p90": metrics_result.cpt.p90,
            "fix_rate": metrics_result.fix_rate,
            "escalation_rate": metrics_result.escalation_rate,
            "ttfr_no_response_pct": metrics_result.ttfr_no_response_pct,
            "ttc_untriaged_pct": metrics_result.ttc_untriaged_pct,
            "shs": metrics_result.shs,
            "dsat": metrics_result.dsat,
            "stale_count": metrics_result.backlog.stale,
            "unassigned_pct": metrics_result.backlog.unassigned_pct,
            "nir_3mo_avg": metrics_result.nir.trailing_3mo_avg,
            "nir_6mo_avg": metrics_result.nir.trailing_6mo_avg,
        }

        snapshots = self._load()

        # Replace if same date exists
        snapshots = [s for s in snapshots if s.date != date]
        snapshots.append(TrendPoint(date=date, metrics=snapshot_metrics))
        snapshots.sort(key=lambda s: s.date)

        self._save(snapshots)

    def analyze(self) -> TrendAnalysis:
        """Compute WoW trend analysis.

        Returns:
            TrendAnalysis with deltas between latest and previous snapshot.
        """
        snapshots = self._load()

        if not snapshots:
            return TrendAnalysis(
                current_date=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                previous_date=None,
                deltas=[],
                snapshots_count=0,
            )

        current = snapshots[-1]

        if len(snapshots) < 2:
            # No previous to compare
            deltas = [
                TrendDelta(
                    name=k,
                    current=v,
                    previous=0,
                    delta=0,
                    direction="→",
                    is_improvement=True,
                )
                for k, v in current.metrics.items()
            ]
            return TrendAnalysis(
                current_date=current.date,
                previous_date=None,
                deltas=deltas,
                snapshots_count=len(snapshots),
            )

        previous = snapshots[-2]
        deltas = []

        for key in current.metrics:
            curr_val = current.metrics.get(key, 0)
            prev_val = previous.metrics.get(key, 0)
            delta = curr_val - prev_val

            if abs(delta) < 0.001:
                direction = "→"
                is_improvement = True
            elif key in LOWER_IS_BETTER:
                direction = "↓" if delta < 0 else "↑"
                is_improvement = delta < 0
            else:
                direction = "↑" if delta > 0 else "↓"
                is_improvement = delta > 0

            deltas.append(
                TrendDelta(
                    name=key,
                    current=curr_val,
                    previous=prev_val,
                    delta=delta,
                    direction=direction,
                    is_improvement=is_improvement,
                )
            )

        # Calculate SHS streak
        streak = 0
        for i in range(len(snapshots) - 1, 0, -1):
            curr_shs = snapshots[i].metrics.get("shs", 0)
            prev_shs = snapshots[i - 1].metrics.get("shs", 0)
            if curr_shs > prev_shs:
                streak += 1
            else:
                break

        return TrendAnalysis(
            current_date=current.date,
            previous_date=previous.date,
            deltas=deltas,
            streak_weeks=streak,
            snapshots_count=len(snapshots),
        )

    def get_table(self) -> str:
        """Generate a formatted trend table across all snapshots.

        Returns:
            Markdown-formatted trend table.
        """
        snapshots = self._load()
        if not snapshots:
            return "No trend data available."

        # Column headers = metric names from the latest snapshot
        cols = list(snapshots[-1].metrics.keys())

        # Header row
        header = "| Date | " + " | ".join(cols) + " |"
        sep = "|------|" + "|".join(["------" for _ in cols]) + "|"

        rows = [header, sep]
        for snap in snapshots[-12:]:  # Show last 12 weeks
            vals = []
            for c in cols:
                v = snap.metrics.get(c, 0)
                if isinstance(v, float):
                    if "rate" in c or "pct" in c:
                        vals.append(f"{v:.1%}" if v < 1 else f"{v:.1f}%")
                    else:
                        vals.append(f"{v:.1f}")
                else:
                    vals.append(str(v))
            rows.append(f"| {snap.date} | " + " | ".join(vals) + " |")

        return "\n".join(rows)
