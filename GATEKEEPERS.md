# 🛡️ GATEKEEPERS.md — Quality Gates & Dual-Operation Parity Protocol

Version: 2.0.0  
Status: ACTIVE / BINDING  
Authority: Quality Assurance & Architecture Governance (`Documents/Structure/04_PIPELINE_GATEKEEPER_DASHBOARD.md`)  
Scope: All quality audits, asset verifications, and cross-platform execution pipelines in HistorySnooze.

---

## 1. ARCHITECTURE OVERVIEW

The HistorySnooze production pipeline enforces a continuous, 7-stage quality assurance architecture (GK1 through GK7) spanning the complete lifecycle of a 90-minute 4K sleep documentary:

```
[Idea / Proposed]
       │
       ▼  GK1: 15-Part Outline Audit (Chronological arc, strictly no "dim the lights")
[Pending ➔ Script]
       │
       ▼  GK2: Full Voiceover Script Audit (1,050–1,150 words/part, 0 digits, Holy Trinity)
[Script Finalized]
       │
       ▼  GK3: Visual Prompts Audit (150–160 beats, Anchor Kit tags, max 1500 chars)
[Voiceover Synthesis]
       │
       ▼  GK4: Acoustic Deep Audio Audit (15 WAVs, >=10KB, RMS>=0.003, Peak>=0.02)
[Image Generation]
       │
       ▼  GK5: Raw Keyframe Quality Audit (>=30KB, valid headers, 16:9 ratio)
[Keyframes Assembled]
       │
       ▼  GK6: Pre-Assembly Asset & HITL Cover Check (15 WAVs + 150 Keyframes + Cover P01_B01)
       │       [PAUSES AT STATUS 'JPEG' UNTIL HUMAN APPROVES & SETS STATUS TO 'IMAGE']
[Video Rendering (GHA / Colab)]
       │
       ▼  GK7: Master Video Assembly Audit (Duration 80.0–95.0 mins, size > 500 MB)
[Ready ➔ Done (Published)]
```

---

## 2. THE 7-STAGE GATEKEEPER PIPELINE (GK1 TO GK7)

### GK1: 15-Part Outline Compliance Audit
* **Stage & Trigger**: Transition from `Proposed` / `Pending` to `Script`.
* **Primary Scope**: Validates documentary thematic pacing and narrative structure.
* **Audit Rules**:
  1. **Exact Structure**: Must contain exactly 15 sequential documentary chapters (`Part 01` through `Part 15`).
  2. **Narrative Arc**: Must follow an immersive, historically authentic, chronological narrative tailored for deep sleep induction.
  3. **Strict Prohibition of "dim the lights" in Outline**: The phrase "dim the lights" (and variations such as "turn off the lights", "dim lights") is **strictly forbidden** anywhere in the outline text. Lighting transition instructions are reserved exclusively for the Part 01 script audio cue.
* **Auditor Implementation**: `hsnooze.scripting/online_script_producer.py` (Outline generation stage).
* **Failure Handling**: Outline generation is rejected and re-prompted with negative constraints until 100% compliant.

---

### GK2: Full Voiceover Script & Holy Trinity Audit
* **Stage & Trigger**: Transition within `Script` stage prior to voiceover synthesis.
* **Primary Scope**: Validates acoustic narration duration, phonetic rendering, and storytelling structure.
* **Audit Rules**:
  1. **Word Count Ceiling & Floor**: Each part must contain between **1,050 and 1,150 words** (total ~16,000–17,250 words across 15 parts). At ASMR reading speed (~130 words/minute with silences), this guarantees an 85–92 minute audio runtime.
  2. **The 0 Digits Rule**: Strictly **ZERO numeric digits (`0-9`)** in the voiceover script. All dates, numbers, years, and measurements must be fully spelled out phonetically (e.g., *"seventeen ninety-two"* instead of *"1792"*, *"fourteen miles"* instead of *"14 miles"*, *"twenty-fourth"* instead of *"24th"*). This completely eliminates TTS engine mispronunciation.
  3. **Holy Trinity Narrative Architecture**: Every part must weave together the three core pillars of sleep documentary storytelling:
     - **Setting**: Vivid, atmospheric environmental descriptions (weather, architecture, landscapes).
     - **Character**: Meditative, calm historical presence and internal reflections.
     - **Atmosphere**: Gentle sensory triggers (rain tapping on eaves, glowing embers, distant river currents, soft wind).
  4. **Pacing Markers**: Sentences separated by 1.0s silence tags; paragraphs separated by 2.0s silence tags.
