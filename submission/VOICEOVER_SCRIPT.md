# DrainWatch AI: demo voice-over script

**Video:** `demo/out/DrainWatch_demo.mp4` (4:27, 1280×720, no audio)
**How to use:** play the video and read each block when its timecode appears. The on-screen captions say
the same thing in short form, so if you fall a little behind, the viewer still follows.
Speak calmly: roughly two to three words per second. Pauses are fine. The video already has captions.

**Tip:** record in a quiet room, phone close to your mouth. Free tools: **Clipchamp** (built into Windows 11)
lets you drop the MP4 on a timeline, record your voice on top, and export. Upload the result to YouTube as
*Unlisted* or *Public* and paste the link into Devpost.

---

### 0:00 – 0:10 · Title card
> Hi, I'm [your name], and this is **DrainWatch AI**: it turns ordinary street footage into prioritised
> drainage work, using **OpenCV 5** and **Amazon Bedrock**.

### 0:10 – 0:23 · The problem
> Blocked drains are usually found too late, after the street has already flooded. Crews can't inspect
> every drain, citizen reports are vague, and standing water can have different causes, each needing a
> different crew.

### 0:23 – 0:36 · The solution
> With DrainWatch, anyone uploads a photo or a short video. OpenCV 5 measures what the camera sees.
> Amazon Nova Pro double-checks it. An agent decides what should happen next, and a person approves it.

### 0:36 – 1:04 · Live report (upload)
> Let's report a real case. A resident sees a flooded car park. They add the photo, the location with
> one tap, and a short note: water across the whole car park, a car is stuck. Then they submit.

### 1:04 – 1:18 · Processing
> Processing starts straight away and runs in the background. First OpenCV checks the image quality and
> analyses the scene. Then Amazon Nova Pro rates the severity. Then the agent investigates and drafts a
> recommendation.

### 1:18 – 1:29 · The recommendation
> About a minute later, there's a recommendation waiting for a supervisor: **P1**, respond within 24
> hours, with an **engineering review**, because the drainage system is overwhelmed.

### 1:29 – 1:42 · How the agent decided
> Here's how the agent decided, in plain language. It checked the site's history, the rainfall and nearby
> reports. When it tried to decide too early, DrainWatch **refused** until it had looked at the image again
> with OpenCV. The vision results have to shape every decision.

### 1:42 – 1:55 · The severity check
> Amazon Nova Pro rated this **critical**: a car partly under water. And DrainWatch cross-checks the two
> systems: OpenCV under-measured the floodwater and mistook part of a car for a drain. Nova Pro looked at a
> close-up of that box and rejected it.

### 1:55 – 2:05 · OpenCV's own results
> OpenCV's raw measurements always stay visible, but the rejected "drain" is struck through, so no crew is
> ever sent to a drain that doesn't exist.

### 2:05 – 2:17 · A second site: D-14
> Now a different site, **D-14**. A puddle was reported here last week, and the inspection crew has just
> filmed a follow-up video. Because the problem keeps coming back, the rules raise it to **P2**: road
> repair within three days.

### 2:17 – 2:30 · OpenCV tools in the decision
> The agent asked OpenCV to line up today's video with last week's photo and measure what changed. It also
> zoomed into the grate: the openings are clear, so the drain itself isn't blocked.

### 2:30 – 2:37 · The likely cause
> So the likely cause is a **dip in the road surface** beside a clear drain. That means a road-repair crew,
> not a drain-cleaning crew: the right team, first time.

### 2:37 – 2:55 · Under the hood: OpenCV 5
> Under the hood, OpenCV 5 tracked the drain across all twenty-one video frames with a Kalman filter. It
> measured where the water sits: the grate's edge is dry, and the puddle lies beside it. And this
> persistence heatmap shows water that stays in most frames, not just a passing reflection.

### 2:55 – 3:13 · Preprocessing
> Before any of that, OpenCV scores every frame's quality and aligns the shaky handheld video using ORB
> features and RANSAC. Dark frames are brightened with gamma and CLAHE, only where needed. Every frame
> keeps its scores and fixes, so the whole process is transparent.

### 3:13 – 3:28 · Human review
> Nothing goes to a crew until a person decides. The supervisor can approve, edit the priority or crew,
> ask for better footage, or reject with a reason. Here they approve, and a **work order** is created
> with a due date based on the priority.

### 3:28 – 3:46 · Work orders and audit trail
> All open work orders are in one place for the crews. And every single step is logged in an **audit
> trail**: who or what did it, and when, from the upload to OpenCV, Nova Pro, the agent and the supervisor.

### 3:46 – 4:05 · Architecture
> To sum up the architecture: a Flask dashboard; OpenCV 5 for preprocessing and analysis; Amazon Nova Pro
> on Bedrock for the severity check; a Bedrock agent that uses OpenCV as tools alongside history,
> rainfall and nearby reports; and a supervisor who approves every action.

### 4:05 – 4:18 · Responsible use
> DrainWatch is decision support, not autopilot. People approve every action, faces and number plates are
> blurred, disagreements are shown rather than hidden, and the agent must follow the priority rules or
> explain why it didn't.

### 4:18 – 4:27 · Close
> DrainWatch AI: see it, measure it, fix it first. Thank you.

---

**Total spoken words:** about 600, a comfortable pace for 4½ minutes.
If you need to save time, the **0:10–0:36** cards and the **2:55–3:13** preprocessing section are the
easiest places to shorten your narration.
