"""
Playwright demo recorder for GitHub Issue Analytics v0.2.0.
Records a 45-second browser walkthrough of the v2-demo.html page,
then outputs demo-video-v2.mp4.

Usage:
    python record_demo_v2.py [--headed]

Prerequisites:
    pip install playwright
    playwright install chromium
"""
import asyncio
import sys
import os
from pathlib import Path
from playwright.async_api import async_playwright

SCRIPT_DIR = Path(__file__).parent
DEMO_HTML = SCRIPT_DIR / "docs" / "v2-demo.html"
OUTPUT_VIDEO = SCRIPT_DIR / "demo-video-v2.mp4"

# Demo repo to analyze (small enough to load fast, big enough to show data)
DEMO_REPO = "pallets/flask"

HEADED = "--headed" in sys.argv


async def main():
    print(f"[1/5] Launching browser ({'headed' if HEADED else 'headless'})...")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=not HEADED)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            record_video_dir=str(SCRIPT_DIR / "_video_tmp"),
            record_video_size={"width": 1280, "height": 800},
        )
        page = await context.new_page()

        # ── Scene 1: Open demo page ──
        print("[2/5] Opening v0.2.0 demo page...")
        demo_url = DEMO_HTML.as_uri()
        await page.goto(demo_url)
        await page.wait_for_load_state("networkidle")
        await asyncio.sleep(2)  # Show the hero + What's New banner

        # ── Scene 2: Type repo and analyze ──
        print(f"[3/5] Analyzing {DEMO_REPO}...")
        repo_input = page.locator("#repoInput")
        await repo_input.click()
        await asyncio.sleep(0.5)

        # Type with realistic speed
        for char in DEMO_REPO:
            await repo_input.type(char, delay=80)
        await asyncio.sleep(0.5)

        # Click Analyze
        await page.locator("#analyzeBtn").click()
        await asyncio.sleep(1)

        # Wait for dashboard to appear (max 60s)
        print("[3/5] Waiting for analysis to complete...")
        try:
            await page.locator("#dashboard").wait_for(state="visible", timeout=60000)
        except Exception:
            print("  WARNING: Dashboard didn't appear in 60s, continuing...")
        await asyncio.sleep(2)

        # ── Scene 3: Scroll through dashboard sections ──
        print("[4/5] Scrolling through dashboard sections...")

        # SHS Gauge
        await page.locator("#shsSection").scroll_into_view_if_needed()
        await asyncio.sleep(2)

        # Lifecycle Funnel (NEW)
        await page.locator("#lifecycleSection").scroll_into_view_if_needed()
        await asyncio.sleep(2.5)

        # Classic Funnel
        await page.locator("#funnelSection").scroll_into_view_if_needed()
        await asyncio.sleep(1.5)

        # Donut + Age
        await page.locator("#donutSection").scroll_into_view_if_needed()
        await asyncio.sleep(2)

        # Heatmap (Enhanced)
        await page.locator("#heatmapSection").scroll_into_view_if_needed()
        await asyncio.sleep(2.5)

        # Click first heatmap row to show active state
        rows = page.locator(".heatmap-row")
        if await rows.count() > 0:
            await rows.first.click()
            await asyncio.sleep(1)

        # Sparkline
        await page.locator("#sparkSection").scroll_into_view_if_needed()
        await asyncio.sleep(2)

        # KPIs
        await page.locator("#kpiGrid").scroll_into_view_if_needed()
        await asyncio.sleep(2)

        # Features grid
        features = page.locator(".features-grid")
        if await features.count() > 0:
            await features.scroll_into_view_if_needed()
            await asyncio.sleep(2)

        # ── Scene 4: Scroll back to top ──
        await page.evaluate("window.scrollTo({top:0, behavior:'smooth'})")
        await asyncio.sleep(2)

        # ── Done: Save video ──
        print("[5/5] Saving video...")
        await context.close()
        await browser.close()

    # Move the video file from temp dir
    tmp_dir = SCRIPT_DIR / "_video_tmp"
    if tmp_dir.exists():
        videos = list(tmp_dir.glob("*.webm"))
        if videos:
            src = videos[0]
            # Try to convert with ffmpeg if available, otherwise just rename
            try:
                import subprocess
                import shutil
                ffmpeg_bin = shutil.which("ffmpeg")
                if not ffmpeg_bin:
                    try:
                        import static_ffmpeg
                        static_ffmpeg.add_paths()
                        ffmpeg_bin = shutil.which("ffmpeg")
                    except ImportError:
                        pass
                if not ffmpeg_bin:
                    raise FileNotFoundError("ffmpeg")
                result = subprocess.run(
                    [ffmpeg_bin, "-y", "-i", str(src), "-c:v", "libx264", "-preset", "fast",
                     "-crf", "23", "-pix_fmt", "yuv420p", str(OUTPUT_VIDEO)],
                    capture_output=True, text=True, timeout=120
                )
                if result.returncode == 0:
                    print(f"  Converted to MP4: {OUTPUT_VIDEO}")
                    src.unlink()
                else:
                    # Fallback: copy as webm
                    webm_out = OUTPUT_VIDEO.with_suffix(".webm")
                    src.rename(webm_out)
                    print(f"  ffmpeg failed, saved as WebM: {webm_out}")
                    print(f"  ffmpeg stderr: {result.stderr[:200]}")
            except FileNotFoundError:
                webm_out = OUTPUT_VIDEO.with_suffix(".webm")
                src.rename(webm_out)
                print(f"  ffmpeg not found, saved as WebM: {webm_out}")

        # Cleanup temp dir
        try:
            tmp_dir.rmdir()
        except OSError:
            pass

    print("\nDone! Demo video recorded.")


if __name__ == "__main__":
    asyncio.run(main())
