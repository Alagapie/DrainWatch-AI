# DrainWatch AI: 3-minute demo video plan

**Final picture:** `demo/out/DrainWatch_demo_3min.mp4` (2:54, 1920×1080, 30 fps, captions burned in, no audio).
It is cut from the full live recording (`demo/out/DrainWatch_demo.mp4`, 4:27) by `demo/cut_short.py`.
Everything on screen is the real app with real Amazon Nova Pro output. The flood case was uploaded and
processed live during the recording. Nothing is mocked.
**Narration:** [VOICEOVER_SCRIPT.md](VOICEOVER_SCRIPT.md), word for word, with timecodes.

---

## 1. Assessment: what to show
DrainWatch's strongest features are the ones a judge can *see* working:

| Strength | Why it convinces | Proof on screen |
|---|---|---|
| **The right crew, not just a score** | It goes beyond spotting water and decides what kind of problem it is | D-14: "dip in the road → road repair, not drain cleaning" |
| **OpenCV and Nova Pro check each other** | It is honest about errors, and the false drain is caught | Flood: "OpenCV under-measured… boxed a car as a drain"; the rejected drain is struck through |
| **Agent guardrails** | It is a real agentic loop: vision tools change the decision, and the agent cannot skip them | "Submission refused until it re-examined the image with OpenCV" |
| **OpenCV 5 depth** | It meets the competition's core requirement | Kalman tracking, water/drain geometry, persistence heatmap, CLAHE slider |
| **Human in the loop** | It is safe and practical | Approve → work order → audit trail |

Left out because they are less visual or already covered: the full frame list, the responsible-use card
(the review scene shows it), and the inspection list.

## 2. Narrative
**Hook** (a problem with three causes) → **promise** (one sentence of pipeline) → **live case 1: a flooded
car park** (speed, P1, agent guardrail, AI cross-check) → **case 2: recurring puddle D-14** (agent uses OpenCV
tools, finds the *cause*, OpenCV 5 under the hood) → **human approves → work order → audit** → **architecture
in one line** → **tagline**.
About 80% of the runtime is the live app.

## 3. Storyboard (2:54)

| Time | Visuals and actions | On-screen text (burned in) | Judging criterion served |
|---|---|---|---|
| 0:00–0:04 | Title card | "Turning street footage into prioritised drainage work." | Clarity |
| 0:04–0:12 | Problem card: three pain points | "Blocked drains are found too late." | Problem relevance |
| 0:12–0:19 | Solution card: OpenCV 5 → Nova Pro → agent + person | "Upload a photo or a short video…" | Solution clarity |
| 0:19–0:35 | New report: photo added, site ID typed, one-tap location, note typed, Submit | Chapter "1 · Report" plus 4 captions | Usability |
| 0:35–0:43 | Inspection page: stage dots and the live progress bar advancing | "Processing starts immediately…" | Execution, real pipeline |
| 0:43–0:51 | Recommendation card: **P1**, engineering review | "P1: respond within 24 hours…" | Impact |
| 0:51–1:04 | Scroll through the plain-language agent steps; red "refused" step | "…not allowed to decide until it had looked at the image again with OpenCV." | **Agentic Vision** |
| 1:04–1:21 | Severity card **critical 90** → cross-check warning → OpenCV card with the struck-through drain | "DrainWatch cross-checks the two…" | Technical depth, honesty |
| 1:21–1:33 | D-14 page: **P2**, recurring | Chapter "6 · Follow-up" | Real-world workflow |
| 1:33–1:53 | Agent steps: registration against the last visit, drain close-up; cause card "surface depression" | "Likely cause: a dip in the road…" | **Agentic Vision**, innovation |
| 1:53–2:09 | OpenCV card: Kalman tracking, "where the water sits", persistence heatmap | Chapter "7 · OpenCV 5" | **OpenCV 5 requirement** |
| 2:09–2:14 | Before/after slider sweeping (original ↔ gamma + CLAHE) | "Dark frames are brightened… only where needed." | OpenCV 5, polish |
| 2:14–2:40 | Supervisor approves (name and note typed) → work order created → Work orders page → audit trail | Chapter "8 · Human review" / "9 · Act" | Completeness, responsibility |
| 2:40–2:48 | Architecture card | "Perception → decision → action, with a human in the loop." | AWS + OpenCV usage |
| 2:48–2:54 | Closing card | "See it. Measure it. Fix it first." + GitHub link | Memorability |

