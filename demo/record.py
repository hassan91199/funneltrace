"""Step 2: drive the real UI through the demo story while recording it.

Needs the stack running (API + frontend + a database the API points at) and the
narration already built. Holds each scene until its narration has finished and the
real work (scoring, drafting, CRM sync) has completed, and writes build/cues.json:
when each scene's narration should start, on the recording's own clock.

Env: API_URL (default http://localhost:8010), WEB_URL (default http://localhost:3010).
"""
import json
import os
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).parent
BUILD = HERE / "build"
API = os.environ.get("API_URL", "http://localhost:8010")
WEB = os.environ.get("WEB_URL", "http://localhost:3010")
SIZE = {"width": 1440, "height": 900}

CURSOR = """
window.addEventListener('DOMContentLoaded', () => {
  const dot = document.createElement('div');
  dot.style.cssText = 'position:fixed;z-index:99999;width:18px;height:18px;border-radius:50%;' +
    'background:rgba(255,200,0,.85);border:2px solid #fff;box-shadow:0 0 0 3px rgba(0,0,0,.35);' +
    'pointer-events:none;left:-40px;top:-40px;transform:translate(-50%,-50%)';
  document.body.appendChild(dot);
  window.addEventListener('mousemove', e => { dot.style.left = e.clientX + 'px'; dot.style.top = e.clientY + 'px'; }, true);
});
"""


def event_counts() -> dict:
    with urllib.request.urlopen(f"{API}/events?follow=false", timeout=10) as resp:
        text = resp.read().decode()
    counts: dict = {}
    for line in text.splitlines():
        if line.startswith("event: "):
            counts[line[7:]] = counts.get(line[7:], 0) + 1
    return counts


def wait_for_count(kind: str, n: int, timeout: float = 60) -> None:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if event_counts().get(kind, 0) >= n:
            return
        time.sleep(0.3)
    raise SystemExit(f"timed out waiting for {n} x {kind}: {event_counts()}")


def main() -> None:
    narration = {s["id"]: s for s in json.loads((BUILD / "narration.json").read_text())}
    if event_counts():
        raise SystemExit("the API's database already has trace events; point it at an empty one")
    cues: dict = {}
    (BUILD / "shots").mkdir(exist_ok=True)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path="/usr/bin/google-chrome", headless=True)
        context = browser.new_context(
            viewport=SIZE, record_video_dir=str(BUILD / "raw"), record_video_size=SIZE,
            color_scheme="dark",
        )
        context.add_init_script(CURSOR)
        page = context.new_page()
        t0 = time.monotonic()  # the video's clock starts when the page is created
        now = lambda: time.monotonic() - t0  # noqa: E731

        def move_to(locator) -> None:
            box = locator.bounding_box()
            page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2, steps=30)

        def start(scene: str, lead: float = 0.0) -> float:
            cues[scene] = {"start": now() + lead}
            return time.monotonic() + lead

        def finish(scene: str) -> None:
            """Hold until the narration is done, plus a beat to read the screen."""
            end_at = t0 + cues[scene]["start"] + narration[scene]["seconds"] + 1.0
            time.sleep(max(0, end_at - time.monotonic()))
            cues[scene]["end"] = now()

        def shot(name: str) -> None:
            page.screenshot(path=str(BUILD / "shots" / f"{name}.png"))

        def click_button(name: str) -> None:
            button = page.get_by_role("button", name=name, exact=True)
            move_to(button)
            time.sleep(0.25)
            button.click()

        page.goto(WEB)
        page.get_by_text("Live", exact=True).wait_for()
        time.sleep(1.0)

        start("intro")
        shot("00-empty")
        finish("intro")

        start("form", lead=0.6)
        click_button("Hot: Sarah, form (furnace out)")
        wait_for_count("drafted", 1)
        page.locator(".card").first.wait_for()
        time.sleep(0.5)
        shot("01-scored-and-drafted")
        finish("form")

        start("merge", lead=0.6)
        click_button("Same person: Sarah, WhatsApp (merges)")
        wait_for_count("drafted", 2)
        time.sleep(1.0)
        shot("02-cross-channel-merge")
        finish("merge")

        start("approve", lead=0.6)
        time.sleep(2.0)
        click_button("Approve")
        wait_for_count("crm_synced", 1)
        time.sleep(1.0)
        shot("03-approved-and-synced")
        finish("approve")

        start("cold", lead=0.6)
        click_button("Cold: Jason, form (SEO vendor)")
        wait_for_count("drafted", 3)
        time.sleep(2.5)
        shot("04-cold-lead")
        click_button("Reject")
        wait_for_count("draft_rejected", 1)
        finish("cold")

        start("outro", lead=0.6)
        page.get_by_label("Lead").select_option(label="Sarah Mitchell")
        time.sleep(1.0)
        shot("05-lead-journey")
        finish("outro")
        time.sleep(0.6)

        video = page.video.path()
        context.close()
        browser.close()

    final = Path(video).rename(BUILD / "raw.webm")
    cues["_duration"] = now()
    cues["_counts"] = event_counts()
    (BUILD / "cues.json").write_text(json.dumps(cues, indent=2))
    print(f"recorded {final} ({cues['_duration']:.1f}s)  events: {cues['_counts']}")


if __name__ == "__main__":
    main()
