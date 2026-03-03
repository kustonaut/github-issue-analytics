"""
Record a demo video of GitHub Issue Analytics using Playwright.

Single-repo flow (~45s):
  1. Hero — title, badges, input (3s)
  2. Click "Live Demo" pill → pallets/flask (1s)
  3. Progress bar fetching issues (wait for completion)
  4. SHS gauge animates (4s)
  5. Issue Funnel + hover tooltips (5s)
  6. Donut + Age charts (5s)
  7. Label Heatmap + click rows (5s)
  8. Sparkline + KPIs (4s)
  9. Scroll back to top — end (3s)

Post-processing (requires ffmpeg):
  ffmpeg -i demo-video.webm -c:v libx264 -crf 23 demo-video.mp4
"""

import os
import sys
import time
import threading
import http.server
import shutil
import subprocess

from playwright.sync_api import sync_playwright


def get_gh_token():
    """Get GitHub token from env or gh CLI."""
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token:
        return token
    try:
        result = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, timeout=5)
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception:
        pass
    return ""

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
DOCS_DIR = os.path.join(PROJECT_DIR, "docs")
VIDEO_DIR = os.path.join(os.environ.get("TEMP", PROJECT_DIR), "gia_recording")
OUTPUT_PATH = os.path.join(PROJECT_DIR, "demo-video.webm")

WIDTH = 1280
HEIGHT = 720
SERVER_PORT = 9123


# ── Helpers ───────────────────────────────────────────