* **Auditor Implementation**: `online_script_producer.py` and `script_validator.py`.
* **Failure Handling**: Parts failing word count bounds or containing numeric digits are automatically rejected and regenerated.

---

### GK3: Visual Prompts Syntax & Anchor Kit Audit
* **Stage & Trigger**: Parsing `combined_imageprompts.txt` prior to image generation.
* **Primary Scope**: Validates visual density, beat formatting, and character/setting consistency.
* **Audit Rules**:
  1. **Prompt File Existence**: `combined_imageprompts.txt` must exist in `01. Pre-Production/` or project root.
  2. **Total Beat Count Bounds**: Total prompts must be between **150 and 160 beats** (`config.EXPECTED_MIN_BEATS = 150`, `config.EXPECTED_MAX_BEATS = 160`).
  3. **Per-Part Distribution**: Every part (1 through 15) must contain at least **10 beats** (`config.TARGET_BEATS_PER_PART = 10`).
  4. **Format & Syntax**:
     - Strict beat naming regex: `^beat_P(\d{2})_B(\d{2})(?:\.jpg|\.png|\.jpeg)?\s*:\s*(.*)$`.
     - 100% `.jpg` extension naming syntax (0% `.gif`).
     - Exactly 1 blank line (`\n\n`) separating beats.
     - Maximum 1500 characters per prompt.
  5. **Milestone 1 Anchor Kit Consistency**: Prompts must incorporate canonical reference tags:
     - `[CHARACTER]`: Consistent facial features, historical clothing, and posture.
     - `[SETTING]`: Authentic architectural era, time of day, and environmental lighting.
     - `[PROP]`: Historically accurate tools, scrolls, lanterns, or artifacts.
     - `[INGREDIENT]`: Culturally authentic materials or culinary items.
* **Auditor Implementation**: `pipeline_orchestrator.py::audit_gk3_prompts()` and `prompt_engine.py::validate_prompt()`.
* **Failure Handling**: Emits warning if `prompt_engine` is absent; raises blocking error if total prompt count or per-part distribution is deficient.

---

### GK4: Acoustic Deep Audio Quality Audit
* **Stage & Trigger**: Post-synthesis of voiceover audio in `02. Media Generation/audio/`.
* **Primary Scope**: Validates acoustic integrity, volume levels, and speech cadence.
* **Audit Rules**:
  1. **Exact File Count**: Exactly **15 WAV audio files** (`Part_01.wav` through `Part_15.wav`).
  2. **Minimum File Size**: Each WAV file must be $\ge 10\text{ KB}$ (`config.GK4_MIN_WAV_SIZE_KB = 10`).
  3. **RMS Energy Threshold**: Root Mean Square energy must be $\ge 0.003$ (`config.GK4_RMS_THRESHOLD = 0.003`) to ensure no corrupted silent audio files.
  4. **Peak Amplitude & Anti-Clipping**: Peak amplitude must be $\ge 0.02$ (`config.GK4_PEAK_THRESHOLD = 0.02`) and strictly below $0.0\text{ dBFS}$ (no clipping distortion).
  5. **Speech Rate Cadence**: Average speech cadence must be $\ge 0.15\text{ seconds/word}$ (`config.GK4_MIN_SEC_PER_WORD = 0.15`), guaranteeing an unhurried, soothing delivery.
