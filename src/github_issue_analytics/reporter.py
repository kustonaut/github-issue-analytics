"""Markdown and HTML report generator.

Generates stakeholder-ready reports with tables, WoW deltas,
per-area breakdowns, and trend indicators.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from github_issue_analytics.metrics import MetricsResult, _fmt_days, _pct


def generate_markdown_report(
    metrics: MetricsResult,
    previous: MetricsResult | None = None,
    title: str | None = None,
) -> str:
    """Generate a full Markdown report from MetricsResult.

    Args:
        metrics: Current metrics.
        previous: Previous period metrics (for WoW deltas).
        title: Custom report title.

    Returns:
        Complete Markdown report string.
    """
    title = title or f"GitHub Issue Analytics — {metrics.repo}"
    lines = [f"# {title}", ""]
    lines.append(f"> Generated: {metrics.computed_at[:19]} UTC")
    lines.append(f"> Repository: `{metrics.repo}`")
    lines.append(f"> Open issues: **{metrics.total_open:,}** | Recently closed: **{metrics.total_closed_recent:,}**")
    lines.append("")

    # ── Service Health Score ──
    shs = metrics.shs
    shs_emoji = "🟢" if shs >= 70 else "🟡" if shs >= 40 else "🔴"
    lines.append(f"## {shs_emoji} Service Health Score: {shs:.0f}/100")
    lines.append("")

    # ── Core Health ──
    lines.append("## Core Health Metrics")
    lines.append("")
    lines.append("| Metric | Value | Detail |")
    lines.append("|--------|-------|--------|")

    lines.append(
        f"| **CPT** (Customer Pain Time) "
        f"| Median: **{_fmt_days(metrics.cpt.median)}** "
        f"| Mean: {_fmt_days(metrics.cpt.mean)}, P90: {_fmt_days(metrics.cpt.p90)}, "
        f"n={metrics.cpt.count:,} |"
    )

    lines.append(
        f"| **TIE** (Time in Engineering) "
        f"| Median: **{_fmt_days(metrics.tie.median)}** "
        f"| {metrics.tie.count:,} issues with tracking IDs |"
    )

    if metrics.dtc.count > 0:
        lines.append(
            f"| **DTC** (Days to Close) "
            f"| Median: **{_fmt_days(metrics.dtc.median)}** "
            f"| P90: {_fmt_days(metrics.dtc.p90)}, n={metrics.dtc.count:,} |"
        )

    dir_emoji = {"increasing": "📈", "decreasing": "📉", "stable": "➡️"}
    lines.append(
        f"| **NIR** (New Incident Rate) "
        f"| {dir_emoji.get(metrics.nir.direction, '➡️')} **{metrics.nir.direction}** "
        f"| 3mo avg: {metrics.nir.trailing_3mo_avg:.0f}/mo, "
        f"6mo avg: {metrics.nir.trailing_6mo_avg:.0f}/mo |"
    )

    lines.append(
        f"| **ER** (Escalation Rate) "
        f"| **{metrics.escalation_rate:.1f}%** "
        f"| Regressions + high-reaction composite |"
    )

    lines.append(
        f"| **Fix Rate** "
        f"| **{metrics.fix_rate:.1%}** "
        f"| Fixed+closed / total tracked |"
    )

    lines.append("")

    # ── Backlog Health ──
    lines.append("## Backlog Health")
    lines.append("")
    lines.append(f"- **Total open:** {metrics.backlog.total:,}")
    lines.append(f"- **Unassigned:** {metrics.backlog.unassigned:,} ({metrics.backlog.unassigned_pct:.1f}%)")
    lines.append(f"- **Zero comments:** {metrics.backlog.zero_comment:,} ({metrics.backlog.zero_comment_pct:.1f}%)")
    lines.append(f"- **Stale (>{metrics.stale_count}d no activity):** {metrics.backlog.stale:,} ({metrics.backlog.stale_pct:.1f}%)")
    lines.append("")

    if metrics.backlog.age_buckets:
        lines.append("### Age Distribution")
        lines.append("")
        lines.append("| Bucket | Count | % |")
        lines.append("|--------|-------|---|")
        for bucket, count in metrics.backlog.age_buckets.items():
            pct = _pct(count, metrics.backlog.total)
            bar = "█" * max(1, int(pct / 3))
            lines.append(f"| {bucket} | {count:,} | {pct:.1f}% {bar} |")
        lines.append("")

    # ── Responsiveness ──
    lines.append("## Responsiveness")
    lines.append("")
    lines.append("| Metric | Value | Detail |")
    lines.append("|--------|-------|--------|")
    lines.append(
        f"| **TTFR** (First Response) "
        f"| **{metrics.ttfr_no_response_pct:.1f}%** no response "
        f"| {metrics.ttfr_no_response_count:,} issues with 0 comments |"
    )
    lines.append(
        f"| **TTC** (Time to Triage) "
        f"| **{metrics.ttc_untriaged_pct:.1f}%** untriaged "
        f"| {metrics.ttc_untriaged_count:,} issues without status label |"
    )
    if metrics.ttcl.count > 0:
        lines.append(
            f"| **TTCl** (Time to Close) "
            f"| Median: **{_fmt_days(metrics.ttcl.median)}** "
            f"| {metrics.ttcl.count:,} near-close issues |"
        )
    lines.append("")

    # ── Status Distribution ──
    if metrics.status_distribution:
        lines.append("## Status Distribution")
        lines.append("")
        lines.append("| Status | Count | % |")
        lines.append("|--------|-------|---|")
        total = sum(metrics.status_distribution.values())
        for status, count in sorted(
            metrics.status_distribution.items(), key=lambda x: x[1], reverse=True
        ):
            pct = _pct(count, total)
            lines.append(f"| {status} | {count:,} | {pct:.1f}% |")
        lines.append("")

    # ── Type Distribution ──
    if metrics.type_distribution:
        lines.append("## Type Distribution")
        lines.append("")
        lines.append("| Type | Count | % |")
        lines.append("|------|-------|---|")
        total = sum(metrics.type_distribution.values())
        for issue_type, count in sorted(
            metrics.type_distribution.items(), key=lambda x: x[1], reverse=True
        ):
            pct = _pct(count, total)
            lines.append(f"| {issue_type} | {count:,} | {pct:.1f}% |")
        lines.append("")

    # ── Per-Area Breakdown ──
    if metrics.per_area:
        lines.append("## Per-Area Breakdown")
        lines.append("")
        lines.append("| Area | Total | Bugs | Regressions | Median Age | Fix Rate | Stale | DSAT |")
        lines.append("|------|-------|------|-------------|-----------|----------|-------|------|")
        for a in metrics.per_area:
            lines.append(
                f"| **{a.area}** "
                f"| {a.total:,} "
                f"| {a.bugs:,} "
                f"| {a.regressions:,} "
                f"| {_fmt_days(a.age.median)} "
                f"| {a.fix_rate:.1%} "
                f"| {a.stale:,} "
                f"| {a.dsat_score:.0f} |"
            )
        lines.append("")

    # ── WoW Deltas ──
    if previous:
        lines.append("## Week-over-Week Changes")
        lines.append("")
        lines.append("| Metric | Previous | Current | Delta |")
        lines.append("|--------|----------|---------|-------|")

        _add_delta_row(lines, "Open Issues", previous.total_open, metrics.total_open)
        _add_delta_row(lines, "Median Age (days)", previous.median_age_days, metrics.median_age_days)
        _add_delta_row(lines, "Fix Rate", previous.fix_rate * 100, metrics.fix_rate * 100, suffix="%")
        _add_delta_row(lines, "SHS", previous.shs, metrics.shs)
        _add_delta_row(lines, "Stale Count", previous.stale_count, metrics.stale_count, lower_better=True)
        _add_delta_row(
            lines,
            "No Response %",
            previous.ttfr_no_response_pct,
            metrics.ttfr_no_response_pct,
            lower_better=True,
        )
        lines.append("")

    lines.append("---")
    lines.append(f"*Report generated by [GitHub Issue Analytics](https://github.com/kustonaut/github-issue-analytics)*")
    lines.append("")

    return "\n".join(lines)


def _add_delta_row(
    lines: list[str],
    label: str,
    prev_val: float,
    curr_val: float,
    lower_better: bool = False,
    suffix: str = "",
):
    """Add a WoW delta row to the report."""
    delta = curr_val - prev_val
    if delta > 0:
        sign = "+"
        emoji = "🔻" if lower_better else "🔺"
    elif delta < 0:
        sign = ""
        emoji = "🔺" if lower_better else "🔻"
    else:
        sign = ""
        emoji = "➡️"

    lines.append(
        f"| {label} | {prev_val:.1f}{suffix} | {curr_val:.1f}{suffix} | {emoji} {sign}{delta:.1f}{suffix} |"
    )


def save_report(report: str, output_path: str | Path):
    """Save a report string to a file."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report)
