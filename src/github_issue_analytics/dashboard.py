"""HTML dashboard generator with dark theme.

Generates a self-contained HTML dashboard with 6 metric categories,
interactive charts, and trend visualizations.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from github_issue_analytics.metrics import MetricsResult, _fmt_days


def generate_dashboard(
    metrics: MetricsResult,
    title: str | None = None,
) -> str:
    """Generate a self-contained HTML dashboard from MetricsResult.

    Args:
        metrics: Computed metrics result.
        title: Custom dashboard title.

    Returns:
        Complete HTML string (self-contained, no external deps).
    """
    title = title or f"GitHub Issue Analytics — {metrics.repo}"

    shs = metrics.shs
    shs_color = "#4caf50" if shs >= 70 else "#ff9800" if shs >= 40 else "#f44336"

    area_rows = ""
    for a in metrics.per_area:
        dsat_color = "#f44336" if a.dsat_score > 100 else "#ff9800" if a.dsat_score > 50 else "#4caf50"
        area_rows += f"""
        <tr>
            <td>{a.area}</td>
            <td>{a.total:,}</td>
            <td>{a.bugs:,}</td>
            <td>{a.regressions:,}</td>
            <td>{_fmt_days(a.age.median)}</td>
            <td>{a.fix_rate:.1%}</td>
            <td>{a.stale:,}</td>
            <td style="color: {dsat_color}; font-weight: bold;">{a.dsat_score:.0f}</td>
        </tr>"""

    backlog_rows = ""
    for bucket, count in metrics.backlog.age_buckets.items():
        pct = (count / metrics.backlog.total * 100) if metrics.backlog.total > 0 else 0
        backlog_rows += f"""
        <tr>
            <td>{bucket}</td>
            <td>{count:,}</td>
            <td>
                <div class="bar-container">
                    <div class="bar" style="width: {min(pct, 100):.0f}%"></div>
                    <span class="bar-label">{pct:.1f}%</span>
                </div>
            </td>
        </tr>"""

    status_rows = ""
    status_total = sum(metrics.status_distribution.values()) or 1
    for status, count in sorted(
        metrics.status_distribution.items(), key=lambda x: x[1], reverse=True
    ):
        pct = count / status_total * 100
        status_rows += f"""
        <tr>
            <td>{status}</td>
            <td>{count:,}</td>
            <td>
                <div class="bar-container">
                    <div class="bar bar-blue" style="width: {min(pct, 100):.0f}%"></div>
                    <span class="bar-label">{pct:.1f}%</span>
                </div>
            </td>
        </tr>"""

    nir_rows = ""
    for month, count in sorted(metrics.nir.months.items())[-12:]:
        nir_rows += f"""
        <tr>
            <td>{month}</td>
            <td>{count:,}</td>
        </tr>"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>
    :root {{
        --bg: #0d1117;
        --surface: #161b22;
        --border: #30363d;
        --text: #c9d1d9;
        --text-muted: #8b949e;
        --accent: #58a6ff;
        --green: #3fb950;
        --orange: #d29922;
        --red: #f85149;
    }}

    * {{ margin: 0; padding: 0; box-sizing: border-box; }}

    body {{
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
        background: var(--bg);
        color: var(--text);
        line-height: 1.5;
        padding: 24px;
    }}

    .header {{
        text-align: center;
        margin-bottom: 32px;
        padding: 24px;
        background: var(--surface);
        border: 1px solid var(--border);
        border-radius: 12px;
    }}

    .header h1 {{
        font-size: 1.8em;
        margin-bottom: 8px;
    }}

    .header .subtitle {{
        color: var(--text-muted);
        font-size: 0.95em;
    }}

    .shs-badge {{
        display: inline-block;
        padding: 12px 24px;
        border-radius: 8px;
        font-size: 2em;
        font-weight: bold;
        margin: 16px 0;
        color: white;
    }}

    .kpi-grid {{
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
        gap: 16px;
        margin-bottom: 32px;
    }}

    .kpi-card {{
        background: var(--surface);
        border: 1px solid var(--border);
        border-radius: 8px;
        padding: 16px;
        text-align: center;
    }}

    .kpi-card .value {{
        font-size: 1.8em;
        font-weight: bold;
        color: var(--accent);
    }}

    .kpi-card .label {{
        font-size: 0.85em;
        color: var(--text-muted);
        margin-top: 4px;
    }}

    .section {{
        background: var(--surface);
        border: 1px solid var(--border);
        border-radius: 12px;
        padding: 24px;
        margin-bottom: 24px;
    }}

    .section h2 {{
        font-size: 1.3em;
        margin-bottom: 16px;
        padding-bottom: 8px;
        border-bottom: 1px solid var(--border);
    }}

    table {{
        width: 100%;
        border-collapse: collapse;
    }}

    th, td {{
        padding: 8px 12px;
        text-align: left;
        border-bottom: 1px solid var(--border);
    }}

    th {{
        color: var(--text-muted);
        font-weight: 600;
        font-size: 0.85em;
        text-transform: uppercase;
    }}

    tr:hover {{
        background: rgba(88, 166, 255, 0.05);
    }}

    .bar-container {{
        display: flex;
        align-items: center;
        gap: 8px;
    }}

    .bar {{
        height: 20px;
        background: var(--green);
        border-radius: 4px;
        min-width: 2px;
    }}

    .bar-blue {{
        background: var(--accent);
    }}

    .bar-label {{
        font-size: 0.85em;
        color: var(--text-muted);
        white-space: nowrap;
    }}

    .footer {{
        text-align: center;
        color: var(--text-muted);
        font-size: 0.85em;
        margin-top: 32px;
        padding-top: 16px;
        border-top: 1px solid var(--border);
    }}

    .footer a {{
        color: var(--accent);
        text-decoration: none;
    }}

    @media (max-width: 768px) {{
        .kpi-grid {{
            grid-template-columns: repeat(2, 1fr);
        }}
    }}