* **Auditor Implementation**: `pipeline_orchestrator.py::audit_gk4_audio()` and `voice_chunk_engine.py::audit_wav_acoustic()`.
* **Failure Handling**: Deficient audio files are flagged, preventing progression, and re-queued for TTS synthesis.

---

### GK5: Raw Keyframe Quality & Dimension Audit
* **Stage & Trigger**: Ingestion of raw keyframe images into `02. Media Generation/keyframes/`.
* **Primary Scope**: Validates image format validity, file completeness, and aspect ratio.
* **Audit Rules**:
  1. **Minimum File Size**: Each image file must be $\ge 30\text{ KB}$ (`config.GK5_MIN_IMAGE_SIZE_KB = 30`). Filters out truncated network downloads and 0-byte placeholders.
  2. **Header & Format Integrity**: Valid JPEG/PNG magic bytes; files must decode cleanly without stream truncation.
  3. **Aspect Ratio & Resolution**: Strict **16:9 widescreen aspect ratio**, native 4K UHD ($3840 \times 2160$) preferred, minimum $1920 \times 1080$.
  4. **Naming Convention**: `beat_P{part:02d}_B{beat:02d}.jpg` (or `.png`).
* **Auditor Implementation**: Keyframe integrity probe (`image_pipeline_worker.py` / `config.py`).
* **Failure Handling**: Corrupted or undersized images are purged and re-queued for generation via `hsnooze.gflow`.

---

### GK6: Pre-Assembly Asset Integrity & HITL Cover Check
* **Stage & Trigger**: Prior to authorizing video rendering (`JPEG` $\rightarrow$ `Image`).
* **Primary Scope**: Validates asset completeness across all 15 parts and enforces the Human-in-the-Loop Cover checkpoint.
* **Audit Rules**:
  1. **Audio Completeness**: Exactly 15 WAV files verified (`Part_01.wav` .. `Part_15.wav`).
  2. **Keyframe Completeness**: At least 150 unique keyframes (`config.EXPECTED_MIN_BEATS`), with stem deduplication to avoid double-counting dual extensions (e.g. `.jpg` and `.jpeg`).
  3. **Distribution**: Every part has $\ge 10$ keyframes (`config.TARGET_BEATS_PER_PART = 10`).
  4. **The HITL Cover Gate (`beat_P01_B01.*`)**:
     - Status `JPEG`: If keyframes exist but Cover is missing or Status is `JPEG`, the pipeline **hard-pauses**. It displays a terminal checkpoint banner and blocks video rendering.
     - Status `Image` without Cover: Raises `ValueError: Cannot render: Status is 'Image' but manual Cover image 'beat_P01_B01' is missing!`.
     - Status `Image` with Cover: When `beat_P01_B01.*` is placed in `keyframes/` and Status is promoted to `Image` on Google Sheets, GK6 passes and authorizes video rendering.
* **Auditor Implementation**: `pipeline_orchestrator.py::audit_gk6_assets()` and `handle_image_generation_stage()`.
* **Failure Handling**: Hard block on Status `JPEG`; halts execution until human operator resolves.

---

### GK7: Master 90-Minute Video Quality & Duration Audit
* **Stage & Trigger**: Post-concatenation of `master_final_90min.mp4` (`Video` $\rightarrow$ `Ready`).
* **Primary Scope**: Validates duration, file size, pacing, and stream integrity of the final documentary.
* **Audit Rules**:
  1. **Master Artifact Existence**: `master_final_90min.mp4` exists in `03. Final Production/` and `output/`.
  2. **Duration Compliance**: Total duration must be between **80.0 minutes and 95.0 minutes** (`config.GK7_MIN_VIDEO_DURATION_MIN = 80`, `config.GK7_MAX_VIDEO_DURATION_MIN = 95`).
  3. **File Size Compliance**: Total file size must exceed **500 MB** (`size_bytes > 500 * 1024 * 1024`).
  4. **Inter-Part Sleep Pacing**: Must contain exactly 14 inter-part silence gaps of **5.0 seconds** each (`config.INTER_PART_SILENCE_SEC = 5.0`).
  5. **Stream Integrity**: Verified via `ffprobe`: exactly 1 video stream (H.264/AVC 3840x2160 @ 30fps) and 1 audio stream (AAC/MP3 stereo 48kHz).
  6. **Lossless Assembly**: Assembled via FFmpeg stream copy (`-c copy`) in under 30 seconds.
