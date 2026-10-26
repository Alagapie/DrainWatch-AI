# Devpost submission text: DrainWatch AI

Copy each section into the matching Devpost field. Replace anything in [brackets].

---

## Project name
DrainWatch AI

## Elevator pitch (short tagline, ≤ 200 characters)
Turn street footage into prioritised drainage work: OpenCV 5 measures, Amazon Nova Pro checks, an agent decides, and a supervisor approves.

---

## Inspiration
Every rainy season, streets flood because drains were blocked long before anyone noticed. City crews can't
inspect every drain, citizen complaints are vague, and "there's water on the road" can mean three different
problems: a blocked drain (send cleaners), a dip in the road (send road repair), or a drainage system that's
simply overwhelmed (send engineers). Sending the wrong crew wastes a day. We wanted to turn the photos and
videos people already take into evidence a maintenance team can act on, and act on correctly.

## What it does
DrainWatch AI is a decision-support web app for drainage inspection.

1. **Report.** Anyone uploads a photo set or a short video of a drain, with location and a note.
2. **OpenCV 5 preprocesses** the footage:
   - samples frames and scores each one's quality (sharpness, brightness, contrast, noise)
   - fixes only what is wrong (gamma, CLAHE, denoising, sharpening)
   - picks keyframes
   - aligns all frames to each other (ORB + RANSAC)
3. **OpenCV 5 analyses** the scene:
   - finds drains and tracks them across frames with a Kalman filter
   - segments water and debris
   - ignores moving cars and people (optical flow)
   - measures what persists across frames versus passing reflections
   - measures where the water sits relative to the drain: around the inlet (blockage) or beside a dry,
     clear grate (surface depression)
4. **Amazon Nova Pro (Amazon Bedrock) runs a severity check:**
   - rates the severity and the likely cause, and recommends a crew
   - verifies each OpenCV drain detection from a close-up crop

   DrainWatch then **cross-checks** the two: it flags when OpenCV under-measured floodwater or boxed
   something that isn't a drain.
5. **An agent recommends the next action.** Using Bedrock tool use, it investigates with **OpenCV tools**
   (re-analyse a frame, zoom into the drain, register against the previous visit) and **information tools**
   (site history, nearby reports, rainfall). It then submits a priority (P1–P4), an action and a crew.
   Two guardrails apply:
   - **Investigation policy:** submission is refused until the required vision checks are done.
   - **Priority policy:** the agent must follow the rules or explain its override.
6. **A supervisor decides.** They approve, edit, ask for better footage or reject. Approval creates a work
   order with a due date. Every step is recorded in an **audit trail**, and the agent's reasoning is shown
   in plain language for non-technical staff.

## How we built it
- **Backend and UI:** Python, Flask and Jinja, with a responsive dashboard (upload, live progress,
  results, work orders, audit trail). Processing runs as background stages with live status.
- **OpenCV 5.0** (`opencv-contrib-python 5.0.0`) does all of the measurement:
  - **Quality:** Laplacian variance, an Immerkær noise estimate.
  - **Enhancement:** gamma LUT, CLAHE in LAB, `fastNlMeansDenoisingColored`, unsharp mask.
  - **Keyframes:** HSV histograms.
  - **Registration:** ORB, BFMatcher, `estimateAffinePartial2D` with RANSAC.
  - **Drain detection:** contours, `minAreaRect`, slot grouping, gradient-orientation histograms.
  - **Water and debris masks:** HSV and texture cues relative to the road, Canny, morphology, connected
    components.
  - **Tracking and motion:** `KalmanFilter`, Farneback optical flow.
  - **Persistence and geometry:** persistence maps, `distanceTransform` water-to-drain geometry.
  - **Evidence and privacy:** a `applyColorMap` heatmap, and Haar cascades to blur faces and licence plates.
- **AWS:** Amazon Bedrock Converse API with **Amazon Nova Pro** (`amazon.nova-pro-v1:0`, us-east-1).
  - The severity check uses multimodal input (photos, OpenCV overlays, drain close-ups) with structured
    JSON output, validated and cross-checked.
  - The agent uses Bedrock **tool use** in a multi-step loop.
