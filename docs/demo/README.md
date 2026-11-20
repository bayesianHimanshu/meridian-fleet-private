# The narrated demo

The demo is a 7 min 30 s video of the Command Center, narrated by a local voice, from
[script.md](script.md). It comes with one page where a viewer watches it and asks questions,
answered by retrieval from the transcript and the project's documents.

## What is where

| File | Committed | What |
|---|---|---|
| docs/demo/script.md | yes | The script: narration, pages, highlights, sources, pronunciation |
| docs/demo/qa-questions.json | yes | The 30 evaluation questions, committed before the index was built |
| docs/demo/qa-results.md | yes | Their results, from one run |
| docs/demo/index.html | yes | The page, with the index and transcript inside (the video is not) |
| src/meridian/demo/, `meridian demo` | yes | Ledger copy, TTS, timing, captions, cards, ffmpeg assembly |
| web/demo/record.mjs, scenes.mjs | yes | The Playwright recorder and each scene's steps |
| web/demo/search.mjs, build-page.mjs, eval-qa.mjs | yes | Retrieval, the page and the evaluation |
| var/demo/demo.mp4 | no | The video: 1440 x 900, H.264 and AAC, 10 chapters |
| var/demo/captions.vtt, transcript.json | no | WebVTT captions and the timestamped transcript |
| var/demo/index.html | no | The page, next to the video: open this one |
| var/demo/ledger.sqlite3, plan.json, frames/, audio/, cards/ | no | Working files |
| var/demo/voice/ | no | The voice model |

## Chapters

| # | Chapter | Starts | Length |
|---|---|---:|---:|
| 1 | What this is | 0:00 | 46.5 s |
| 2 | The Command Center | 0:46 | 38.4 s |
| 3 | RBQM and traceability | 1:24 | 41.5 s |
| 4 | Containment | 2:06 | 44.2 s |
| 5 | Safety | 2:50 | 44.4 s |
| 6 | Preclinical, from the rat to the first dose | 3:34 | 82.1 s |
| 7 | Portfolio and the IND gate | 4:56 | 43.0 s |
| 8 | Audit and attribution | 5:39 | 37.0 s |
| 9 | Scale | 6:16 | 32.3 s |
| 10 | Honest limits and lessons | 6:49 | 40.3 s |
| | **Total** | | **449.5 s (7 min 30 s)** |

## Never writing, and never acting as a person

- **The ledger copy.** Recording reads only a copy of the ledger. `meridian demo prepare`
  copies it, and opens the real ledger read-only with SQLite's backup API.
  - The copy is verified (`ledger verify`).
  - Its last hash must equal the real ledger's hash at the same seq.
  - At the recording: 20,212 events, last hash `4783893682db5e03...`, equal to the real
    ledger's at seq 20212.
- **The read-only API.** The API serves that copy with `meridian api serve --port 8766
  --demo-read-only var/demo/refusals.jsonl --fixed-now 2026-11-20T12:00:00+00:00`.
  - In this mode any request other than GET, HEAD or OPTIONS gets a 403 before any route
    runs. Each refusal is appended to the log with its time.
  - tests/api/test_demo_read_only.py covers every write endpoint, and checks that the
    ledger file is unchanged.
- **The proof, during the recording.** In scene 3 the recorder makes a real decision
  request: `POST /api/v1/findings/RBQM-0134/decisions` as asha.rao.
  - It must be refused with 403, or the recording stops.
  - The response and its time go to var/demo/frames/proof.json, and the API logs the same
    refusal.
  - Afterwards the copy's last seq and hash are checked again; they have not changed.
  - In the final recording, the attempt was refused with 403 at 2026-11-20T11:02:49Z (wall
    clock), at 1:55.9 in the video's time.
- **People.** Each scene is shown as the person whose role sees the page (the role
  switcher is development identity). No form is ever submitted. Where the narration
  speaks of a decision, the recorded decision is shown.

## Re-recording

You need:
- `uv tool install piper-tts==1.8.0`: Piper, the local TTS engine. It is installed as a
  uv tool, outside this project's dependencies and lockfile; the pipeline calls the
  `piper` executable.
- The voice model in var/demo/voice/ (below).
- ffmpeg on the system.
- Google Chrome (Playwright drives it through `channel: "chrome"`; no browser is
  downloaded).
- The web dependencies (`cd web && npm ci`).

```sh
uv run meridian demo prepare                  # copy and verify the ledger; narration; plan; cards
MERIDIAN_LEDGER_PATH=var/demo/ledger.sqlite3 uv run meridian api serve --port 8766 \
  --demo-read-only var/demo/refusals.jsonl --fixed-now 2026-11-20T12:00:00+00:00 &
(cd web && MERIDIAN_API_URL=http://127.0.0.1:8766 npx vite --port 5175 &)
(cd web && node demo/record.mjs)              # one still per step; var/demo/frames/
uv run meridian demo assemble                 # var/demo/demo.mp4 with chapters
node web/demo/build-page.mjs                  # the index and the page (both copies)
node web/demo/eval-qa.mjs                     # the Q&A evaluation (run once per recording)
```

