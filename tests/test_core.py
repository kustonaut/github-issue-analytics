"""Unit tests for github-issue-analytics core modules."""

from __future__ import annotations

import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from github_issue_analytics.config import Config, TrackingPattern, Thresholds
from github_issue_analytics.etl import ClassifiedIssue
from github_issue_analytics.metrics import MetricsEngine, MetricsResult


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def sample_config():
    """Minimal config for testing."""
    return Config(
        repo="test-org/test-repo",
        area_labels={
            "frontend": ["ui-", "frontend-"],
            "backend": ["api-", "server-"],
        },
        type_labels={
            "bug": ["bug", "type-bug"],
            "feature": ["feature-request"],
            "regression": ["regression"],
        },
        status_labels={
            "triaged": ["triaged", "confirmed"],
            "needs_info": ["needs-more-info"],
        },
        tracking_patterns=[
            TrackingPattern(name="ado", pattern="(?:ADO|AB)#\\d+"),
        ],
        thresholds=Thresholds(),
        bots=["dependabot[bot]", "github-actions[bot]"],
    )


@pytest.fixture
def sample_issues() -> list[ClassifiedIssue]:
    """Generate a set of classified issues for testing."""
    now = datetime.now(timezone.utc)
    issues = []

    for i in range(20):
        age_days = i * 30  # 0, 30, 60, ... 570
        created = now - timedelta(days=age_days)
        issues.append(
            ClassifiedIssue(
                number=i + 1,
                title=f"Test issue {i + 1}",
                state="open",
                created_at=created.isoformat(),
                updated_at=(now - timedelta(days=max(0, age_days - 10))).isoformat(),
                closed_at=None,
                author=f"user{i}",
                assignee="dev1" if i % 3 == 0 else None,
                labels=[
                    "bug" if i % 2 == 0 else "feature-request",
                    "ui-components" if i % 4 == 0 else "api-core",
                ],
                area="frontend" if i % 4 == 0 else "backend",
                issue_type="bug" if i % 2 == 0 else "feature",
                status="triaged" if i % 5 == 0 else "unknown",
                has_tracking_id=i % 7 == 0,
                tracking_type="ado" if i % 7 == 0 else None,
                age_days=age_days,
                comment_count=i * 2,
                reaction_count=i,
                url=f"https://github.com/test-org/test-repo/issues/{i + 1}",
                body_snippet=f"Test body for issue {i + 1}",
            )
        )

    return issues


@pytest.fixture
def closed_issues() -> list[ClassifiedIssue]:
    """Generate a set of recently closed issues."""
    now = datetime.now(timezone.utc)
    return [
        ClassifiedIssue(
            number=100 + i,
            title=f"Closed issue {i}",
            state="closed",
            created_at=(now - timedelta(days=60)).isoformat(),
            updated_at=(now - timedelta(days=i)).isoformat(),
            closed_at=(now - timedelta(days=i)).isoformat(),
            author=f"user{i}",
            assignee="dev1",
            labels=["bug", "ui-components"],
            area="frontend",
            issue_type="bug",
            status="triaged",
            has_tracking_id=False,
            tracking_type=None,
            age_days=60 - i,
            comment_count=5,
            reaction_count=2,
            url=f"https://github.com/test-org/test-repo/issues/{100 + i}",
            body_snippet=f"Closed body {i}",
        )
        for i in range(5)
    ]


# =============================================================================
# Config Tests
# =============================================================================


