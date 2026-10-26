"""Full-screen cards (1280x720) used in the demo video."""

_BASE = """<!doctype html><html><head><meta charset="utf-8">
<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
* { box-sizing: border-box; margin: 0; }
body { width: 1280px; height: 720px; overflow: hidden; font-family: "Plus Jakarta Sans", system-ui, sans-serif;
  background: radial-gradient(900px 500px at 15% 10%, #13405a, transparent 70%), linear-gradient(135deg, #0a1c27, #0d2a38);
  color: #eaf3f8; display: flex; flex-direction: column; justify-content: center; padding: 70px 90px; }
.logo { display: flex; align-items: center; gap: 14px; font-weight: 800; font-size: 26px; margin-bottom: 34px; }
.mark { width: 52px; height: 52px; border-radius: 15px; display: grid; place-items: center;
  background: linear-gradient(135deg, #0b7fb0, #13a38b); }
.logo em { font-style: normal; color: #5cc3ec; }
h1 { font-size: 58px; line-height: 1.08; letter-spacing: -.025em; font-weight: 800; }
h2 { font-size: 40px; line-height: 1.15; letter-spacing: -.02em; font-weight: 800; margin-bottom: 26px; }
p.lead { font-size: 24px; line-height: 1.5; color: #b9d0dc; margin-top: 20px; max-width: 1000px; }
.tag { display: inline-block; padding: 7px 16px; border-radius: 999px; background: rgba(92,195,236,.15); color: #7fd3f3;
  font-weight: 700; font-size: 16px; letter-spacing: .06em; text-transform: uppercase; margin-bottom: 22px; align-self: flex-start; }
.grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 20px; }
.box { padding: 22px; border-radius: 18px; background: rgba(255,255,255,.06); border: 1px solid rgba(255,255,255,.1); }
.box b { display: block; font-size: 22px; margin-bottom: 8px; color: #fff; }
.box span { font-size: 17px; line-height: 1.45; color: #b9d0dc; }
.flow { display: flex; align-items: stretch; gap: 10px; }
.node { flex: 1; padding: 16px 12px; border-radius: 16px; text-align: center; background: rgba(255,255,255,.07);
  border: 1px solid rgba(255,255,255,.12); display: flex; flex-direction: column; gap: 6px; }
.node b { font-size: 17px; color: #fff; }
.node span { font-size: 13.5px; line-height: 1.35; color: #b9d0dc; }
.node.cv { border-color: #3fb0e0; background: rgba(63,176,224,.14); }
.node.aws { border-color: #ff9d2e; background: rgba(255,157,46,.12); }
.node.human { border-color: #3cc684; background: rgba(60,198,132,.13); }
.arrow { align-self: center; color: #5cc3ec; font-size: 26px; font-weight: 800; }
.legend { display: flex; gap: 26px; margin-top: 22px; font-size: 16px; color: #b9d0dc; }
.legend i { display: inline-block; width: 14px; height: 14px; border-radius: 4px; margin-right: 8px; vertical-align: -2px; }
ul.list { list-style: none; padding: 0; display: grid; grid-template-columns: 1fr 1fr; gap: 16px 40px; }
ul.list li { font-size: 21px; line-height: 1.45; padding-left: 34px; position: relative; color: #dbe9f0; }
ul.list li::before { content: "✓"; position: absolute; left: 0; color: #3cc684; font-weight: 800; }
.big { font-size: 64px; font-weight: 800; letter-spacing: -.03em; }
</style></head><body>{body}</body></html>"""

_LOGO = """<div class="logo"><div class="mark"><svg width="30" height="30" viewBox="0 0 32 32">
<path d="M16 3c-4.5 6-8 10.4-8 14.5a8 8 0 0 0 16 0C24 13.4 20.5 9 16 3z" fill="#fff"/>
<path d="M11.5 18.5h9M11.5 21.5h9M13 15.5h6" stroke="#0b7fb0" stroke-width="1.6" stroke-linecap="round"/></svg></div>
<span>DrainWatch <em>AI</em></span></div>"""


