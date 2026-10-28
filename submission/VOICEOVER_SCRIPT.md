# DrainWatch AI: voice-over script (3-minute cut)

**Video:** `demo/out/DrainWatch_demo_3min.mp4` (2:54, 1920×1080, captions on screen, no audio)
**How to use:** play the video and start each block when its timecode appears. Speak at a calm, steady
pace (about 2.3 words a second). Each block fits its scene with a little room to breathe. If you fall
behind, drop the words in *[brackets]*; they are optional.

---

| Time | Scene | Say |
|---|---|---|
| 0:00 – 0:04 | Title card | This is **DrainWatch AI**: street footage in, the right repair crew out. |
| 0:04 – 0:12 | Problem card | Streets flood because blocked drains are found too late. And standing water has different causes, each needing a different crew. |
| 0:12 – 0:19 | Solution card | Upload a photo or video. **OpenCV 5** measures, **Amazon Nova Pro** checks, an agent recommends, and a person approves. |
| 0:19 – 0:35 | Live report | Here's a live report. A resident photographs a flooded car park, shares their location with one tap, adds a note *[that a car is stuck]*, and submits. |
| 0:35 – 0:43 | Live progress | Processing starts at once: OpenCV first, then Nova Pro on Amazon Bedrock, then the agent. |
| 0:43 – 0:51 | Recommendation (P1) | About a minute later: **priority one**, respond within 24 hours. An engineering review, because the drains are overwhelmed. |
| 0:51 – 1:04 | How the agent decided | Here's how the agent decided, in plain language. It checked site history, rainfall and nearby reports. When it tried to decide early, DrainWatch **refused** until it had re-examined the image with OpenCV. |
| 1:04 – 1:17 | Severity check | Nova Pro rates this **critical**. And DrainWatch cross-checks both systems: OpenCV under-measured the floodwater and boxed part of a car as a drain. Nova Pro checked a close-up and rejected it. |
| 1:17 – 1:21 | Rejected drain struck through | So no crew is ever sent to a drain that isn't there. |
| 1:21 – 1:33 | Site D-14 | A second site, **D-14**. A puddle was reported here last week; this is the crew's follow-up video. It keeps coming back, so the rules raise it to **priority two**. |
| 1:33 – 1:46 | Agent's OpenCV tools | The agent used OpenCV as tools: it aligned today's video with last week's photo to measure the change, and zoomed into the grate. The openings are clear. |
| 1:46 – 1:53 | Likely cause | So the cause is a **dip in the road**, not a blocked drain: send road repair, not drain cleaning. |
| 1:53 – 2:09 | OpenCV 5 under the hood | Under the hood, OpenCV 5 tracked the drain across 21 frames with a Kalman filter, measured that the grate's edge is dry with water beside it, and built a persistence heatmap: water that stays, not a passing reflection. |
| 2:09 – 2:14 | Before / after slider | Shaky, dark frames are aligned and enhanced only where needed. |
| 2:14 – 2:24 | Supervisor decision | Nothing reaches a crew until a person decides: approve, edit, ask for better footage, or reject. |
| 2:24 – 2:36 | Approved → work order | The supervisor approves, and a **work order** is created with a due date set by priority, ready for the crews. |
| 2:36 – 2:40 | Audit trail | Every step is logged in an audit trail. |
| 2:40 – 2:48 | Architecture card | OpenCV 5 measures. Amazon Nova Pro on Bedrock checks and decides, using OpenCV as its tools. A human approves. |
| 2:48 – 2:54 | Closing card | **DrainWatch AI.** See it, measure it, fix it first. |

**Spoken words:** about 330, which fits 2:54 comfortably.