class TestConfig:
    def test_default_config(self):
        config = Config.default("owner/repo")
        assert config.repo == "owner/repo"
        assert isinstance(config.thresholds, Thresholds)
        assert config.thresholds.stale_days == 30  # Default is 30

    def test_classify_area(self, sample_config):
        assert sample_config.classify_area(["ui-", "priority-high"]) == "frontend"
        assert sample_config.classify_area(["api-"]) == "backend"
        assert sample_config.classify_area(["random-label"]) == "Unknown"

    def test_classify_type(self, sample_config):
        assert sample_config.classify_type(["bug", "area-core"]) == "bug"
        assert sample_config.classify_type(["feature-request"]) == "feature"
        assert sample_config.classify_type(["regression"]) == "regression"
        assert sample_config.classify_type(["random"]) == "unknown"

    def test_classify_status(self, sample_config):
        assert sample_config.classify_status(["triaged", "bug"]) == "triaged"
        assert sample_config.classify_status(["needs-more-info"]) == "needs_info"
        assert sample_config.classify_status(["unknown-label"]) == "untriaged"

    def test_tracking_id_detection(self, sample_config):
        assert sample_config.has_tracking_id("Fixed in ADO#12345") == (True, "ado")
        assert sample_config.has_tracking_id("See AB#9999") == (True, "ado")
        assert sample_config.has_tracking_id("Just a normal body")[0] is False

    def test_is_bot(self, sample_config):
        assert sample_config.is_bot("dependabot[bot]") is True
        assert sample_config.is_bot("github-actions[bot]") is True
        assert sample_config.is_bot("real-user") is False

    def test_from_yaml_roundtrip(self, sample_config, tmp_path):
        """Test that config can be saved to YAML and loaded back."""
        import yaml

        config_path = tmp_path / "test_config.yaml"
        config_dict = {
            "repo": sample_config.repo,
            "area_labels": sample_config.area_labels,
            "type_labels": sample_config.type_labels,
            "status_labels": sample_config.status_labels,
            "tracking_patterns": [
                {"name": tp.name, "pattern": tp.pattern}
                for tp in sample_config.tracking_patterns
            ],
            "thresholds": {
                "stale_days": sample_config.thresholds.stale_days,
                "target_fix_rate": sample_config.thresholds.target_fix_rate,
            },
            "bots": sample_config.bots,
        }

        with open(config_path, "w") as f:
            yaml.dump(config_dict, f)

        loaded = Config.from_yaml(config_path)
        assert loaded.repo == "test-org/test-repo"
        assert "frontend" in loaded.area_labels
        assert loaded.is_bot("dependabot[bot]") is True


# =============================================================================
# Metrics Tests
# =============================================================================


class TestMetrics:
    def test_compute_returns_result(self, sample_config, sample_issues, closed_issues):
        engine = MetricsEngine(sample_config)
        result = engine.compute(sample_issues, closed_issues)

        assert isinstance(result, MetricsResult)
        assert result.total_open == 20
        assert result.total_closed_recent == 5

    def test_shs_is_bounded(self, sample_config, sample_issues, closed_issues):
        engine = MetricsEngine(sample_config)
        result = engine.compute(sample_issues, closed_issues)

        assert 0 <= result.shs <= 100

    def test_fix_rate_calculated(self, sample_config, sample_issues, closed_issues):
        engine = MetricsEngine(sample_config)
        result = engine.compute(sample_issues, closed_issues)

        # 5 closed out of 25 total
        expected = 5 / 25
        assert abs(result.fix_rate - expected) < 0.01

    def test_age_distribution(self, sample_config, sample_issues, closed_issues):
        engine = MetricsEngine(sample_config)
        result = engine.compute(sample_issues, closed_issues)

        assert result.cpt.median >= 0
        assert result.cpt.p90 >= result.cpt.median
        assert result.cpt.mean >= 0

    def test_empty_issues(self, sample_config):
        engine = MetricsEngine(sample_config)
        result = engine.compute([], [])

        assert result.total_open == 0
        assert 0 <= result.shs <= 100  # Score is bounded
        assert result.fix_rate == 0.0

    def test_per_area_breakdown(self, sample_config, sample_issues, closed_issues):
        engine = MetricsEngine(sample_config)
        result = engine.compute(sample_issues, closed_issues)

        assert len(result.per_area) > 0
        area_names = [a.area for a in result.per_area]
        assert "frontend" in area_names or "backend" in area_names

    def test_backlog_health(self, sample_config, sample_issues, closed_issues):
        engine = MetricsEngine(sample_config)
        result = engine.compute(sample_issues, closed_issues)

        assert result.backlog.total == 20
        assert result.backlog.stale >= 0
        assert 0 <= result.backlog.unassigned_pct <= 100

    def test_escalation_rate(self, sample_config, sample_issues, closed_issues):
        engine = MetricsEngine(sample_config)
        result = engine.compute(sample_issues, closed_issues)

        # Some issues have high reaction/comment counts
        assert result.escalation_rate >= 0

    def test_nir_monthly_trend(self, sample_config, sample_issues, closed_issues):
        engine = MetricsEngine(sample_config)
        result = engine.compute(sample_issues, closed_issues)

        assert len(result.nir.months) > 0
        assert result.nir.direction in ("increasing", "decreasing", "stable")


