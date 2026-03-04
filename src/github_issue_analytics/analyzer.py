"""High-level Analyzer facade — the primary user-facing class.

Ties together Config, GitHubETL, MetricsEngine, Reporter, Dashboard,
and TrendStore into a single coherent API.

Usage::

    from github_issue_analytics import Analyzer

    analyzer = Analyzer.from_config("config.yaml")
    result = analyzer.run()
    print(result.report)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from github_issue_analytics.config import Config
from github_issue_analytics.dashboard import generate_dashboard, save_dashboard
from github_issue_analytics.etl import GitHubETL
from github_issue_analytics.funnel import generate_funnel
from github_issue_analytics.heatmap import generate_heatmap
from github_issue_analytics.metrics import MetricsEngine, MetricsResult
from github_issue_analytics.reporter import generate_markdown_report
from github_issue_analytics.trends import TrendStore


class AnalysisResult:
    """Result container from a complete analysis run."""

    def __init__(
        self,
        metrics: MetricsResult,
        report: str,
        dashboard_html: str,
        output_dir: Path,
        heatmap_path: str | None = None,
        funnel_path: str | None = None,
    ):
        self.metrics = metrics
        self.report = report
        self.dashboard_html = dashboard_html
        self.output_dir = output_dir
        self.heatmap_path = heatmap_path
        self.funnel_path = funnel_path

    @property
    def shs(self) -> float:
        """Service Health Score (0-100)."""
        return self.metrics.shs

    @property
    def total_open(self) -> int:
        return self.metrics.total_open

    def save_all(self):
        """Save all artifacts to the output directory."""
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Report
        report_path = self.output_dir / "report.md"
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(self.report)

        # Dashboard
        dashboard_path = self.output_dir / "dashboard.html"
        save_dashboard(self.dashboard_html, dashboard_path)

        paths = {
            "report": str(report_path),
            "dashboard": str(dashboard_path),
        }

        # Heatmap (matplotlib; skip if no per_area data or matplotlib missing)
        if self.metrics.per_area:
            try:
                heatmap_path = self.output_dir / "heatmap.png"
                self.heatmap_path = generate_heatmap(self.metrics, heatmap_path)
                paths["heatmap"] = self.heatmap_path
            except ImportError:
                pass  # matplotlib not installed — skip silently

        # Funnel
        try:
            funnel_path = self.output_dir / "funnel.png"
            self.funnel_path = generate_funnel(self.metrics, funnel_path)
            paths["funnel"] = self.funnel_path
        except ImportError:
            pass

        return paths


class Analyzer:
    """High-level facade for GitHub issue analytics.

    This is the primary entry point for the library. It orchestrates
    the full pipeline: fetch → classify → compute metrics → generate
    reports + dashboards.

    Example::

        analyzer = Analyzer.from_config("config.yaml")
        result = analyzer.run()
        paths = result.save_all()
        print(f"Report: {paths['report']}")
        print(f"SHS: {result.shs:.0f}/100")
    """

    def __init__(self, config: Config):
        """Initialize with a Config object.

        Args:
            config: Configuration with repo, labels, thresholds, etc.
        """
        self.config = config
        self.etl = GitHubETL(config)
        self.engine = MetricsEngine(config)
        self._trend_store: TrendStore | None = None

    @classmethod
    def from_config(cls, config_path: str | Path) -> "Analyzer":
        """Create an Analyzer from a YAML config file.

        Args:
            config_path: Path to YAML configuration file.

        Returns:
            Configured Analyzer instance.
        """
        config = Config.from_yaml(config_path)
        return cls(config)

    @classmethod
    def from_repo(cls, repo: str, token: str | None = None) -> "Analyzer":
        """Create an Analyzer with default config for a GitHub repo.

        Args:
            repo: GitHub repo in owner/name format.
            token: Optional GitHub token (falls back to GITHUB_TOKEN env var).

        Returns:
            Configured Analyzer instance with sensible defaults.
        """
        config = Config.default(repo)
        if token:
            config.github_token = token
        return cls(config)

    @property
    def trend_store(self) -> TrendStore:
        """Lazy-initialized trend store."""
        if self._trend_store is None:
            history_dir = Path(self.config.output_dir) / "history"
            self._trend_store = TrendStore(history_dir)
        return self._trend_store

    def fetch(self, use_cache: bool = False) -> Any:
        """Fetch issues from GitHub API or cache.

        Args:
            use_cache: If True, load from cache instead of fetching.

        Returns:
            FetchResult with classified issues.
        """
        if use_cache:
            return self.etl.load_cached()
        return self.etl.fetch()

    def run(
        self,
        use_cache: bool = False,
        save_trend: bool = True,
        title: str | None = None,
    ) -> AnalysisResult:
        """Run the complete analytics pipeline.

        Steps:
            1. Fetch/load issues
            2. Compute all 13 metrics
            3. Load previous metrics for WoW comparison
            4. Generate markdown report (with deltas)
            5. Generate HTML dashboard
            6. Save trend snapshot

        Args:
            use_cache: Use cached issues instead of fetching.
            save_trend: Save this run as a trend snapshot.
            title: Custom title for reports.

        Returns:
            AnalysisResult with metrics, report, and dashboard.
        """
        # 1. Fetch
        fetch_result = self.fetch(use_cache=use_cache)

        # 2. Compute metrics
        metrics = self.engine.compute(
            fetch_result.issues, fetch_result.closed_issues
        )

        # 3. Load previous for WoW deltas
        previous = self._load_previous_metrics()

        # 4. Generate report
        report = generate_markdown_report(
            metrics=metrics,
            previous=previous,
            title=title or f"GitHub Issue Analytics — {self.config.repo}",
        )

        # 5. Generate dashboard
        dashboard_html = generate_dashboard(
            metrics=metrics,
            title=title,
        )

        # 6. Save trend
        if save_trend:
            self.trend_store.add_snapshot(metrics)

        output_dir = Path(self.config.output_dir)

        # 7. Generate heatmap + funnel (best-effort; matplotlib optional)
        heatmap_path = None
        funnel_path = None
        try:
            hp = output_dir / "heatmap.png"
            heatmap_path = generate_heatmap(metrics, hp)
        except (ImportError, Exception):
            pass

        try:
            fp = output_dir / "funnel.png"
            funnel_path = generate_funnel(metrics, fp)
        except (ImportError, Exception):
            pass

        return AnalysisResult(
            metrics=metrics,
            report=report,
            dashboard_html=dashboard_html,
            output_dir=output_dir,
            heatmap_path=heatmap_path,
            funnel_path=funnel_path,
        )

    def trending(self) -> str:
        """Get formatted WoW trend table.

        Returns:
            Markdown table of historical metric trends.
        """
        return self.trend_store.get_table()

    def _load_previous_metrics(self) -> MetricsResult | None:
        """Load previous week's metrics from trend store if available."""
        analysis = self.trend_store.analyze()
        if analysis.previous_date is None:
            return None

        # We don't have the full MetricsResult from history,
        # but the reporter only needs a subset of fields.
        # Return None for now — the reporter handles None gracefully.
        # Future: serialize full MetricsResult to trend store.
        return None
