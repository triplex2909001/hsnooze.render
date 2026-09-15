# 🏛️ AGENTS.md — HistorySnooze Autonomous Operational Constitution

Version: 2.0.0  
Status: ACTIVE / BINDING  
Authority: Architecture Governance Board (`Documents/Structure/01_ARCHITECTURE_CONSTRAINED_AI.md`)  
Scope: All autonomous AI agents, subagents, scripts, and human developers in the HistorySnooze ecosystem.

---

## 1. CORE MISSION & IDENTITY

HistorySnooze is an automated, high-precision media engineering ecosystem dedicated to producing 90-minute 4K Ultra-HD sleep and meditation documentaries. The ecosystem operates across a distributed, zero-cost cloud and containerized infrastructure.

Every agent working on this repository must operate under **Constrained AI Engineering**: AI agents do not invent architecture or modify established system boundaries. Agents act strictly as bounded implementers adhering to this Constitution, `GATEKEEPERS.md`, and the project Single Source of Truth (`config.py`).

---

## 2. HOST INFRASTRUCTURE & ROLE BOUNDARIES

### 2.1. Host VPS Role: Generation & Dispatch Station ONLY
The host virtual private server (`vpsg24gb` at `/media/vpsg24gb/DATA/historysnooze/`) is dedicated **exclusively** to two functions:
1. **Image Generation Station**: Executing `hsnooze.gflow` (Node.js LTS 20+ and Headless Google Chrome via Playwright/CDP) to drive ImageFX/Flow and download 4K visual assets.
2. **Central Orchestrator & Dispatcher**: Executing `pipeline_orchestrator.py` to manage state transitions across the Google Sheet Central Dashboard, validate assets, package input payloads, and dispatch rendering jobs to cloud execution environments.

### 2.2. ABSOLUTE PROHIBITION: ZERO VIDEO RENDERING ON HOST VPS
* **MANDATE**: **ZERO video rendering occurs on the host VPS (`vpsg24gb`)**.
* Under no circumstances may an agent, script, or workflow invoke FFmpeg video encoding, Ken Burns zoompan filtergraphs, overlay synthesis, chunk rendering, or master video assembly on `vpsg24gb`.
* **Rationale**: The VPS host must maintain 100% operational stability, low thermal load, and zero memory exhaustion. Heavy FFmpeg 4K 60fps/30fps rendering consumes 100% CPU/GPU, exhausts system RAM, triggers Linux kernel OOM kills (SIGKILL 137), and starves interactive services.
* **Enforcement**: Any agent attempting to invoke `chunk_renderer.py`, `render_single_part.py`, or `assemble_master.py` locally on the host VPS violates this constitution and must immediately halt.

### 2.3. Distributed Heavy Compute Offload
All heavy video rendering is strictly offloaded to dedicated distributed compute runners:
* **Offload Environment A (GitHub Actions)**: `.github/workflows/render_parallel.yml` running 15-way parallel matrix jobs on ephemeral Ubuntu cloud runners (`render_single_part.py`), uploading chunk artifacts, and concatenating via `assemble_master.py`.
* **Offload Environment B (Google Colab)**: `colab_render_runner.py` running on hardware-accelerated GPU instances (NVIDIA T4/L4 NVENC / CUDA) with memory-bounded concurrency and automatic CPU fallback.

---

## 3. STRICT MODULARITY & CODE QUALITY STANDARDS

### 3.1. The 150-Line Modularity Limit
* **Hard Ceiling**: No source code file (`.py`, `.ts`, `.js`, `.sh`) may exceed **150 lines of code** (excluding documentation comments and blank lines).
* **Single Responsibility Principle (SRP)**: Each file must perform exactly one conceptual function. 
* **Monolithic Code Decomposition**: Any script that expands beyond 150 lines must be split into dedicated submodules (e.g., separating cue parsing, shader construction, asset verification, and process execution into discrete files).
* **AI Context Window Protection**: Keeping files under 150 lines prevents "Context Rot" and token bloat, ensuring that agents maintain sharp, zero-hallucination context.

### 3.2. Deterministic Non-LLM Processing
* Core engineering mechanics—including SHA-256 content hashing, FFmpeg command generation, audio LUFS normalization, audio RMS/Peak calculation, file size checks, and concatenation—must remain **100% deterministic pure Python/Node code**.
* Never permit an LLM to perform numerical calculations, file parsing, or quality audits. LLM usage is restricted to creative text generation (scripting, titles, prompts).

### 3.3. Self-Healing Network I/O
* Every network I/O interaction (Google Drive API v3, Google Sheets API, GitHub Releases, Cloudflare, Buffer API) must be wrapped in robust error handling with **minimum 3 retries** and exponential backoff.
* Network failures must never silently corrupt pipeline state; they must either recover cleanly or transition the task into an explicit error state with actionable diagnostic logs.