# =============================================================================
# Trend Store Tests
# =============================================================================


class TestTrendStore:
    def test_add_and_analyze(self, sample_config, sample_issues, closed_issues, tmp_path):
        from github_issue_analytics.trends import TrendStore

        store = TrendStore(tmp_path / "history")
        engine = MetricsEngine(sample_config)

        # Add two snapshots
        result1 = engine.compute(sample_issues, closed_issues)
        store.add_snapshot(result1, date="2026-02-24")
        store.add_snapshot(result1, date="2026-03-03")

        analysis = store.analyze()
        assert analysis.snapshots_count == 2
        assert analysis.previous_date == "2026-02-24"
        assert len(analysis.deltas) > 0

    def test_get_table(self, sample_config, sample_issues, closed_issues, tmp_path):
        from github_issue_analytics.trends import TrendStore

        store = TrendStore(tmp_path / "history")
        engine = MetricsEngine(sample_config)
        result = engine.compute(sample_issues, closed_issues)

        store.add_snapshot(result, date="2026-02-24")
        store.add_snapshot(result, date="2026-03-03")

        table = store.get_table()
        assert "2026-02-24" in table
        assert "2026-03-03" in table

    def test_empty_store(self, tmp_path):
        from github_issue_analytics.trends import TrendStore

        store = TrendStore(tmp_path / "empty")
        analysis = store.analyze()
        assert analysis.snapshots_count == 0
        assert analysis.previous_date is None


# =============================================================================
# Reporter Tests
# =============================================================================


class TestReporter:
    def test_generate_report(self, sample_config, sample_issues, closed_issues):
        from github_issue_analytics.reporter import generate_markdown_report

        engine = MetricsEngine(sample_config)
        result = engine.compute(sample_issues, closed_issues)

        report = generate_markdown_report(result)
        assert "Service Health Score" in report
        assert "Fix Rate" in report
        assert "Backlog" in report

    def test_report_with_previous(self, sample_config, sample_issues, closed_issues):
        from github_issue_analytics.reporter import generate_markdown_report

        engine = MetricsEngine(sample_config)
        result = engine.compute(sample_issues, closed_issues)

        # Use same result as "previous" — all deltas should be zero
        report = generate_markdown_report(result, previous=result)
        assert "Week-over-Week" in report or "WoW" in report or "➡️" in report


# =============================================================================
# Dashboard Tests
# =============================================================================


class TestDashboard:
    def test_generate_html(self, sample_config, sample_issues, closed_issues):
        from github_issue_analytics.dashboard import generate_dashboard

        engine = MetricsEngine(sample_config)
        result = engine.compute(sample_issues, closed_issues)

        html = generate_dashboard(result)
        assert "<html" in html
        assert "SHS" in html
        assert "github-issue-analytics" in html

    def test_save_dashboard(self, sample_config, sample_issues, closed_issues, tmp_path):
        from github_issue_analytics.dashboard import generate_dashboard, save_dashboard

        engine = MetricsEngine(sample_config)
        result = engine.compute(sample_issues, closed_issues)

        html = generate_dashboard(result)
        out_path = tmp_path / "test_dashboard.html"
        save_dashboard(html, out_path)

        assert out_path.exists()
        assert out_path.stat().st_size > 1000