* **Auditor Implementation**: `pipeline_orchestrator.py::audit_gk7_master()` and `master_assembler.py::assemble_master_video()`.
* **Failure Handling**: GK7 failure prevents promotion to `Ready`; logs diagnostic report and halts pipeline.

---

## 3. DUAL-OPERATION PARITY PROTOCOL (GHA & COLAB)

### 3.1. The Parity Mandate
*"Mọi sự thay đổi một cách tích cực, đều được cập nhật trên cả 2 operation versions."*  
Every architectural improvement, bug fix, or optimization must be strictly maintained across both rendering environments:
* **Operation Version A**: GitHub Actions Distributed Matrix (`.github/workflows/render_parallel.yml` + `render_single_part.py` + `assemble_master.py`).
* **Operation Version B**: Google Colab GPU CLI Runner (`colab_render_runner.py`).

### 3.2. Seven Parity Checkpoints

| # | Feature / Checkpoint | Version A (GitHub Actions) | Version B (Google Colab) | Parity Standard |
|---|---|---|---|---|
| **1** | **Asset Ingestion & Safe Tarball** | `download_drive_assets.py` & GitHub Release CDN; `safe_extract_tarball()` | `download_drive_assets.py` & Drive mount; `safe_extract_tarball()` | CVE-2007-4559 neutralized; member targets validated |
| **2** | **Lighting & Stardust Shader** | Cosine ease-in stardust ($t_0 \to t_1$) on Part 1 Beat 1; `DEFAULT_VIGNETTE = "none"` | Cosine ease-in stardust ($t_0 \to t_1$) on Part 1 Beat 1; `DEFAULT_VIGNETTE = "none"` | Uniform dimming; zero black oval border vignette |
| **3** | **HITL Cover Gate** | Halts on Part 1 if `beat_P01_B01.*` missing | Halts on Part 1 if `beat_P01_B01.*` missing unless `--force` | Blocks render on missing Cover |
| **4** | **Hardware / Memory Clamping** | CPU multi-worker clamped to available RAM ($\ge 3.5\text{ GB}$/worker) | GPU NVENC clamped to max 2 sessions; automatic CPU fallback | Zero Linux OOM kills; zero NVENC session limit crashes |
| **5** | **Inter-Part Silence Insertion** | 14x 5.0-second silence clips between parts in `assemble_master.py` | 14x 5.0-second silence clips between parts in `master_assembler.py` | Exactly 5.0s sleep pacing gap |
| **6** | **GK7 Master Audit** | ffprobe check: duration $\ge 80.0\text{ min}$, size $> 500\text{ MB}$ | ffprobe check: duration $\ge 80.0\text{ min}$, size $> 500\text{ MB}$ | Identical validation math |
| **7** | **Output Hierarchy** | Chunks in `output/chunk_part_*.mp4`, master in `output/master_final_90min.mp4` | Chunks in `output/chunk_part_*.mp4`, master in `output/master_final_90min.mp4` | Canonical output paths mirrored |

### 3.3. Automated Parity Verification
Parity is verified by the automated test suite:
```bash
pytest tests/test_dual_operation_parity.py -v
```
All 7 checkpoints must pass with 0 failures before any change to the rendering pipeline is accepted.