def start_local_server():
    class QuietHandler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=DOCS_DIR, **kwargs)

        def log_message(self, format, *args):
            pass  # suppress HTTP logs

    httpd = http.server.HTTPServer(("127.0.0.1", SERVER_PORT), QuietHandler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd


def slow_type(page, selector, text, delay=70):
    page.focus(selector)
    for ch in text:
        page.keyboard.type(ch, delay=delay)


def smooth_scroll(page, target_y, steps=20, delay=40):
    cur = page.evaluate("window.scrollY")
    step = (target_y - cur) / steps
    for i in range(steps):
        page.evaluate(f"window.scrollTo(0, {int(cur + step * (i + 1))})")
        time.sleep(delay / 1000)


def scroll_to(page, selector, offset=-80, steps=25):
    """Scroll element into view. Returns True if element exists."""
    exists = page.evaluate(f"!!document.querySelector('{selector}')")
    if not exists:
        print(f"    ⚠ selector '{selector}' not found, skipping")
        return False
    target = page.evaluate(f"""
        (() => {{
            const el = document.querySelector('{selector}');
            return el.getBoundingClientRect().top + window.scrollY + ({offset});
        }})()
    """)
    smooth_scroll(page, int(target), steps=steps)
    return True


# ── Main Recording ────────────────────────────────────

def main():
    print(f"Serving docs/ on http://127.0.0.1:{SERVER_PORT}")
    httpd = start_local_server()
    demo_url = f"http://127.0.0.1:{SERVER_PORT}/index.html"

    os.makedirs(VIDEO_DIR, exist_ok=True)
    # Clean old recordings
    for f in os.listdir(VIDEO_DIR):
        if f.endswith(".webm"):
            os.remove(os.path.join(VIDEO_DIR, f))

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        ctx = browser.new_context(
            viewport={"width": WIDTH, "height": HEIGHT},
            record_video_dir=VIDEO_DIR,
            record_video_size={"width": WIDTH, "height": HEIGHT},
            device_scale_factor=1,
        )
        page = ctx.new_page()

        # Capture console for debugging
        page.on("console", lambda msg: (
            print(f"    [browser {msg.type}] {msg.text}")
            if msg.type in ("error", "warning") else None
        ))
        page.on("pageerror", lambda err: print(f"    [PAGE ERROR] {err}"))

        page.goto(demo_url, wait_until="networkidle")
        print("Page loaded.\n")

        # ── 1. Hero ───────────────────────────────────────
        print("[1/9] Hero — title, input, badges...")
        time.sleep(3)

        # ── 2. Inject token + Click Live Demo pill ────────
        token = get_gh_token()
        if token:
            print(f"    Injecting GH token ({len(token)} chars) for 5000 req/hr...")
            page.evaluate(f"document.getElementById('ghToken').value = '{token}'")
        else:
            print("    ⚠ No GH token — using unauthenticated API (60 req/hr)")

        print("[2/9] Clicking Live Demo pill (pallets/flask)...")
        # Set repo input and trigger analysis directly via JS
        # (dispatchEvent('submit') doesn't reliably fire onsubmit handler)
        page.evaluate("document.getElementById('repoInput').value = 'pallets/flask'")
        time.sleep(0.3)
        page.evaluate("startAnalysis(new Event('submit'))")
        time.sleep(1)

        # ── 3. Wait for dashboard ─────────────────────────
        print("[3/9] Waiting for issue fetch + dashboard render...")
        try:
            page.wait_for_function(
                """() => {
                    const d = document.getElementById('dashboard');
                    const s = document.getElementById('shsSection');
                    return d && d.style.display === 'block' && s && s.innerHTML.length > 20;
                }""",
                timeout=60000,
            )
            print("    Dashboard rendered!")
        except Exception:
            # Diagnose — guard against page already closed
            if page.is_closed():
                print("    ❌ Browser page crashed during fetch!")
                try:
                    ctx.close()
                except Exception:
                    pass
                browser.close()
                httpd.shutdown()
                return
            ds = page.evaluate("document.getElementById('dashboard')?.style.display || 'none'")
            ss = page.evaluate("document.getElementById('shsSection')?.innerHTML?.length || 0")
            eb = page.evaluate("document.getElementById('errorBanner')?.textContent || ''")
            print(f"    ⚠ Timeout! dashboard='{ds}', shsLen={ss}, error='{eb}'")
            if eb:
                print(f"\n❌ GitHub API error: {eb}")
                print("   Likely rate-limited. Wait a few minutes and retry.")
                ctx.close()
                browser.close()
                httpd.shutdown()
                return
        time.sleep(2)

        # ── 4. SHS Gauge ─────────────────────────────────
        print("[4/9] SHS gauge animating...")
        scroll_to(page, "#shsSection", offset=-30)
        time.sleep(4)

        # ── 5. Issue Funnel ───────────────────────────────
        print("[5/9] Issue Funnel + hover tooltips...")
        if scroll_to(page, "#funnelSection", offset=-30):
            time.sleep(1.5)
            stages = page.query_selector_all(".funnel-stage")
            for s in stages[:4]:
                s.hover()
                time.sleep(0.7)
            time.sleep(0.5)

        # ── 6. Donut + Age ────────────────────────────────
        print("[6/9] Donut + Age charts...")
        if scroll_to(page, "#donutSection", offset=-30):
            time.sleep(1.5)
            segs = page.query_selector_all(".donut-seg")
            for s in segs[:3]:
                s.hover()
                time.sleep(0.6)
        scroll_to(page, "#ageSection", offset=-80)
        time.sleep(2)

        # ── 7. Heatmap ───────────────────────────────────
        print("[7/9] Label Heatmap...")
        if scroll_to(page, "#heatmapSection", offset=-30):
            time.sleep(1)
            rows = page.query_selector_all(".heatmap-row")
            if rows:
                rows[0].click()
                time.sleep(1)
            if len(rows) > 2:
                rows[2].click()
                time.sleep(1)

        # ── 8. Sparkline + KPIs ───────────────────────────
        print("[8/9] Sparkline + KPIs...")
        scroll_to(page, "#sparkSection", offset=-30)
        time.sleep(2)
        scroll_to(page, "#kpiGrid", offset=-50)
        time.sleep(2.5)

        # ── 9. Back to top ────────────────────────────────
        print("[9/9] Scrolling back to top...")
        smooth_scroll(page, 0, steps=30, delay=45)
        time.sleep(3)

        # ── Done ──────────────────────────────────────────
        print("\nRecording complete. Closing browser...")
        ctx.close()
        browser.close()

    httpd.shutdown()

    # Find and move the auto-generated .webm
    webm_files = sorted(
        [f for f in os.listdir(VIDEO_DIR) if f.endswith(".webm")],
        key=lambda f: os.path.getmtime(os.path.join(VIDEO_DIR, f)),
        reverse=True,
    )
    if webm_files:
        src = os.path.join(VIDEO_DIR, webm_files[0])
        if os.path.exists(OUTPUT_PATH):
            os.remove(OUTPUT_PATH)
        shutil.move(src, OUTPUT_PATH)
        size_mb = os.path.getsize(OUTPUT_PATH) / (1024 * 1024)
        print(f"\n✅ Video saved: {OUTPUT_PATH}")
        print(f"   Size: {size_mb:.1f} MB")
    else:
        print("⚠ No .webm found in recording dir")


if __name__ == "__main__":
    main()