def _card(body: str) -> str:
    return _BASE.replace("{body}", body)


CARDS = {
    "title": _card(_LOGO + """
<span class="tag">OpenCV AI Competition 2026 · powered by AWS</span>
<h1>Turning street footage into<br>prioritised drainage work.</h1>
<p class="lead">OpenCV 5 measures what the camera sees. Amazon Nova Pro checks it. An agent decides what should
happen next, and a person approves it.</p>"""),

    "problem": _card("""
<span class="tag">The problem</span>
<h2>Blocked drains are found too late.</h2>
<div class="grid">
  <div class="box"><b>Limited coverage</b><span>Crews can't inspect every drain often, so problems are found after the street floods.</span></div>
  <div class="box"><b>Vague reports</b><span>Citizen complaints are hard to verify and impossible to prioritise fairly.</span></div>
  <div class="box"><b>Wrong crew, wasted trips</b><span>Standing water can mean a blocked drain, a dip in the road, or an overloaded system. Each needs a different team.</span></div>
</div>"""),

    "solution": _card("""
<span class="tag">The solution</span>
<h2>Upload a photo or a short video. Get an evidence-backed decision.</h2>
<div class="grid">
  <div class="box"><b>OpenCV 5 measures</b><span>Finds the drain, water and debris, tracks them across frames, and measures what persists.</span></div>
  <div class="box"><b>Nova Pro checks</b><span>Rates severity and the likely cause, and corrects OpenCV where it is wrong.</span></div>
  <div class="box"><b>An agent decides, a person approves</b><span>Checks history and rainfall, looks again with OpenCV, then drafts a work order for a supervisor.</span></div>
</div>"""),

    "architecture": _card("""
<span class="tag">How it works</span>
<h2>Perception → decision → action, with a human in the loop.</h2>
<div class="flow">
  <div class="node"><b>Upload</b><span>Flask dashboard<br>photo / video + location</span></div><div class="arrow">→</div>
  <div class="node cv"><b>OpenCV 5 · preprocess</b><span>quality scores, gamma, CLAHE, denoise, keyframes, ORB + RANSAC alignment</span></div><div class="arrow">→</div>
  <div class="node cv"><b>OpenCV 5 · analyse</b><span>drain detection, water &amp; debris masks, Kalman tracking, optical flow, persistence, geometry</span></div><div class="arrow">→</div>
  <div class="node aws"><b>Amazon Nova Pro</b><span>severity, likely cause, verifies OpenCV's drains (Bedrock)</span></div><div class="arrow">→</div>
  <div class="node aws"><b>Agent (Bedrock tools)</b><span>OpenCV tools + history, rainfall, nearby reports; policy-checked</span></div><div class="arrow">→</div>
  <div class="node human"><b>Supervisor</b><span>approve / edit / reject, work order, audit trail</span></div>
</div>
<div class="legend"><span><i style="background:#3fb0e0"></i>OpenCV 5 (measures)</span><span><i style="background:#ff9d2e"></i>Amazon Bedrock (reasons)</span><span><i style="background:#3cc684"></i>Human (decides)</span></div>"""),

    "responsible": _card("""
<span class="tag">Responsible by design</span>
<h2>Decision support, not autopilot.</h2>
<ul class="list">
  <li>A person approves every action</li>
  <li>Faces and number plates blurred in evidence</li>
  <li>Confidence and disagreements shown, never hidden</li>
  <li>OpenCV's raw measurements always visible</li>
  <li>Agent must follow priority rules or justify overrides</li>
  <li>Every step logged in an audit trail</li>
</ul>"""),

    "closing": _card(_LOGO + """
<h1>See it. Measure it. Fix it first.</h1>
<p class="lead">DrainWatch AI · OpenCV 5 + Amazon Bedrock (Nova Pro)<br>github.com/Alagapie/DrainWatch-AI</p>"""),
}
