"""Record the DrainWatch demo video (captions on screen, no audio).

Drives the running app in Microsoft Edge with Playwright, records each section,
then joins them into one MP4. A timings file is written next to the video so the
voice-over script can be matched to it.

    python demo/record_demo.py <app-url> <followup-inspection-id> <out-dir>
"""
import json
import os
import subprocess
import sys
import time
import urllib.request

import imageio_ffmpeg
from playwright.sync_api import sync_playwright

from cards import CARDS

W, H = 1280, 720
CAPTION_JS = """([text, chapter]) => {
  let c = document.getElementById('dw-cap');
  if (!c) {
    c = document.createElement('div'); c.id = 'dw-cap';
    c.style.cssText = 'position:fixed;left:50%;bottom:26px;transform:translateX(-50%);z-index:99999;max-width:1080px;' +
      'padding:14px 22px;border-radius:14px;background:rgba(9,24,34,.88);color:#fff;font:600 21px/1.4 "Plus Jakarta Sans",system-ui,sans-serif;' +
      'box-shadow:0 10px 30px rgba(0,0,0,.35);text-align:center;transition:opacity .25s';
    document.body.appendChild(c);
    const k = document.createElement('div'); k.id = 'dw-chap';
    k.style.cssText = 'position:fixed;right:22px;top:74px;z-index:99999;padding:6px 14px;border-radius:999px;' +
      'background:#0b7fb0;color:#fff;font:700 14px "Plus Jakarta Sans",system-ui,sans-serif;letter-spacing:.03em';
    document.body.appendChild(k);
  }
  c.textContent = text; c.style.opacity = text ? 1 : 0;
  const k = document.getElementById('dw-chap'); k.textContent = chapter || ''; k.style.display = chapter ? 'block' : 'none';
}"""
SCROLL_JS = """([target, ms]) => new Promise(done => {
  const start = window.scrollY, dist = target - start, t0 = performance.now();
  const ease = t => t < .5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;
  function step(now) {
    const t = Math.min(1, (now - t0) / ms);
    window.scrollTo(0, start + dist * ease(t));
    t < 1 ? requestAnimationFrame(step) : done();
  }
  requestAnimationFrame(step);
})"""


class Recorder:
    def __init__(self, browser, out_dir):
        self.browser, self.out_dir = browser, out_dir
        self.segments, self.timeline, self.offset = [], [], 0.0

    def segment(self, name, **ctx_kwargs):
        return Segment(self, name, ctx_kwargs)


class Segment:
    def __init__(self, rec, name, ctx_kwargs):
        self.rec, self.name, self.ctx_kwargs = rec, name, ctx_kwargs

    def __enter__(self):
        self.ctx = self.rec.browser.new_context(
            viewport={"width": W, "height": H}, record_video_dir=os.path.join(self.rec.out_dir, "raw"),
            record_video_size={"width": W, "height": H}, **self.ctx_kwargs)
        self.page = self.ctx.new_page()
        self.t0 = time.perf_counter()
        return self

    def now(self):
        return self.rec.offset + time.perf_counter() - self.t0

    def caption(self, text, chapter=None, hold=0.0):
        self.page.evaluate(CAPTION_JS, [text, chapter])
        self.rec.timeline.append({"t": round(self.now(), 1), "segment": self.name, "chapter": chapter, "caption": text})
        if hold:
            self.page.wait_for_timeout(int(hold * 1000))

    def scroll_to(self, selector, ms=1400, offset=86):
        loc = self.page.locator(selector).first
        loc.wait_for(state="attached", timeout=10000)
        y = loc.evaluate("(e, o) => e.getBoundingClientRect().top + window.scrollY - o", offset)
        self.page.evaluate(SCROLL_JS, [max(0, y), ms])

    def scroll_by(self, dy, ms=1400):
        self.page.evaluate(SCROLL_JS, [self.page.evaluate("window.scrollY") + dy, ms])

    def __exit__(self, *exc):
        dur = time.perf_counter() - self.t0
        video = self.page.video
        self.ctx.close()
        self.rec.segments.append({"name": self.name, "path": video.path(), "duration": dur})
        self.rec.offset += dur
        return False


def wait_until_processed(base, iid, timeout=300):
    end = time.time() + timeout
    while time.time() < end:
        with urllib.request.urlopen(f"{base}/inspections/{iid}/status") as r:
            if not json.load(r)["running"]:
                return
        time.sleep(2)


def show_card(seg, key, seconds):
    seg.page.set_content(CARDS[key])
    seg.page.wait_for_timeout(int(seconds * 1000))
    seg.rec.timeline.append({"t": round(seg.now() - seconds, 1), "segment": seg.name, "chapter": None, "caption": f"[card: {key}]"})


