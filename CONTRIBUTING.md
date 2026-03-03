# Contributing to GitHub Issue Analytics

Thank you for your interest in contributing! This project follows a focused,
quality-first development process.

## Getting Started

1. **Fork** the repository
2. **Clone** your fork:
   ```bash
   git clone https://github.com/YOUR_USERNAME/github-issue-analytics.git
   cd github-issue-analytics
   ```
3. **Install** in development mode:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # Windows: .venv\Scripts\activate
   pip install -e ".[dev]"
   ```
4. **Run tests** to verify:
   ```bash
   pytest tests/ -v
   ```

## Development Workflow

### Branch Naming

- `feat/description` — new features
- `fix/description` — bug fixes
- `docs/description` — documentation
- `refactor/description` — code improvements

### Code Quality

This project uses **ruff** for linting and formatting:

```bash
# Check
ruff check src/ tests/
ruff format --check src/ tests/

# Auto-fix
ruff check --fix src/ tests/
ruff format src/ tests/
```

### Tests

All changes must include tests. Run:

```bash
pytest tests/ -v --tb=short
```

### Commit Messages

Follow conventional commits:
- `feat: add time-to-close metric`
- `fix: handle empty label lists in classify_area`
- `docs: add config reference for tracking patterns`
- `test: add edge case for zero-issue backlog`
- `refactor: extract age calculation to utility`

## Architecture

```
src/github_issue_analytics/
├── config.py       # YAML config → dataclasses
├── etl.py          # GitHub REST API → ClassifiedIssue
├── metrics.py      # 13-metric calculation engine
├── analyzer.py     # High-level facade (orchestrates everything)
├── reporter.py     # Markdown report generator
├── dashboard.py    # HTML dashboard generator
├── trends.py       # WoW trend storage & analysis
└── cli.py          # Click CLI (`gia` command)
```

### Key Design Decisions

1. **Config-driven** — All label mappings, thresholds, and rules live in YAML.
   No hardcoded repository-specific logic in any module.

2. **Dataclass-first** — Intermediate data uses frozen/typed dataclasses,
   not raw dicts. This catches errors early and documents structure.

3. **No external dashboard deps** — The HTML dashboard is self-contained
   (no Chart.js, no CDN). Works offline, renders in any browser.

4. **Pure `requests`** — No dependency on `gh` CLI or other GitHub tools.
   Only the GitHub REST API via `requests`.

## Pull Request Process

1. Create a branch from `main`
2. Make your changes with tests
3. Run `ruff check` and `pytest`
4. Submit a PR with a clear description
5. Wait for CI to pass and a maintainer review

## Reporting Issues

- Use GitHub Issues
- Include: Python version, OS, config snippet, error message
- Label appropriately: `bug`, `feature-request`, `docs`

## License

By contributing, you agree that your contributions will be licensed
under the MIT License.
