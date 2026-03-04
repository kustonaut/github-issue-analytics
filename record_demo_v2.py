"""
Playwright demo recorder for GitHub Issue Analytics v0.2.0.
Records a ~40-second browser walkthrough of the v2-demo.html page.
The page auto-loads demo data with Chart.js charts — no fetch needed.

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

HEADED = "--headed" in sys.argv


async def main():
    print(f"[1/4] Launching browser ({'headed' if HEADED else 'headless'})...")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=not HEADED)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            record_video_dir=str(SCRIPT_DIR / "_video_tmp"),
            record_video_size={"width": 1280, "height": 800},
        )
        page = await context.new_page()

        # ── Scene 1: Open demo page (auto-loads Chart.js dashboard) ──
        print("[2/4] Opening v0.2.0 demo page (auto-loads demo data)...")
        demo_url = DEMO_HTML.as_uri()
        await page.goto(demo_url)
        await page.wait_for_load_state("networkidle")
        await asyncio.sleep(3)  # Let hero animations + Chart.js render complete

        # ── Scene 2: Scroll through dashboard sections ──
        print("[3/4] Scrolling through dashboard sections...")

        # SHS Gauge (animated arc fill)
        await page.locator("#shsSection").scroll_into_view_if_needed()
        await asyncio.sleep(2.5)

        # Lifecycle Funnel (trapezoid segments with reveal animation)
        await page.locator("#lifecycleSection").scroll_into_view_if_needed()
        await asyncio.sleep(2.5)

        # Classic Funnel (trapezoid segments)
        await page.locator("#funnelSection").scroll_into_view_if_needed()
        await asyncio.sleep(2)

        # Donut (Chart.js doughnut) + Age (Chart.js bar) — side by side
        await page.locator("#donutSection").scroll_into_view_if_needed()
        await asyncio.sleep(2.5)

        # Heatmap (severity-colored table)
        await page.locator("#heatmapSection").scroll_into_view_if_needed()
        await asyncio.sleep(2)

        # Click first heatmap row to show active state
        rows = page.locator(".heatmap-row")
        if await rows.count() > 0:
            await rows.first.click()
            await asyncio.sleep(1)

        # Sparkline (Chart.js line chart with area fill)
        await page.locator("#sparkSection").scroll_into_view_if_needed()
        await asyncio.sleep(2)

        # KPIs (card grid)
        await page.locator("#kpiGrid").scroll_into_view_if_needed()
        await asyncio.sleep(2)

        # Features grid (if present)
        features = page.locator(".features-grid")
        if await features.count() > 0:
            await features.scroll_into_view_if_needed()
            await asyncio.sleep(2)

        # ── Scene 3: Scroll back to top ──
        await page.evaluate("window.scrollTo({top:0, behavior:'smooth'})")
        await asyncio.sleep(2)

        # ── Done: Save video ──
        print("[4/4] Saving video...")
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