Transitions are 0.4 s crossfades at every cut. There are no zooms or effects: the captions and the smooth
scripted scrolling already guide the eye.

## 4. Voice-over
See [VOICEOVER_SCRIPT.md](VOICEOVER_SCRIPT.md).

## 5. Recording (already done) and how to redo it
The picture was recorded by script, so cursor movement, scrolling and typing are already clean:
- **Browser:** Microsoft Edge via Playwright, a clean window with no tabs, bookmarks or desktop, at
  1280×720 and upscaled to 1080p.
- **Script:** `demo/record_demo.py` performs every action (typing, one-tap location, submit, scrolling,
  slider, approval). Then `demo/cut_short.py` trims the recording to the scenes above.
- **To re-record from scratch:** start from an empty `data/` folder (otherwise CP-3 gains a history and D-14 is
  already approved, which changes the results), then follow "Reproduce the demo video" in the README.

**You only need to record your voice.**

## 6. Editing (Clipchamp, free, built into Windows 11)
1. **New video, 16:9.** Drag in `DrainWatch_demo_3min.mp4`.
2. **Voice:** *Record & create → Audio* (or record on your phone and import the file). Read the script while
   the video plays. Record one block at a time; re-recording a single block is easy.
3. **Line up each voice clip** with its timecode. If a clip runs long, trim pauses, or speed it up by 1.05×
   (no more).
4. **Music (optional):** *Content library → Music*, choose a calm, low-key track ("corporate", "ambient").
   Set it to **10–15 % volume** under the voice, and fade in and out over 2 s. Music should never compete
   with the words.
5. **Noise:** if Clipchamp offers *Noise suppression* on the voice clip, turn it on.
6. **Captions:** they are already burned in, so do not add auto-captions as well.

## 7. Assets
- [x] Final picture: `demo/out/DrainWatch_demo_3min.mp4`
- [x] Script: `submission/VOICEOVER_SCRIPT.md`
- [x] Thumbnail: `submission/thumbnail.png`
- [ ] Your voice recording (quiet room; phone 15–20 cm from your mouth; record a 3 s silence first)
- [ ] Optional music track from the Clipchamp or YouTube Audio Library (royalty-free)

## 8. Final checklist
- [x] Total 2:54, under 3:00
- [x] Problem stated by 0:12, solution by 0:19
- [x] Live app on screen from 0:19 to 2:40 (about 80 % of the runtime)
- [x] OpenCV 5 and Amazon Bedrock each named and shown doing real work
- [x] Agent behaviour shown through its real trace (refused step, OpenCV tool calls)
- [x] No invented numbers: every value on screen comes from the live run
- [x] Captions readable at 1080p; no blank or loading frames at the cuts
- [ ] Voice matches the picture at each timecode
- [ ] Voice clearly louder than the music; no clipping
- [ ] Watched once end to end on a phone screen

## 9. Export and upload
- **Clipchamp export:** **1080p**, MP4 (H.264 + AAC).
- **YouTube:** upload as **Public** or **Unlisted** and set the thumbnail to `submission/thumbnail.png`.
  - **Title:** *DrainWatch AI: OpenCV 5 + Amazon Bedrock agent for drain inspection (OpenCV AI Competition 2026)*
  - Paste the Devpost elevator pitch into the description, and add the GitHub link.
- **Then:** paste the YouTube link into `README.md` and the Devpost "Video demo link" field.
