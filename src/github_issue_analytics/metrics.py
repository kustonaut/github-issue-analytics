"""13-metric calculation engine for GitHub Issue Analytics.

All 13 metrics are repo-agnostic and driven by Config.

Metric categories:
  - Core Health:    CPT, TIE, DTC, NIR, ER, Fix Rate, Backlog
  - Responsiveness: TTFR, TTC, TTCl
  - Composite:      SHS, DSAT, Per-Area breakdown
"""

from __future__ import annotations

import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from github_issue_analytics.config import Config
from github_issue_analytics.etl import ClassifiedIssue


# ── Utility functions ─────────────────────────────────────────────


def _parse_dt(value: str | datetime | None) -> datetime | None:
    """Parse an ISO date string or return datetime directly.

    Always returns a UTC-aware datetime so arithmetic with
    ``datetime.now(timezone.utc)`` never raises.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, AttributeError):
        return None


def _median(values: list[float]) -> float:
    """Median of a list, or 0.0 if empty."""
    return statistics.median(values) if values else 0.0


def _mean(values: list[float]) -> float:
    """Mean of a list, or 0.0 if empty."""
    return statistics.mean(values) if values else 0.0


def _p90(values: list[float]) -> float:
    """90th percentile, or 0.0 if empty."""
    if not values:
        return 0.0
    sorted_v = sorted(values)
    idx = int(len(sorted_v) * 0.9)
    return sorted_v[min(idx, len(sorted_v) - 1)]


def _pct(part: int, whole: int) -> float:
    """Safe percentage calculation."""
    return (part / whole * 100) if whole > 0 else 0.0


def _fmt_days(days: float) -> str:
    """Format days into human-readable string."""
    if days < 1:
        return f"{days * 24:.0f}h"
    if days < 30:
        return f"{days:.0f}d"
    if days < 365:
        return f"{days / 30:.1f}mo"
    return f"{days / 365:.1f}yr"


# ── Data structures ───────────────────────────────────────────────

@dataclass
class AgeDistribution:
    """Age statistics for a set of issues."""

    mean: float = 0.0
    median: float = 0.0
    p90: float = 0.0
    min_days: float = 0.0
    max_days: float = 0.0
    count: int = 0

    def to_dict(self) -> dict:
        return {
            "mean": round(self.mean, 1),
            "median": round(self.median, 1),
            "p90": round(self.p90, 1),
            "min": round(self.min_days, 1),
            "max": round(self.max_days, 1),
            "count": self.count,
        }


@dataclass
class BacklogHealth:
    """Backlog age distribution and health indicators."""

    total: int = 0
    age_buckets: dict[str, int] = field(default_factory=dict)
    unassigned: int = 0
    zero_comment: int = 0
    stale: int = 0  # no activity > stale_days
    unassigned_pct: float = 0.0
    zero_comment_pct: float = 0.0
    stale_pct: float = 0.0


@dataclass
class MonthlyTrend:
    """Monthly filing trend data."""

    months: dict[str, int] = field(default_factory=dict)  # "YYYY-MM" → count
    trailing_3mo_avg: float = 0.0
    trailing_6mo_avg: float = 0.0
    direction: str = "stable"  # "increasing", "decreasing", "stable"


@dataclass
class AreaMetrics:
    """Per-area metric breakdown."""

    area: str
    total: int = 0
    bugs: int = 0
    features: int = 0
    regressions: int = 0
    age: AgeDistribution = field(default_factory=AgeDistribution)
    fix_rate: float = 0.0
    stale: int = 0
    dsat_score: float = 0.0


@dataclass
class MetricsResult:
    """Complete metrics output — all 13 metrics plus per-area breakdown."""

    # ── Core Health ───────────────────────────────────────
    cpt: AgeDistribution = field(default_factory=AgeDistribution)  # Customer Pain Time
    tie: AgeDistribution = field(default_factory=AgeDistribution)  # Time in Engineering
    dtc: AgeDistribution = field(default_factory=AgeDistribution)  # Days to Close
    nir: MonthlyTrend = field(default_factory=MonthlyTrend)        # New Incident Rate
    escalation_rate: float = 0.0                                    # ER
    fix_rate: float = 0.0
    backlog: BacklogHealth = field(default_factory=BacklogHealth)

    # ── Responsiveness ────────────────────────────────────
    ttfr_no_response_count: int = 0    # Time to First Response (zero-comment proxy)
    ttfr_no_response_pct: float = 0.0
    ttc_untriaged_count: int = 0       # Time to Triage
    ttc_untriaged_pct: float = 0.0
    ttcl: AgeDistribution = field(default_factory=AgeDistribution)  # Time to Close

    # ── Composite Scores ──────────────────────────────────
    shs: float = 0.0     # Service Health Score (0-100)
    dsat: float = 0.0     # Dissatisfaction Proxy
    median_age_days: float = 0.0

    # ── Breakdown ─────────────────────────────────────────
    per_area: list[AreaMetrics] = field(default_factory=list)
    total_open: int = 0
    total_closed_recent: int = 0
    status_distribution: dict[str, int] = field(default_factory=dict)
    type_distribution: dict[str, int] = field(default_factory=dict)

    # ── Meta ──────────────────────────────────────────────
    repo: str = ""
    computed_at: str = ""
    stale_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Serialize for JSON export."""
        return {
            "repo": self.repo,
            "computed_at": self.computed_at,
            "total_open": self.total_open,
            "total_closed_recent": self.total_closed_recent,
            "cpt": self.cpt.to_dict(),
            "tie": self.tie.to_dict(),
            "dtc": self.dtc.to_dict(),
            "nir": {
                "months": self.nir.months,
                "trailing_3mo_avg": round(self.nir.trailing_3mo_avg, 1),
                "trailing_6mo_avg": round(self.nir.trailing_6mo_avg, 1),
                "direction": self.nir.direction,
            },
            "escalation_rate": round(self.escalation_rate, 2),
            "fix_rate": round(self.fix_rate, 4),
            "backlog": {
                "total": self.backlog.total,
                "age_buckets": self.backlog.age_buckets,
                "unassigned": self.backlog.unassigned,
                "zero_comment": self.backlog.zero_comment,
                "stale": self.backlog.stale,
            },
            "ttfr_no_response_pct": round(self.ttfr_no_response_pct, 2),
            "ttc_untriaged_pct": round(self.ttc_untriaged_pct, 2),
            "ttcl": self.ttcl.to_dict(),
            "shs": round(self.shs, 1),
            "dsat": round(self.dsat, 1),
            "median_age_days": round(self.median_age_days, 1),
            "stale_count": self.stale_count,
            "status_distribution": self.status_distribution,
            "type_distribution": self.type_distribution,
            "per_area": [
                {
                    "area": a.area,
                    "total": a.total,
                    "bugs": a.bugs,
                    "features": a.features,
                    "regressions": a.regressions,
                    "median_age": round(a.age.median, 1),
                    "fix_rate": round(a.fix_rate, 4),
                    "stale": a.stale,
                    "dsat_score": round(a.dsat_score, 1),
                }
                for a in self.per_area
            ],
        }


