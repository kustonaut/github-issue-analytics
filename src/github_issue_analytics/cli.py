"""Command-line interface for GitHub Issue Analytics.

Provides the `gia` CLI with commands for analysis, dashboards,
trend tracking, and data export.

Usage::

    # Full analysis from config
    gia analyze --config config.yaml

    # Quick analysis with defaults
    gia analyze --repo owner/repo

    # Generate dashboard only (from cache)
    gia dashboard --config config.yaml --cached

    # Show WoW trends
    gia trending --config config.yaml

    # Export raw classified issues
    gia export --config config.yaml --format csv
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click

from github_issue_analytics.analyzer import Analyzer
from github_issue_analytics.config import Config


@click.group()
@click.version_option(package_name="github-issue-analytics")
def cli():
    """GitHub Issue Analytics — data-driven GitHub issue management.

    Fetch issues, compute 13 health metrics, generate reports and
    dashboards. Track trends week-over-week.
    """


@cli.command()
@click.option(
    "--config", "-c", "config_path", type=click.Path(exists=True),
    help="Path to YAML configuration file.",
)
@click.option(
    "--repo", "-r", type=str,
    help="GitHub repo (owner/name). Used if no config file.",
)
@click.option(
    "--cached", is_flag=True, default=False,
    help="Use cached issues instead of fetching from GitHub API.",
)
@click.option(
    "--output", "-o", type=click.Path(),
    help="Output directory for reports. Default: ./gia_output",
)
@click.option(
    "--no-trend", is_flag=True, default=False,
    help="Skip saving a trend snapshot for this run.",
)
def analyze(config_path, repo, cached, output, no_trend):
    """Run full analysis pipeline.

    Fetches issues, computes 13 metrics, generates markdown report
    and HTML dashboard.

    \b
    Examples:
        gia analyze --config config.yaml
        gia analyze --repo microsoft/vscode --cached
        gia analyze -c config.yaml -o ./reports
    """
    analyzer = _build_analyzer(config_path, repo, output)

    click.echo(f"🔍 Analyzing {analyzer.config.repo}...")

    if cached:
        click.echo("📦 Using cached issues")
    else:
        click.echo("🌐 Fetching from GitHub API...")

    result = analyzer.run(use_cache=cached, save_trend=not no_trend)

    # Save artifacts
    paths = result.save_all()

    # Print summary
    shs = result.shs
    shs_emoji = "🟢" if shs >= 70 else "🟡" if shs >= 40 else "🔴"

    click.echo()
    click.echo(f"{shs_emoji} Service Health Score: {shs:.0f}/100")
    click.echo(f"📊 Open issues: {result.total_open:,}")
    click.echo(f"📈 Fix rate: {result.metrics.fix_rate:.1%}")
    click.echo(f"⏱️  Median age: {result.metrics.cpt.median:.0f} days")
    click.echo()
    click.echo(f"📄 Report:    {paths['report']}")
    click.echo(f"🌐 Dashboard: {paths['dashboard']}")


@cli.command()
@click.option(
    "--config", "-c", "config_path", type=click.Path(exists=True),
    help="Path to YAML config.",
)
@click.option("--repo", "-r", type=str, help="GitHub repo (owner/name).")
@click.option("--cached", is_flag=True, default=False, help="Use cached data.")
@click.option("--output", "-o", type=click.Path(), help="Output HTML path.")
@click.option("--open", "open_browser", is_flag=True, default=False, help="Open in browser.")
def dashboard(config_path, repo, cached, output, open_browser):
    """Generate an HTML dashboard.

    \b
    Examples:
        gia dashboard --config config.yaml --open
        gia dashboard --repo owner/repo --cached
    """
    analyzer = _build_analyzer(config_path, repo, None)

    click.echo(f"📊 Generating dashboard for {analyzer.config.repo}...")

    result = analyzer.run(use_cache=cached, save_trend=False)

    # Determine output path
    if output:
        out_path = Path(output)
    else:
        out_path = Path(analyzer.config.output_dir) / "dashboard.html"

    from github_issue_analytics.dashboard import save_dashboard
    save_dashboard(result.dashboard_html, out_path)

    click.echo(f"✅ Dashboard saved: {out_path}")

    if open_browser:
        import webbrowser
        webbrowser.open(str(out_path.resolve()))
        click.echo("🌐 Opened in browser")


@cli.command()
@click.option(
    "--config", "-c", "config_path", type=click.Path(exists=True),
    help="Path to YAML config.",
)
@click.option("--repo", "-r", type=str, help="GitHub repo (owner/name).")
@click.option("--output", "-o", type=click.Path(), help="Output directory.")
def trending(config_path, repo, output):
    """Show week-over-week trend analysis.

    Displays a table of historical metrics across all snapshots,
    with directional indicators for each metric.

    \b
    Examples:
        gia trending --config config.yaml
        gia trending --repo owner/repo
    """
    analyzer = _build_analyzer(config_path, repo, output)
    table = analyzer.trending()
    click.echo(table)


@cli.command()
@click.option(
    "--config", "-c", "config_path", type=click.Path(exists=True),
    help="Path to YAML config.",
)
@click.option("--repo", "-r", type=str, help="GitHub repo (owner/name).")
@click.option("--cached", is_flag=True, default=False, help="Use cached data.")
@click.option(
    "--format", "fmt", type=click.Choice(["json", "csv"]), default="json",
    help="Export format.",
)
@click.option("--output", "-o", type=click.Path(), help="Output file path.")
def export(config_path, repo, cached, fmt, output):
    """Export classified issues as JSON or CSV.

    Useful for custom analysis, BI tools, or downstream pipelines.

    \b
    Examples:
        gia export --config config.yaml --format csv -o issues.csv
        gia export --repo owner/repo --cached --format json
    """
    analyzer = _build_analyzer(config_path, repo, None)

    click.echo(f"📦 Loading issues for {analyzer.config.repo}...")

    fetch_result = analyzer.fetch(use_cache=cached)
    issues = fetch_result.issues

    if fmt == "json":
        from dataclasses import asdict

        data = [asdict(i) for i in issues]

        if output:
            with open(output, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, default=str)
            click.echo(f"✅ Exported {len(data)} issues to {output}")
        else:
            click.echo(json.dumps(data, indent=2, default=str))

    elif fmt == "csv":
        import csv
        from dataclasses import fields

        if not issues:
            click.echo("No issues to export.")
            return

        fieldnames = [f.name for f in fields(issues[0])]
        out = sys.stdout if not output else open(output, "w", newline="", encoding="utf-8")

        try:
            writer = csv.DictWriter(out, fieldnames=fieldnames)
            writer.writeheader()
            from dataclasses import asdict
            for issue in issues:
                writer.writerow({k: str(v) for k, v in asdict(issue).items()})
        finally:
            if output and out is not sys.stdout:
                out.close()

        if output:
            click.echo(f"✅ Exported {len(issues)} issues to {output}")


def _build_analyzer(
    config_path: str | None,
    repo: str | None,
    output: str | None,
) -> Analyzer:
    """Build an Analyzer from CLI options."""
    if config_path:
        analyzer = Analyzer.from_config(config_path)
    elif repo:
        analyzer = Analyzer.from_repo(repo)
    else:
        # Try default locations
        for default in ["config.yaml", "config.yml", "gia.yaml", "gia.yml"]:
            if Path(default).exists():
                analyzer = Analyzer.from_config(default)
                break
        else:
            raise click.UsageError(
                "No config file found. Use --config or --repo, or create "
                "config.yaml / gia.yaml in the current directory."
            )

    if output:
        analyzer.config.output_dir = output

    return analyzer


if __name__ == "__main__":
    cli()
