# LinkedIn Post — github-issue-analytics

## Hook Type: Build in Public / Day 2 — Sequel to Issue Sentinel

---

Yesterday I shared how I built Issue Sentinel to auto-classify GitHub issues. That solved triage. But it didn't answer the harder question: where are issues actually piling up?

Classification tells you what each issue is. Analytics tells you what's going wrong.

So I built the second tool in the series — GitHub Issue Analytics. Here's what 6,000+ issues across real repos taught me:

1. A single health score changes behavior.
I computed a "Stale Health Score" (0–100) combining resolution rate, median age, and stale ratio. One number. When teams see 34/100, they don't debate priority — they act. Dashboards with 20 charts get ignored. One gauge gets action.

2. The funnel is where problems hide.
Open → In Progress → Resolved → Closed. Simple, right? Except most repos have a massive gap between Open and In Progress. Visualizing that funnel exposed bottlenecks no metric table ever surfaced. The drop-off IS the insight.

3. Label heatmaps reveal team blind spots.
Plotting issues by label × month showed that some labels (like "needs-investigation") were graveyards — issues went in, never came out. No one noticed because each issue looked fine in isolation. The pattern only appeared in aggregate.

4. Browser-only beats backend every time.
The live demo runs 100% client-side. Paste a repo, hit Analyze — it calls the GitHub API directly from your browser. Zero backend. Zero auth required for public repos. Removing infrastructure removed adoption friction.

5. 500 lines of Python, not 5,000.
The core library is under 500 lines — ETL, 13 metrics, dashboard generation. I kept fighting the urge to add features. Every line I didn't write is a line nobody has to maintain. Constraint is a feature.

6. Day 1 was classification. Day 2 is visibility.
Issue Sentinel tells you WHAT each issue is. GitHub Issue Analytics tells you WHERE your repo is failing. Triage without analytics is firefighting. Analytics without triage is just charts. Together, they're a system.

The tool: GitHub Issue Analytics
→ 13 metrics: health score, resolution rate, age distribution, label heatmaps, time-series trends
→ One `pip install`. One YAML config. Full dashboard.
→ Live demo — paste any public repo, get the dashboard in seconds.

It's MIT licensed and live:
🔗 github.com/kustonaut/github-issue-analytics
🎮 Try it: kustonaut.github.io/github-issue-analytics

Day 1: classify. Day 2: analyze. Day 3... automate the response. Stay tuned.

What metric do you wish your issue tracker showed you?

#OpenSource #BuildInPublic #ProductManagement #GitHubAnalytics #DevTools #Python #LessonsLearned

---

## Posting Checklist
- [ ] Attach `demo-video.mp4` (60s, 2x speed, 2.8 MB) as native video
- [ ] Post between 8–10 AM IST (Tue/Wed optimal — today is Tue!)
- [ ] Reference yesterday's Issue Sentinel post in first comment: "This is Day 2 of the series. Day 1 (Issue Sentinel) is here: [link to yesterday's post]"
- [ ] Second comment: "The entire demo page is a single HTML file with zero external dependencies. No React, no build step."
- [ ] Reply to first 5 comments within 1 hour (algorithm boost)
- [ ] If yesterday's post is still getting engagement, cross-link in a comment there too

## Video Location
`demo-video.mp4` — same folder as this file (2.8 MB, 60s at 2x speed)

## Series Arc
- Day 1 (posted): Issue Sentinel — classify issues (rule-based + LLM hybrid)
- Day 2 (this post): GitHub Issue Analytics — visualize & measure repo health
- Day 3 (upcoming): TBD — automate response / close-the-loop tool