- **Agent design:** 7 tools, an investigation policy and a priority policy enforced inside
  `submit_recommendation`, a full trace, and a plain-language explanation layer.

## Challenges we ran into
- **Classical vision on messy scenes.** Our first water detector called plain grey concrete "water", and the
  first debris detector flagged ordinary asphalt grain. We rebuilt both to compare each pixel against the
  road's own brightness and texture, and rebuilt drain detection to group parallel slots into one grate.
- **Telling causes apart.** Puddle size alone couldn't separate a blocked drain from a dip in the road. We
  added OpenCV geometry: how much of the grate's edge is wet, and where the puddle's centre lies.
- **Unrelated photos in one report.** Photos of different places polluted the score. Now OpenCV detects
  photos that can't be registered and analyses them as separate views.
- **Keeping the agent honest.** The agent liked to skip the vision tools and sometimes contradicted its own
  priority rules. We moved the rules into the tools themselves: the submission is refused until the
  evidence has been checked, and any override must be explained.
- **Floodwater and false drains.** OpenCV under-measures rippled floodwater and once boxed a car as a drain,
  so we added drain close-up verification and automatic cross-checks between OpenCV and Nova Pro.

## Accomplishments that we're proud of
- **OpenCV and the AI check each other.** On a flooded car park, OpenCV scored medium (35). Nova Pro rated it
  critical, explained exactly what OpenCV got wrong, and rejected the false drain detection.
- **The right crew, not just a score.** On a real photo of a puddle in a road dip, DrainWatch concluded
  "surface depression → road-repair crew", because OpenCV measured that the grate's edge was dry and the
  water sat beside it.
- **Vision results change decisions.** The agent cannot finish without looking at the image again, and its
  steps show how the OpenCV results changed its conclusion.
- **A complete human-in-the-loop workflow:** approvals, edits, work orders and an audit trail.

## What we learned
- Simple, interpretable OpenCV measurements combined with a vision-language model that checks them work
  better than either alone, and the disagreements between them are useful signals.
- Rules for an agent belong in its tools, not only in its prompt.
- Non-technical users need the agent's reasoning in plain sentences, with the raw trace kept one click away.

## What's next for DrainWatch AI
- Validate on a labelled dataset of local drains (precision/recall, IoU, false-alert rate), and train a
  small detector to complement the classical rules.
- A mobile capture app with offline upload and automatic GPS site matching.
- Deployment on AWS (S3 for media, DynamoDB for records, Cognito for roles) with multi-user review.
- Rainfall-triggered re-inspection campaigns and maintenance-trend reports per ward.

## Built with
`python` · `opencv` · `opencv-5` · `flask` · `amazon-bedrock` · `amazon-nova-pro` · `aws` · `boto3` · `numpy` · `javascript` · `html` · `css` · `open-meteo` · `openstreetmap`

## Try it out
- GitHub: https://github.com/Alagapie/DrainWatch-AI
- Demo video: [your YouTube link]

---

## Special award: Agentic Vision (paste where Devpost asks, or add to the description)
DrainWatch's agent runs a perception → decision → action loop in which **OpenCV 5 results directly change
what happens next**:
- The agent calls OpenCV tools: frame re-analysis with chosen enhancements, a drain close-up measuring
  visible grate openings, and ORB + RANSAC registration against the previous visit with a change map.
- The `submit_recommendation` tool **refuses** until the required vision checks have run, so a decision
  can't be made without looking at the image again.
- The tool results feed the decision. "Grate openings clearly visible" plus "water beside a dry grate edge"
  leads to road repair instead of drain cleaning, and "worse than the last visit" raises the priority.
- The outcome is an action that **requests human approval** (a work order, a request for better footage,
  or monitoring), with every step in an audit trail.

## Notes for judges
- **OpenCV 5 is meaningful:** it produces every measurement (quality, alignment, drains, water and debris
  masks, tracking, motion, persistence, geometry, evidence). The models interpret and check those
  measurements; they do not create detections.
- **AWS component:** Amazon Bedrock (Nova Pro) powers both the multimodal severity check and the tool-using
  agent.
- **Honest limits:** the system was tested on a small set of real photos and generated footage, not a large
  labelled dataset; the README lists the limitations.