def main(base, followup_id, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    assets = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge")
        rec = Recorder(browser, out_dir)

        # 1. Title and problem -------------------------------------------------------
        with rec.segment("intro") as s:
            show_card(s, "title", 7)
            show_card(s, "problem", 11)
            show_card(s, "solution", 11)

        # 2. Live upload of a flooded car park ------------------------------------------
        with rec.segment("upload", geolocation={"latitude": 9.0765, "longitude": 7.3986},
                         permissions=["geolocation"]) as s:
            pg = s.page
            pg.goto(f"{base}/inspections/new", wait_until="domcontentloaded")
            s.caption("A resident spots flooding and opens DrainWatch on their phone or laptop.", "1 · Report", hold=3.5)
            pg.set_input_files("#media", os.path.join(assets, "car_puddle.jpg"))
            s.caption("They add a photo or a short video of the drain…", "1 · Report", hold=2.5)
            s.scroll_to("#lat", 900, offset=260)
            pg.locator("input[name=site_id]").type("CP-3", delay=90)
            pg.locator("input[name=address]").type("Shopping centre car park, Wuse", delay=35)
            pg.click("#geolocate")
            s.caption("…and share their location with one tap.", "1 · Report", hold=2.0)
            s.scroll_to("textarea[name=notes]", 900, offset=300)
            pg.locator("input[name=reporter]").type("Musa Ibrahim", delay=50)
            pg.locator("textarea[name=notes]").type("Water across the whole car park. A car is stuck.", delay=28)
            s.caption("A short note helps the team. Then: submit.", "1 · Report", hold=1.5)
            pg.click("#submit")
            pg.wait_for_url("**/inspections/insp-*", timeout=60000)
            s.caption("Processing starts immediately: OpenCV, then Amazon Nova Pro, then the agent.", "2 · Analyse", hold=6)
            s.caption("Every step runs in the background with live progress.", "2 · Analyse", hold=5)
            new_id = pg.url.rstrip("/").split("/")[-1].split("#")[0]
        wait_until_processed(base, new_id)

        # 3. The flood result: recommendation, severity check, OpenCV ----------------------
        with rec.segment("flood_result") as s:
            pg = s.page
            pg.goto(f"{base}/inspections/{new_id}", wait_until="domcontentloaded")
            pg.wait_for_timeout(800)
            s.caption("About a minute later, a prioritised recommendation is ready for a supervisor.", "3 · Recommend", hold=4.5)
            s.caption("P1: respond within 24 hours. Engineering review, because the drains are overwhelmed.", "3 · Recommend", hold=4.5)
            s.scroll_to(".steps-block", 1500)
            s.caption("In plain words: how the agent decided. It checked history, rainfall and nearby reports…", "3 · Recommend", hold=4.5)
            s.scroll_by(330, 1500)
            s.caption("…and it was not allowed to decide until it had looked at the image again with OpenCV.", "3 · Recommend", hold=5)
            s.scroll_to(".vlm-card", 1600)
            s.caption("Amazon Nova Pro rates severity from the photo and OpenCV's measurements: critical.", "4 · Severity", hold=4.5)
            s.scroll_to(".vlm-card .warn-box", 1200, offset=220)
            s.caption("DrainWatch cross-checks the two: OpenCV under-measured the floodwater and boxed a car as a drain.", "4 · Severity", hold=5.5)
            s.scroll_to("section.card:has(h2:has-text('OpenCV analysis'))", 1600)
            s.caption("OpenCV's own measurements stay visible: the rejected 'drain' is struck through, so no crew is sent to it.", "5 · OpenCV", hold=4)
            s.scroll_to(".rejected-note", 1300, offset=200)
            s.page.wait_for_timeout(3500)

        # 4. Follow-up video at D-14: OpenCV over time ------------------------------------
        with rec.segment("followup") as s:
            pg = s.page
            pg.goto(f"{base}/inspections/{followup_id}", wait_until="domcontentloaded")
            pg.wait_for_timeout(800)
            s.caption("Another site, D-14: a puddle reported last week, and now a follow-up video.", "6 · Follow-up", hold=4.5)
            s.caption("The problem keeps coming back, so the rules raise it to P2: road repair within 3 days.", "6 · Follow-up", hold=4.5)
            s.scroll_to(".steps-block", 1500)
            s.scroll_by(260, 1200)
            s.caption("The agent asked OpenCV to line up today's video with last week's photo and measure the change.", "6 · Follow-up", hold=5)
            s.scroll_by(420, 1500)
            s.caption("It also zoomed into the grate: the openings are clear, so the drain itself is not blocked.", "6 · Follow-up", hold=5)
            s.scroll_to(".vlm-card .cause", 1500, offset=180)
            s.caption("Likely cause: a dip in the road surface beside a clear drain. So: a road-repair crew, not drain cleaning.", "6 · Follow-up", hold=5.5)
            s.scroll_to("section.card:has(h2:has-text('OpenCV analysis'))", 1500)
            s.caption("Under the hood, OpenCV 5 tracked the drain across 21 video frames.", "7 · OpenCV 5", hold=3.5)
            s.scroll_to(".geo", 1300)
            s.caption("It measured where the water sits: the grate's edge is dry and the puddle lies beside it.", "7 · OpenCV 5", hold=4.5)
            s.scroll_to(".evidence-grid", 1300)
            s.caption("The persistence heatmap: red marks water present in most frames, not a passing reflection.", "7 · OpenCV 5", hold=5.5)
            s.scroll_to("section.card:has(h2:has-text('Preprocessing'))", 1600)
            s.caption("Before any of that, OpenCV checks every frame's quality and aligns the shaky handheld video.", "7 · OpenCV 5", hold=4)
            s.scroll_to(".compare", 1200, offset=140)
            s.caption("Dark frames are brightened (gamma + CLAHE) only where needed.", "7 · OpenCV 5", hold=0.5)
            for v in list(range(50, 92, 2)) + list(range(92, 8, -2)) + list(range(8, 52, 2)):
                pg.evaluate("v => { const r = document.querySelector('.compare input[type=range]'); r.value = v;"
                            " r.dispatchEvent(new Event('input')); }", v)
                pg.wait_for_timeout(40)
            s.scroll_to(".frames-head", 1200)
            pg.click("button[data-filter=all]")
            s.caption("Every frame keeps its quality scores, fixes and alignment, for full transparency.", "7 · OpenCV 5", hold=4)

        # 5. Supervisor decision, work order, audit trail ----------------------------------
        with rec.segment("decision") as s:
            pg = s.page
            pg.goto(f"{base}/inspections/{followup_id}#decision", wait_until="domcontentloaded")
            pg.wait_for_timeout(600)
            s.scroll_to("#decision", 900)
            s.caption("Nothing is sent to a crew until a person decides.", "8 · Human review", hold=3.5)
            pg.click(".choice-ok")
            pg.locator("input[name=reviewer]").type("A. Bello, Works Supervisor", delay=45)
            pg.locator("#decision-form textarea[name=note]").type("Patch the dip before the next rain.", delay=30)
            s.caption("The supervisor can approve, edit, ask for better footage, or reject with a reason.", "8 · Human review", hold=1.5)
            pg.click("#decision-form button.btn")
            pg.wait_for_load_state("domcontentloaded")
            pg.wait_for_timeout(500)
            s.scroll_to("#decision", 900)
            s.caption("Approved: a work order is created with a due date based on priority.", "8 · Human review", hold=4.5)
            pg.click("a[href='/work-orders/']")
            pg.wait_for_load_state("domcontentloaded")
            s.caption("All open work orders in one place, ready for the crews.", "9 · Act", hold=4.5)
            pg.go_back(wait_until="domcontentloaded")
            pg.wait_for_load_state("domcontentloaded")
            s.scroll_to("section.card:has(h2:has-text('Audit trail'))", 1600)
            s.caption("And every step is logged: who or what did it, and when. A complete audit trail.", "9 · Act", hold=5.5)
            pg.goto(f"{base}/inspections/", wait_until="domcontentloaded")
            s.caption("Every report in one list, with its review status.", "9 · Act", hold=4)

        # 6. Architecture, responsible use, close ----------------------------------------
        with rec.segment("outro") as s:
            show_card(s, "architecture", 14)
            show_card(s, "responsible", 10)
            show_card(s, "closing", 7)
        browser.close()

    with open(os.path.join(out_dir, "timeline.json"), "w", encoding="utf-8") as fh:
        json.dump({"segments": rec.segments, "captions": rec.timeline, "flood_inspection": new_id}, fh, indent=2)
    out = join(rec.segments, out_dir)
    print("video:", out, f"({rec.offset:.0f} s)")


def join(segments: list[dict], out_dir: str) -> str:
    """Concatenate the recorded sections into one H.264 MP4."""
    out = os.path.join(out_dir, "DrainWatch_demo.mp4")
    cmd = [imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error"]
    chains = []
    for i, seg in enumerate(segments):
        cmd += ["-i", seg["path"]]
        chains.append(f"[{i}:v]fps=30,scale={W}:{H},setsar=1[v{i}]")
    graph = (";".join(chains) + ";" + "".join(f"[v{i}]" for i in range(len(segments)))
             + f"concat=n={len(segments)}:v=1:a=0,format=yuv420p[out]")
    cmd += ["-filter_complex", graph, "-map", "[out]", "-c:v", "libx264", "-crf", "20", "-preset", "medium", out]
    subprocess.run(cmd, check=True)
    return out


if __name__ == "__main__":
    if sys.argv[1] == "--join":           # re-join an earlier recording: --join <out-dir>
        with open(os.path.join(sys.argv[2], "timeline.json"), encoding="utf-8") as fh:
            print("video:", join(json.load(fh)["segments"], sys.argv[2]))
    else:
        main(*sys.argv[1:4])