# =============================================================================
# Heatmap Tests
# =============================================================================


class TestHeatmap:
    def test_generate_heatmap_png(self, sample_config, sample_issues, closed_issues, tmp_path):
        """Generate a heatmap PNG and verify it saved."""
        pytest.importorskip("matplotlib")
        from github_issue_analytics.heatmap import generate_heatmap

        engine = MetricsEngine(sample_config)
        result = engine.compute(sample_issues, closed_issues)

        out_path = tmp_path / "heatmap.png"
        path = generate_heatmap(result, out_path)

        assert path is not None
        assert Path(path).exists()
        assert Path(path).stat().st_size > 1000

    def test_heatmap_base64_when_no_path(self, sample_config, sample_issues, closed_issues):
        """When output_path is None, returns base64 string."""
        pytest.importorskip("matplotlib")
        from github_issue_analytics.heatmap import generate_heatmap

        engine = MetricsEngine(sample_config)
        result = engine.compute(sample_issues, closed_issues)

        b64 = generate_heatmap(result, None)
        assert b64 is not None
        assert len(b64) > 100  # reasonable base64 length

    def test_heatmap_returns_none_for_empty_areas(self, sample_config):
        """No per_area data → returns None gracefully."""
        pytest.importorskip("matplotlib")
        from github_issue_analytics.heatmap import generate_heatmap

        engine = MetricsEngine(sample_config)
        result = engine.compute([], [])

        assert generate_heatmap(result) is None

    def test_save_heatmap_raises_on_empty(self, sample_config, tmp_path):
        """save_heatmap should raise ValueError for empty data."""
        pytest.importorskip("matplotlib")
        from github_issue_analytics.heatmap import save_heatmap

        engine = MetricsEngine(sample_config)
        result = engine.compute([], [])

        with pytest.raises(ValueError, match="No per_area"):
            save_heatmap(result, tmp_path / "empty.png")


# =============================================================================
# Funnel Tests
# =============================================================================


class TestFunnel:
    def test_generate_funnel_png(self, sample_config, sample_issues, closed_issues, tmp_path):
        """Generate a funnel PNG and verify it saved."""
        pytest.importorskip("matplotlib")
        from github_issue_analytics.funnel import generate_funnel

        engine = MetricsEngine(sample_config)
        result = engine.compute(sample_issues, closed_issues)

        out_path = tmp_path / "funnel.png"
        path = generate_funnel(result, out_path)

        assert path is not None
        assert Path(path).exists()
        assert Path(path).stat().st_size > 1000

    def test_funnel_base64_when_no_path(self, sample_config, sample_issues, closed_issues):
        """When output_path is None, returns base64 string."""
        pytest.importorskip("matplotlib")
        from github_issue_analytics.funnel import generate_funnel

        engine = MetricsEngine(sample_config)
        result = engine.compute(sample_issues, closed_issues)

        b64 = generate_funnel(result, None)
        assert b64 is not None
        assert len(b64) > 100

    def test_funnel_stages_match_metrics(self, sample_config, sample_issues, closed_issues):
        """Verify stage values map correctly from MetricsResult."""
        pytest.importorskip("matplotlib")
        from github_issue_analytics.funnel import _build_stages

        engine = MetricsEngine(sample_config)
        result = engine.compute(sample_issues, closed_issues)

        stages = _build_stages(result)
        assert len(stages) == 4
        assert stages[0].label == "INTAKE"
        assert stages[1].label == "TRIAGE"
        assert stages[2].label == "ACTIVE"
        assert stages[3].label == "CLOSING"
        assert stages[0].value == result.backlog.total or stages[0].value == result.total_open
        assert stages[3].value == result.total_closed_recent
