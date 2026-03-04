# LinkedIn Post — github-issue-analytics v0.2.0

## Hook Type: Build in Public / Day 3 — Ship the Hard Parts

---

Two days ago I shared GitHub Issue Analytics — 13 metrics, one health score, zero backend. The response was incredible.

But when I used it on repos with 2,000+ issues, two things bothered me:

I couldn't see WHERE issues pile up across labels.
I couldn't see WHERE they get stuck in the lifecycle.

Tables and gauges tell you a repo is unhealthy. They don't tell you WHY.

So for v0.2.0, I built two new visualizations that do.

**1. Area Heatmap — 7 metrics × every label, severity-colored.**

Each cell shows one number. Green means healthy. Amber means watch it. Red means act now.

I stared at the Flask repo for 5 minutes and immediately saw: "type-bug" had a 0.91 stale ratio (red). "type-feature" had zero resolution (red). These aren't surprises — but seeing them side by side in one view is different from knowing about them individually.

The Python module (`gia heatmap`) generates a matplotlib PNG you can drop into any report or Slack message. The browser demo colors cells in real time.

**2. Lifecycle Funnel — INTAKE → TRIAGE → ACTIVE → CLOSING.**

Every repo has a conversion problem. Most just don't know which stage.

The funnel shows 4 stages with drop-off percentages between each. In Flask, 67% of issues make it past Triage — but only 12% reach the Closing stage. That gap between Active and Closing? That's your bottleneck.

Green/amber/red thresholds at each stage. One glance. Zero interpretation required.

**The constraint that changed everything:**

Both modules are optional. `pip install github-issue-analytics` gives you the core 13 metrics. Add `[viz]` for matplotlib heatmaps and funnels. The library never forces a dependency you don't need.

I kept the CLI dead simple:
```
gia analyze pallets/flask
gia heatmap pallets/flask --output flask-heat.png
gia funnel pallets/flask --output flask-funnel.png
```

Three commands. Full visibility.

**What I learned building v0.2.0:**

→ Severity coloring (green/amber/red) communicates faster than numbers. Always.
→ Drop-off rates are more useful than totals. "67% → 12%" tells a story. "4,200 active issues" doesn't.
→ Optional dependencies are a form of respect for your users.
→ The best feature is the one that makes you say "oh, THAT's why" in 5 seconds.

**Try it live:** Paste any public repo into the demo page. The heatmap and funnel render in your browser. No backend. No auth.

🔗 Repo: github.com/kustonaut/github-issue-analytics
🎮 Demo: kustonaut.github.io/github-issue-analytics/v2-demo.html
📦 Install: `pip install github-issue-analytics[viz]`

Day 1: classify (Issue Sentinel). Day 2: measure (13 metrics). Day 3: see (heatmaps + funnels).

Day 4? Automate the response. The system closes the loop.

What's the one visualization you wish your issue tracker had?

#OpenSource #BuildInPublic #ProductManagement #GitHubAnalytics #DevTools #Python #DataViz

---

## Posting Checklist
- [ ] Attach `demo-video-v2-narrated.mp4` (narrated walkthrough, ~3 MB) as native video
- [ ] Post between 8–10 AM IST (Wed/Thu optimal)
- [ ] First comment: "This is Day 3 of the series. Day 1 (Issue Sentinel): [link]. Day 2 (GitHub Issue Analytics): [link]."
- [ ] Second comment: "The heatmap module is 259 lines. The funnel module is 227 lines. Both have full test coverage. Sometimes less code = more insight."
- [ ] Reply to first 5 comments within 1 hour (algorithm boost)
- [ ] Cross-link from Day 2 post if still getting engagement

## Video Location
`demo-video-v2-narrated.mp4` — same folder as this file (~3 MB with TTS voiceover)

## Series Arc
- Day 1 (posted): Issue Sentinel — classify issues (rule-based + LLM hybrid)
- Day 2 (posted): GitHub Issue Analytics v0.1.0 — 13 metrics, health score, zero backend
- Day 3 (this post): GitHub Issue Analytics v0.2.0 — area heatmaps + lifecycle funnels
- Day 4 (upcoming): Close-the-loop automation