</style>
</head>
<body>

<div class="header">
    <h1>📊 {title}</h1>
    <div class="subtitle">
        {metrics.total_open:,} open issues · {metrics.total_closed_recent:,} recently closed · {metrics.computed_at[:10]}
    </div>
    <div class="shs-badge" style="background: {shs_color};">
        SHS: {shs:.0f}/100
    </div>
</div>

<div class="kpi-grid">
    <div class="kpi-card">
        <div class="value">{metrics.total_open:,}</div>
        <div class="label">Open Issues</div>
    </div>
    <div class="kpi-card">
        <div class="value">{_fmt_days(metrics.cpt.median)}</div>
        <div class="label">Median Age (CPT)</div>
    </div>
    <div class="kpi-card">
        <div class="value">{metrics.fix_rate:.1%}</div>
        <div class="label">Fix Rate</div>
    </div>
    <div class="kpi-card">
        <div class="value">{metrics.escalation_rate:.1f}%</div>
        <div class="label">Escalation Rate</div>
    </div>
    <div class="kpi-card">
        <div class="value">{metrics.ttfr_no_response_pct:.1f}%</div>
        <div class="label">No Response Rate</div>
    </div>
    <div class="kpi-card">
        <div class="value">{metrics.backlog.stale:,}</div>
        <div class="label">Stale Items</div>
    </div>
    <div class="kpi-card">
        <div class="value">{metrics.dsat:.0f}</div>
        <div class="label">DSAT Score</div>
    </div>
    <div class="kpi-card">
        <div class="value">{metrics.ttc_untriaged_pct:.1f}%</div>
        <div class="label">Untriaged Rate</div>
    </div>
</div>

<div class="section">
    <h2>🗺️ Area Heatmap</h2>
    <table>
        <thead>
            <tr>
                <th>Area</th>
                <th>Total</th>
                <th>Bugs</th>
                <th>Regressions</th>
                <th>Median Age</th>
                <th>Fix Rate</th>
                <th>Stale</th>
                <th>DSAT</th>
            </tr>
        </thead>
        <tbody>
            {area_rows}
        </tbody>
    </table>
</div>

<div class="section">
    <h2>📦 Backlog Age Distribution</h2>
    <table>
        <thead>
            <tr>
                <th>Bucket</th>
                <th>Count</th>
                <th>Distribution</th>
            </tr>
        </thead>
        <tbody>
            {backlog_rows}
        </tbody>
    </table>
</div>

<div class="section">
    <h2>🏷️ Status Distribution</h2>
    <table>
        <thead>
            <tr>
                <th>Status</th>
                <th>Count</th>
                <th>Distribution</th>
            </tr>
        </thead>
        <tbody>
            {status_rows}
        </tbody>
    </table>
</div>

<div class="section">
    <h2>📈 Monthly Filing Trend (NIR)</h2>
    <p style="color: var(--text-muted); margin-bottom: 12px;">
        Direction: <strong>{metrics.nir.direction}</strong> ·
        3-month avg: {metrics.nir.trailing_3mo_avg:.0f}/mo ·
        6-month avg: {metrics.nir.trailing_6mo_avg:.0f}/mo
    </p>
    <table>
        <thead>
            <tr>
                <th>Month</th>
                <th>Issues Filed</th>
            </tr>
        </thead>
        <tbody>
            {nir_rows}
        </tbody>
    </table>
</div>

<div class="footer">
    Generated by <a href="https://github.com/kustonaut/github-issue-analytics">GitHub Issue Analytics</a>
    · {metrics.computed_at[:19]} UTC
</div>

</body>
</html>"""

    return html


def save_dashboard(html: str, output_path: str | Path):
    """Save dashboard HTML to a file."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