Open var/demo/index.html. To record one scene while working on it, run
`DEMO_SCENES=6 node demo/record.mjs`.

**Deterministic.** The same ledger copy and the same script give the same video, byte for
byte. Four things make it so:
- **Fixed audio.** Piper runs with noise 0; with its default noise, the same sentence gave
  different audio twice.
- **Fixed clocks.** Both the browser's clock and the API's clock stand at
  2026-11-20T12:00:00Z.
- **Fixed rendering.** Chrome renders in software, with a fixed colour profile and no LCD
  text.
- **Stills, not a screen capture.** The video is made from still frames with exact
  durations, and ffmpeg encodes with one thread and bitexact flags.

How it was checked:
- Two recordings gave 85 identical PNGs.
- Clearing the audio cache and synthesising again gave the same narration, captions,
  transcript and video.

## Versions and licences

| Item | Version | Licence | Note |
|---|---|---|---|
| Piper (piper-tts) | 1.8.0 | GPL-3.0-or-later | A uv tool, run as a separate program; no Piper code is in this repository |
| Voice | en_US-libritts-high, speaker 0 | Dataset LibriTTS, CC BY 4.0 (model card) | Trained from scratch on LibriTTS train-clean-360 |
| @playwright/test | 1.65.0 (web devDependency, exact) | Apache-2.0 | |
| Browser | Google Chrome 157.0.8103.38 | | Playwright's own Chromium is not installed; none was downloaded |
| ffmpeg | 8.0.1-3ubuntu2+esm5 | | System package |

Voice files (from huggingface.co/rhasspy/piper-voices, en/en_US/libritts/high):

| File | sha256 |
|---|---|
| en_US-libritts-high.onnx | 9127a559e11603f10b366d1a20ac7426826081dbc521de4c2420c57728d73f0f |
| en_US-libritts-high.onnx.json | 2efdc6d7f954588b8180132cbd9b8001933fdd00932c92bc92fd0d2028a9eb3d |
| MODEL_CARD | c478d826aae8a6332f69509271a56083b9ece014a993e16fc79cb94968106a5f |

**Why not the voice first approved.** The first voice, en_US-libritts_r-medium, was
approved as CC BY 4.0. Its model card says it was fine-tuned from en_US-lessac-medium,
which was trained on the Blizzard 2013 Lessac data. That data's licence allows research use
only and excludes commercial use. The project lead chose en_US-libritts-high instead,
whose model card says it was trained from scratch on LibriTTS (CC BY 4.0).

**Credit,** on the closing card and in the page footer: "Narration voice: Piper
en_US-libritts-high, trained on LibriTTS (CC BY 4.0)." The dataset citation: Zen, H., Dang,
V., Clark, R., Zhang, Y., Weiss, R. J., Jia, Y., Chen, Z. and Wu, Y. (2019). LibriTTS: A
Corpus Derived from LibriSpeech for Text-to-Speech. Interspeech 2019.

## The question box

- **Retrieval, not generation.** The page holds an index of 147 passages:
  - transcript segments, each with its time;
  - sections of README.md, docs/project-summary.md, docs/architecture.md, docs/lessons.md
    and the six phase summaries.
- **How a question is answered.** It is scored with BM25 (web/demo/search.mjs; the page and
  the evaluation run the same code). The page shows the top 3 passages with their source,
  and "Play from here" for a transcript passage.
- **When it declines.** It declines when the best passage covers less than half of the
  question's idf weight, and then suggests chapters.
- **Self-contained.** No API key, no model, and no request beyond the video next to the
  page.
- **Captions** are built in the page from the transcript, because a page opened from disk
  may not load captions.vtt.

Results: [qa-results.md](qa-results.md). They are reported as they came out, not tuned.

| Set | Questions | Top-1 | Top-3 | Declined |
|---|---:|---:|---:|---:|
| Answerable from one source | 20 | 11 | 14 | 3 wrongly |
| Needing two sources (top-3: both present) | 5 | 3 | 1 | 1 wrongly |
| Not covered | 5 | | | 1 correctly |

**Two runs.**
- **Run 1** used the index built at the recording (147 passages).
- **Run 2** used the final index. That index has 148 passages, because the README gained
  its demo section afterwards; nothing else changed.
- Every question's outcome was the same in both runs.

**A flaw the run exposed, left unfixed.** The decline rule weighs only words that appear
in some passage. A question about something the project never mentions ("Azure", "Okta",
"price") keeps its known words, so the best passage can cover all of its known weight. u02
scored 1.00 and was not declined. A rule that counts unknown words, at a typical idf, would
decline more often. Changing it after the run would be tuning on these questions, so it is
not done here (docs/backlog.md).