### 3.4. Test-Driven Development (TDD) Mandate
* No feature or bug fix may be merged without accompanying automated tests.
* Tests must be written or verified first to validate expected failure, followed by minimal code changes to achieve a passing suite (`pytest tests/`).

---

## 4. HUMAN-IN-THE-LOOP (HITL) STATE MACHINE & PROTOCOLS

### 4.1. Lifecycle Status State Machine
The production lifecycle progresses strictly through 9 discrete states defined in `config.STATUS_FLOW`:
```
Proposed ➔ Pending ➔ Script ➔ Voiceover ➔ JPEG ➔ Image ➔ Video ➔ Ready ➔ Done
```

### 4.2. Status `JPEG` Checkpoint: The Cover Image Exemption
* **Automated Image Generation Boundary**: When the orchestrator executes automated keyframe generation at Status `Voiceover`, it generates keyframes for Beats 2 through 10 of Part 1, and Beats 1 through 10 of Parts 2 through 15 (149–159 total beats).
* **Cover Exemption**: Automated generation **strictly skips the Part 1 Beat 1 Cover image (`beat_P01_B01`)**.
* **Status `JPEG` Pause**: Upon completing automated keyframe generation, the pipeline automatically transitions status from `Voiceover` to `JPEG`.
* **Hard Render Block**: While status is `JPEG`, all video rendering is **strictly blocked**. The pipeline pauses execution and awaits human creative intervention.

### 4.3. Human Cover Placement & Status Promotion Protocol
1. **Human Action Required**: A human designer crafts a bespoke, high-click-through-rate (CTR) YouTube Cover image.
2. **Asset Placement**: The human uploads the custom cover as `beat_P01_B01.jpg` (or `.png`) directly into `02. Media Generation/keyframes/`.
3. **Status Promotion**: The human opens the Google Sheets Dashboard and changes Column D (`Status`) from `JPEG` to `Image`.
4. **Gatekeeper Validation**: When the orchestrator detects Status `Image`, it executes `pipeline_orchestrator.handle_image_generation_stage()`. If `beat_P01_B01.*` is present, render execution is authorized. If the Cover is missing, the system immediately raises a blocking `ValueError` and prevents rendering.

---

## 5. SECURITY CONSTRAINTS & ZERO-LEAK POLICY

### 5.1. Non-Root Execution
* All processes inside containers and on the host must run strictly as non-root user `appuser` (UID `1000`, GID `1000`).
* Root execution (`sudo`, `user: "0:0"`) inside application containers is strictly prohibited.
* Linux capability drops are enforced in container runtimes: `cap_drop: [ALL]`, `security_opt: [no-new-privileges:true]`.

### 5.2. Zero-Leak Credential Management
* **Zero Hardcoded Secrets**: No API keys, Google tokens, Telegram bot tokens, or private credentials may ever be hardcoded in source code, committed to Git, or stored in unencrypted persistent files.
* **Read-Only Mounting**: Host credential profiles (`~/.cloud-profiles/historysnooze`) must be mounted into containers strictly as read-only (`:ro`).
* **RAM-Only Temporary Vault**: In-memory decryption of credentials occurs strictly in volatile RAM (`tmpfs: /dev/shm:rw,noexec,nosuid,size=512m`). Secrets in RAM vanish immediately when the container terminates.
* **Pre-Commit Enforcement**: Gitleaks and TruffleHog pre-commit hooks block any commit containing token signatures or unencrypted secret keys.

### 5.3. Telegram Bot Isolation
* Every container and project profile has a dedicated 1-to-1 Telegram Bot Token binding.
* Cross-container bot token borrowing is strictly prohibited. If a token fails, the agent must halt and log an alert rather than attempting to use credentials from another project.

---

## 6. DUAL-OPERATION PARITY MANDATE

* **Constitutional Rule**: *"Mọi sự thay đổi một cách tích cực, đều được cập nhật trên cả 2 operation versions."* (Every positive improvement, optimization, or fix must be strictly maintained across BOTH operation versions).
* Any functional improvement applied to GitHub Actions (`.github/workflows/render_parallel.yml`) must be mirrored in Google Colab (`colab_render_runner.py`), and vice versa.
* Parity is verified automatically via `tests/test_dual_operation_parity.py`.

---

## 7. AGENT CONDUCT & ESCALATION PROTOCOL

1. **Check Status First**: Before executing any task, read current state from `config.py` and the Google Sheet Central Dashboard.
2. **Never Overwrite User Customizations**: Do not delete existing custom Cover images, manually polished scripts, or user voice recordings.
3. **Stop & Escalate on Ambiguity**: When encountering corrupted assets, missing credentials, or unexpected gatekeeper rejections, stop execution, log the exact file path and line number, and alert the human supervisor.
