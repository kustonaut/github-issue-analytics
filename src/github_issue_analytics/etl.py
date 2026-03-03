"""GitHub REST API ETL pipeline.

Paginated issue fetcher with rate limiting, caching, and classification.
All repo-specific references are removed — everything is driven by Config.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

from github_issue_analytics.config import Config

logger = logging.getLogger(__name__)

# GitHub API constants
GITHUB_API = "https://api.github.com"
PER_PAGE = 100
RATE_LIMIT_PAUSE = 60  # seconds to wait when rate limited


@dataclass
class ClassifiedIssue:
    """A GitHub issue with structured classification fields.

    This is the core data unit that flows through the metrics engine.
    Raw GitHub API response → ClassifiedIssue via classify().
    """

    number: int
    title: str
    state: str  # "open" or "closed"
    created_at: datetime
    updated_at: datetime
    closed_at: datetime | None
    author: str
    assignee: str | None
    labels: list[str]
    area: str
    issue_type: str
    status: str
    has_tracking_id: bool
    tracking_type: str | None
    age_days: float
    comment_count: int
    reaction_count: int
    url: str
    body_snippet: str  # first 200 chars of body for pattern matching

    def to_dict(self) -> dict[str, Any]:
        """Serialize for JSON export."""
        d = asdict(self)
        d["created_at"] = self.created_at.isoformat()
        d["updated_at"] = self.updated_at.isoformat()
        d["closed_at"] = self.closed_at.isoformat() if self.closed_at else None
        return d


@dataclass
class FetchResult:
    """Result of an ETL fetch operation."""

    issues: list[ClassifiedIssue]
    closed_issues: list[ClassifiedIssue]
    fetch_time: datetime
    repo: str
    total_open: int
    total_closed_recent: int
    from_cache: bool = False


class GitHubETL:
    """Paginated GitHub REST API fetcher with rate limiting and caching.

    Usage:
        etl = GitHubETL(config, token="ghp_...")
        result = etl.fetch()
        # result.issues = classified open issues
        # result.closed_issues = recently closed issues
    """

    def __init__(self, config: Config, token: str | None = None):
        self.config = config
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        })
        if token:
            self.session.headers["Authorization"] = f"Bearer {token}"

        self._cache_dir = Path(config.cache_dir)
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    def fetch(
        self,
        include_closed: bool = True,
        closed_since_days: int = 90,
    ) -> FetchResult:
        """Fetch all open issues and optionally recent closed issues.

        Args:
            include_closed: Whether to also fetch recently closed issues.
            closed_since_days: How far back to look for closed issues.

        Returns:
            FetchResult with classified issues.
        """
        logger.info("Fetching open issues from %s...", self.config.repo)
        open_raw = self._fetch_all_issues(state="open")
        logger.info("Fetched %d open issues", len(open_raw))

        closed_raw = []
        if include_closed:
            logger.info("Fetching recently closed issues (last %d days)...", closed_since_days)
            closed_raw = self._fetch_recently_closed(since_days=closed_since_days)
            logger.info("Fetched %d recently closed issues", len(closed_raw))

        open_classified = [self._classify(raw) for raw in open_raw]
        closed_classified = [self._classify(raw) for raw in closed_raw]

        result = FetchResult(
            issues=open_classified,
            closed_issues=closed_classified,
            fetch_time=datetime.now(timezone.utc),
            repo=self.config.repo,
            total_open=len(open_classified),
            total_closed_recent=len(closed_classified),
        )

        self._save_cache(result)
        return result

    def load_cached(self, week_start: str | None = None) -> FetchResult | None:
        """Load issues from local cache.

        Args:
            week_start: Optional YYYY-MM-DD date string. If None, loads the most recent cache.

        Returns:
            FetchResult if cache exists, None otherwise.
        """
        if week_start:
            cache_file = self._cache_dir / f"issues_{week_start}.json"
        else:
            # Find most recent cache file
            cache_files = sorted(self._cache_dir.glob("issues_*.json"), reverse=True)
            if not cache_files:
                return None
            cache_file = cache_files[0]

        if not cache_file.exists():
            return None

        logger.info("Loading cached issues from %s", cache_file)
        with open(cache_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        issues = [self._dict_to_classified(d) for d in data.get("issues", [])]
        closed = [self._dict_to_classified(d) for d in data.get("closed_issues", [])]

        return FetchResult(
            issues=issues,
            closed_issues=closed,
            fetch_time=datetime.fromisoformat(data["fetch_time"]),
            repo=data["repo"],
            total_open=len(issues),
            total_closed_recent=len(closed),
            from_cache=True,
        )

    # ── Internal fetchers ─────────────────────────────────────────────

    def _fetch_all_issues(self, state: str = "open") -> list[dict]:
        """Paginated fetch of all issues (excluding PRs) with rate limit handling."""
        all_issues = []
        page = 1

        while True:
            url = f"{GITHUB_API}/repos/{self.config.repo}/issues"
            params = {
                "state": state,
                "per_page": PER_PAGE,
                "page": page,
                "sort": "created",
                "direction": "asc",
            }

            resp = self._api_get(url, params)
            if resp is None:
                break

            items = resp.json()
            if not items:
                break

            # Filter out pull requests (GitHub API returns PRs mixed with issues)
            for item in items:
                if "pull_request" not in item:
                    all_issues.append(item)

            logger.debug("Page %d: %d items (%d total)", page, len(items), len(all_issues))
            page += 1

            # Respect rate limits
            remaining = int(resp.headers.get("X-RateLimit-Remaining", 100))
            if remaining < 10:
                reset_at = int(resp.headers.get("X-RateLimit-Reset", 0))
                wait = max(0, reset_at - int(time.time())) + 1
                logger.warning("Rate limit low (%d remaining). Waiting %ds...", remaining, wait)
                time.sleep(wait)

        return all_issues

    def _fetch_recently_closed(self, since_days: int = 90) -> list[dict]:
        """Fetch issues closed within the last N days."""
        since = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        since = since.replace(day=max(1, since.day))  # safety
        from datetime import timedelta

        since = since - timedelta(days=since_days)
        since_str = since.strftime("%Y-%m-%dT%H:%M:%SZ")

        all_closed = []
        page = 1

        while True:
            url = f"{GITHUB_API}/repos/{self.config.repo}/issues"
            params = {
                "state": "closed",
                "since": since_str,
                "per_page": PER_PAGE,
                "page": page,
                "sort": "updated",
                "direction": "desc",
            }

            resp = self._api_get(url, params)
            if resp is None:
                break

            items = resp.json()
            if not items:
                break

            for item in items:
                if "pull_request" not in item:
                    all_closed.append(item)

            page += 1

            remaining = int(resp.headers.get("X-RateLimit-Remaining", 100))
            if remaining < 10:
                reset_at = int(resp.headers.get("X-RateLimit-Reset", 0))
                wait = max(0, reset_at - int(time.time())) + 1
                logger.warning("Rate limit low. Waiting %ds...", wait)
                time.sleep(wait)

        return all_closed

    def _api_get(
        self, url: str, params: dict | None = None, max_retries: int = 3
    ) -> requests.Response | None:
        """GET with retry and rate limit handling."""
        for attempt in range(max_retries):
            try:
                resp = self.session.get(url, params=params, timeout=30)

                if resp.status_code == 200:
                    return resp
                elif resp.status_code == 403:
                    # Rate limited
                    reset_at = int(resp.headers.get("X-RateLimit-Reset", 0))
                    wait = max(0, reset_at - int(time.time())) + RATE_LIMIT_PAUSE
                    logger.warning("Rate limited (403). Waiting %ds...", wait)
                    time.sleep(wait)
                elif resp.status_code == 404:
                    logger.error("Repository not found: %s", self.config.repo)
                    return None
                else:
                    logger.warning(
                        "API error %d on attempt %d: %s",
                        resp.status_code,
                        attempt + 1,
                        resp.text[:200],
                    )
                    time.sleep(2**attempt)

            except requests.RequestException as e:
                logger.warning("Request failed on attempt %d: %s", attempt + 1, e)
                time.sleep(2**attempt)

        logger.error("All %d retries exhausted for %s", max_retries, url)
        return None

    # ── Classification ────────────────────────────────────────────────

    def _classify(self, raw: dict) -> ClassifiedIssue:
        """Classify a raw GitHub API issue dict into a structured ClassifiedIssue."""
        now = datetime.now(timezone.utc)

        labels = [lbl["name"] for lbl in raw.get("labels", [])]
        body = raw.get("body", "") or ""

        created = _parse_dt(raw.get("created_at"))
        updated = _parse_dt(raw.get("updated_at"))
        closed = _parse_dt(raw.get("closed_at")) if raw.get("closed_at") else None

        age_days = (now - created).total_seconds() / 86400 if created else 0

        has_tid, tid_type = self.config.has_tracking_id(body)

        reactions = raw.get("reactions", {})
        reaction_count = sum(
            reactions.get(k, 0)
            for k in ["total_count", "+1", "-1", "laugh", "hooray", "confused", "heart", "rocket", "eyes"]
            if k == "total_count"
        ) if isinstance(reactions, dict) else 0

        return ClassifiedIssue(
            number=raw["number"],
            title=raw.get("title", ""),
            state=raw.get("state", "open"),
            created_at=created or now,
            updated_at=updated or now,
            closed_at=closed,
            author=raw.get("user", {}).get("login", "unknown"),
            assignee=(raw.get("assignee") or {}).get("login"),
            labels=labels,
            area=self.config.classify_area(labels),
            issue_type=self.config.classify_type(labels),
            status=self.config.classify_status(labels),
            has_tracking_id=has_tid,
            tracking_type=tid_type,
            age_days=age_days,
            comment_count=raw.get("comments", 0),
            reaction_count=reaction_count,
            url=raw.get("html_url", ""),
            body_snippet=body[:200] if body else "",
        )

    # ── Caching ───────────────────────────────────────────────────────

    def _save_cache(self, result: FetchResult):
        """Save fetch result to local JSON cache."""
        date_str = result.fetch_time.strftime("%Y-%m-%d")
        cache_file = self._cache_dir / f"issues_{date_str}.json"

        data = {
            "repo": result.repo,
            "fetch_time": result.fetch_time.isoformat(),
            "total_open": result.total_open,
            "total_closed_recent": result.total_closed_recent,
            "issues": [i.to_dict() for i in result.issues],
            "closed_issues": [i.to_dict() for i in result.closed_issues],
        }

        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)

        logger.info("Cached %d issues to %s", len(result.issues), cache_file)

    def _dict_to_classified(self, d: dict) -> ClassifiedIssue:
        """Reconstruct a ClassifiedIssue from a cached dict."""
        return ClassifiedIssue(
            number=d["number"],
            title=d["title"],
            state=d["state"],
            created_at=_parse_dt(d["created_at"]) or datetime.now(timezone.utc),
            updated_at=_parse_dt(d["updated_at"]) or datetime.now(timezone.utc),
            closed_at=_parse_dt(d["closed_at"]) if d.get("closed_at") else None,
            author=d["author"],
            assignee=d.get("assignee"),
            labels=d["labels"],
            area=d["area"],
            issue_type=d["issue_type"],
            status=d["status"],
            has_tracking_id=d["has_tracking_id"],
            tracking_type=d.get("tracking_type"),
            age_days=d["age_days"],
            comment_count=d["comment_count"],
            reaction_count=d["reaction_count"],
            url=d["url"],
            body_snippet=d.get("body_snippet", ""),
        )


# ── Utilities ─────────────────────────────────────────────────────

def _parse_dt(s: str | None) -> datetime | None:
    """Parse an ISO 8601 datetime string."""
    if not s:
        return None
    try:
        # Handle GitHub's "2024-01-15T10:30:00Z" format
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        return datetime.fromisoformat(s)
    except (ValueError, TypeError):
        return None