# ── Metrics Engine ────────────────────────────────────────────────

class MetricsEngine:
    """Calculates all 13 metrics from classified issues.

    Usage:
        engine = MetricsEngine(config)
        result = engine.compute(open_issues, closed_issues)
    """

    def __init__(self, config: Config):
        self.config = config

    def compute(
        self,
        issues: list[ClassifiedIssue],
        closed_issues: list[ClassifiedIssue] | None = None,
    ) -> MetricsResult:
        """Calculate all 13 metrics.

        Args:
            issues: Open (or all current) issues.
            closed_issues: Recently closed issues (for fix rate, DTC).

        Returns:
            Complete MetricsResult with all 13 metrics.
        """
        closed_issues = closed_issues or []
        now = datetime.now(timezone.utc)

        result = MetricsResult(
            repo=self.config.repo,
            computed_at=now.isoformat(),
            total_open=len(issues),
            total_closed_recent=len(closed_issues),
        )

        if not issues:
            return result

        # Age values for all issues
        ages = [i.age_days for i in issues]

        # ── 1. CPT (Customer Pain Time) ──
        result.cpt = self._compute_age_dist(ages)
        result.median_age_days = result.cpt.median

        # ── 2. TIE (Time in Engineering) ──
        tie_ages = [i.age_days for i in issues if i.has_tracking_id]
        result.tie = self._compute_age_dist(tie_ages)

        # ── 3. DTC (Days to Close) ──
        if closed_issues:
            close_durations = []
            for ci in closed_issues:
                if ci.closed_at and ci.created_at:
                    closed_dt = _parse_dt(ci.closed_at)
                    created_dt = _parse_dt(ci.created_at)
                    if closed_dt and created_dt:
                        dur = (closed_dt - created_dt).total_seconds() / 86400
                        if dur >= 0:
                            close_durations.append(dur)
            result.dtc = self._compute_age_dist(close_durations)

        # ── 4. NIR (New Incident Rate) ──
        result.nir = self._compute_nir(issues)

        # ── 5. ER (Escalation Rate) ──
        regressions = [i for i in issues if i.issue_type == "regression"]
        high_reaction = [
            i for i in issues if i.reaction_count >= self.config.thresholds.high_reaction_threshold
        ]
        result.escalation_rate = _pct(len(regressions) + len(high_reaction), len(issues))

        # ── 6. Fix Rate ──
        fixed_statuses = {"fixed", "fix_committed", "resolved", "closed"}
        status_counts = Counter(i.status for i in issues)
        fixed_count = sum(count for s, count in status_counts.items() if s in fixed_statuses)
        total_for_fix = len(issues) + len(closed_issues)
        fixed_total = fixed_count + len(closed_issues)
        result.fix_rate = fixed_total / total_for_fix if total_for_fix > 0 else 0.0
        result.status_distribution = dict(status_counts)
        result.type_distribution = dict(Counter(i.issue_type for i in issues))

        # ── 7. Backlog Health ──
        result.backlog = self._compute_backlog(issues)
        result.stale_count = result.backlog.stale

        # ── 8. TTFR (Time to First Response) ──
        no_response = [i for i in issues if i.comment_count == 0]
        result.ttfr_no_response_count = len(no_response)
        result.ttfr_no_response_pct = _pct(len(no_response), len(issues))

        # ── 9. TTC (Time to Triage) ──
        untriaged = [i for i in issues if i.status == "untriaged"]
        result.ttc_untriaged_count = len(untriaged)
        result.ttc_untriaged_pct = _pct(len(untriaged), len(issues))

        # ── 10. TTCl (Time to Close) — for near-close issues ──
        near_close_statuses = {"fixed", "fix_committed", "resolved"}
        near_close = [i for i in issues if i.status in near_close_statuses]
        if near_close:
            result.ttcl = self._compute_age_dist([i.age_days for i in near_close])

        # ── 11. SHS (Service Health Score) ──
        result.shs = self._compute_shs(result, issues)

        # ── 12. DSAT (Dissatisfaction Proxy) ──
        result.dsat = self._compute_dsat(issues)

        # ── 13. Per-Area Breakdown ──
        result.per_area = self._compute_per_area(issues, closed_issues)

        return result

    # ── Internal calculators ──────────────────────────────────────

    @staticmethod
    def _compute_age_dist(values: list[float]) -> AgeDistribution:
        """Compute age distribution statistics."""
        if not values:
            return AgeDistribution()
        return AgeDistribution(
            mean=_mean(values),
            median=_median(values),
            p90=_p90(values),
            min_days=min(values),
            max_days=max(values),
            count=len(values),
        )

    def _compute_nir(self, issues: list[ClassifiedIssue]) -> MonthlyTrend:
        """Compute New Incident Rate — monthly filing trend."""
        monthly: dict[str, int] = defaultdict(int)
        for i in issues:
            dt = _parse_dt(i.created_at)
            if dt:
                key = dt.strftime("%Y-%m")
            else:
                key = str(i.created_at)[:7]  # fallback: "YYYY-MM" from string
            monthly[key] += 1

        sorted_months = sorted(monthly.keys())
        counts = [monthly[m] for m in sorted_months]

        trend = MonthlyTrend(months=dict(monthly))

        if len(counts) >= 3:
            trend.trailing_3mo_avg = _mean(counts[-3:])
        if len(counts) >= 6:
            trend.trailing_6mo_avg = _mean(counts[-6:])

        # Determine direction
        if len(counts) >= 3:
            recent = _mean(counts[-3:])
            earlier = _mean(counts[:3]) if len(counts) >= 6 else _mean(counts[:len(counts) - 3])
            if recent > earlier * 1.15:
                trend.direction = "increasing"
            elif recent < earlier * 0.85:
                trend.direction = "decreasing"
            else:
                trend.direction = "stable"

        return trend

    def _compute_backlog(self, issues: list[ClassifiedIssue]) -> BacklogHealth:
        """Compute backlog health with age buckets."""
        bh = BacklogHealth(total=len(issues))
        buckets = self.config.thresholds.backlog_age_buckets
        stale_days = self.config.thresholds.stale_days

        # Initialize buckets
        labels = []
        for i, threshold in enumerate(buckets):
            if i == 0:
                labels.append(f"<{threshold}d")
            else:
                labels.append(f"{buckets[i-1]}-{threshold}d")
        labels.append(f">{buckets[-1]}d")

        bucket_counts = {label: 0 for label in labels}

        for issue in issues:
            age = issue.age_days

            # Classify into bucket
            placed = False
            for idx, threshold in enumerate(buckets):
                if age < threshold:
                    bucket_counts[labels[idx]] += 1
                    placed = True
                    break
            if not placed:
                bucket_counts[labels[-1]] += 1

            # Stale check
            updated_dt = _parse_dt(issue.updated_at)
            if updated_dt:
                updated_age = (datetime.now(timezone.utc) - updated_dt).total_seconds() / 86400
            else:
                updated_age = issue.age_days  # fallback to issue age
            if updated_age > stale_days:
                bh.stale += 1

            if not issue.assignee:
                bh.unassigned += 1
            if issue.comment_count == 0:
                bh.zero_comment += 1

        bh.age_buckets = bucket_counts
        bh.unassigned_pct = _pct(bh.unassigned, bh.total)
        bh.zero_comment_pct = _pct(bh.zero_comment, bh.total)
        bh.stale_pct = _pct(bh.stale, bh.total)

        return bh

    def _compute_shs(self, result: MetricsResult, issues: list[ClassifiedIssue]) -> float:
        """Compute Service Health Score (0-100).

        Weighted composite:
          - Fix rate vs target (30 pts)
          - Median age vs target (20 pts)
          - Regression penalty (15 pts)
          - Stale rate penalty (15 pts)
          - No-response penalty (10 pts)
          - Untriaged penalty (10 pts)
        """
        score = 100.0
        t = self.config.thresholds

        # Fix rate score (30 pts)
        if t.target_fix_rate > 0:
            fix_ratio = min(result.fix_rate / t.target_fix_rate, 1.0)
            score -= (1 - fix_ratio) * 30

        # Median age score (20 pts)
        if result.median_age_days > t.target_median_age_days:
            age_penalty = min(
                (result.median_age_days - t.target_median_age_days) / t.target_median_age_days, 1.0
            )
            score -= age_penalty * 20

        # Regression penalty (15 pts)
        regression_count = sum(1 for i in issues if i.issue_type == "regression" and i.state == "open")
        if len(issues) > 0:
            regression_pct = regression_count / len(issues)
            score -= min(regression_pct * t.regression_penalty * 100, 15)

        # Stale rate (15 pts)
        if result.backlog.total > 0:
            stale_ratio = result.backlog.stale / result.backlog.total
            score -= min(stale_ratio * 30, 15)

        # No-response rate (10 pts)
        score -= min(result.ttfr_no_response_pct / 10, 10)

        # Untriaged rate (10 pts)
        score -= min(result.ttc_untriaged_pct / 10, 10)

        return max(0.0, min(100.0, score))

    def _compute_dsat(self, issues: list[ClassifiedIssue]) -> float:
        """Compute Dissatisfaction Proxy.

        Signals:
          - High reaction count issues
          - Old issues without tracking IDs
          - Zero-comment issues
          - Stale regressions
        """
        t = self.config.thresholds
        dsat = 0.0

        for issue in issues:
            if issue.reaction_count >= t.high_reaction_threshold:
                dsat += 2.0
            if issue.age_days > 365 and not issue.has_tracking_id:
                dsat += 1.0
            if issue.comment_count == 0 and issue.age_days > 30:
                dsat += 0.5
            if issue.issue_type == "regression" and issue.age_days > t.stale_days:
                dsat += t.regression_penalty

        return dsat

    def _compute_per_area(
        self,
        issues: list[ClassifiedIssue],
        closed_issues: list[ClassifiedIssue],
    ) -> list[AreaMetrics]:
        """Compute metrics broken down by configured area labels."""
        areas: dict[str, list[ClassifiedIssue]] = defaultdict(list)
        for issue in issues:
            areas[issue.area].append(issue)

        closed_by_area: dict[str, list[ClassifiedIssue]] = defaultdict(list)
        for ci in closed_issues:
            closed_by_area[ci.area].append(ci)

        result = []
        for area_name in sorted(areas.keys()):
            area_issues = areas[area_name]
            area_closed = closed_by_area.get(area_name, [])

            age_dist = self._compute_age_dist([i.age_days for i in area_issues])

            total_for_fix = len(area_issues) + len(area_closed)
            fixed_statuses = {"fixed", "fix_committed", "resolved", "closed"}
            fixed_open = sum(1 for i in area_issues if i.status in fixed_statuses)
            fix_rate = (fixed_open + len(area_closed)) / total_for_fix if total_for_fix > 0 else 0.0

            now = datetime.now(timezone.utc)
            stale_count = 0
            for i in area_issues:
                upd = _parse_dt(i.updated_at)
                if upd:
                    upd_age = (now - upd).total_seconds() / 86400
                else:
                    upd_age = i.age_days
                if upd_age > self.config.thresholds.stale_days:
                    stale_count += 1

            # Area DSAT score:
            #   open*1 + regression*3 + high_comment*2 + high_reaction*2
            bugs = sum(1 for i in area_issues if i.issue_type == "bug")
            regressions = sum(1 for i in area_issues if i.issue_type == "regression")
            high_comment = sum(
                1 for i in area_issues
                if i.comment_count >= self.config.thresholds.high_comment_threshold
            )
            high_reaction = sum(
                1 for i in area_issues
                if i.reaction_count >= self.config.thresholds.high_reaction_threshold
            )
            dsat_score = (
                len(area_issues) * 1
                + regressions * 3
                + high_comment * 2
                + high_reaction * 2
            )

            result.append(AreaMetrics(
                area=area_name,
                total=len(area_issues),
                bugs=bugs,
                features=sum(1 for i in area_issues if i.issue_type == "feature"),
                regressions=regressions,
                age=age_dist,
                fix_rate=fix_rate,
                stale=stale_count,
                dsat_score=dsat_score,
            ))

        # Sort by DSAT score descending (worst areas first)
        result.sort(key=lambda a: a.dsat_score, reverse=True)
        return result
