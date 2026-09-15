# Original User Request

## Initial Request — 2026-09-13T01:09:32Z

Comprehensive code audit, architectural review, and risk assessment of the `hsnooze.render` video rendering pipeline codebase.

Working directory: /Users/hanario/Documents/HistorySnooze/hsnooze.render
Integrity mode: development

## Requirements

### R1. Comprehensive Logical & Static Code Audit
Audit all Python source modules in the repository (`pipeline_orchestrator.py`, `chunk_renderer.py`, `beat_aligner.py`, `cue_extractor.py`, `kenburns_asmr.py`, `image_pipeline_worker.py`, `generate_ambient_stardust.py`, `render_single_part.py`, `master_assembler.py`, `assemble_master.py`, `colab_render_runner.py`, `download_drive_assets.py`, `config.py`) for:
- Silent failures, missing exception handling, and error propagation issues.
- Subprocess, FFmpeg command construction vulnerabilities, and pipe deadlock risks.
- Temporary file management, resource leaks, and disk space / RAM overhead.
- Race conditions, shared state bugs, and multiprocessing synchronization flaws.

### R2. Pipeline Architecture & Scalability Review
Analyze the end-to-end video production workflow:
- Data flow and intermediate artifact handoffs between cue extraction, image processing, audio/beat alignment, chunk rendering, and master assembly.
- Scalability and portability across local machines and cloud/Colab environments (`colab_render_runner.py`).
- Configuration management consistency and environmental variable dependencies (`config.py`).

### R3. Structured Audit Deliverable
Deliver a comprehensive markdown report (`AUDIT_REPORT.md`) saved directly in the working directory, categorized with standard severity levels (Critical, High, Medium, Low, Info) and prioritized recommendations.

## Acceptance Criteria

### Audit Coverage & Depth
- [ ] All active Python scripts in the project are examined and explicitly covered in the report.
- [ ] Each reported vulnerability or bug includes the specific file path, approximate line numbers, description of the failure trigger, and impact analysis.
- [ ] FFmpeg subprocess calls, memory handling during video generation, and temp directory cleanup are evaluated with dedicated sections.

### Actionability & Quality of Deliverable
- [ ] Includes an Executive Summary with an overall health score/rating and high-level risk profile.
- [ ] Provides concrete, step-by-step remediation advice for all Critical and High severity findings.
- [ ] The completed audit is written to `/Users/hanario/Documents/HistorySnooze/hsnooze.render/AUDIT_REPORT.md` without modifying existing project code files.

## Follow-up — 2026-09-13T05:02:27Z

This is a single self-contained fix; keep it small and focused. Implement the Phase 1 (Sprint 1 / P0 Blockers) remediation plan detailed in AUDIT_REPORT.md to ensure the hsnooze.render video pipeline executes safely and reliably across both macOS and Linux/GitHub Actions environments.

Working directory: /Users/hanario/Documents/HistorySnooze/hsnooze.render
Integrity mode: development

## Requirements

### R1. Storage & Memory Safeguards
- Eliminate redundant triple-copy video duplication in pipeline_orchestrator.py (which currently inflates storage by 75–85 GB) by replacing it with canonical single-source paths or symlinks.
- Clamp maximum concurrent rendering workers in chunk_renderer.py based on available system RAM (minimum 3.5 GB per worker) to eliminate Linux kernel OOM kills (SIGKILL 137).
- Bound 8K zoompan filtergraph allocation in kenburns_asmr.py to prevent memory blowup during Pan/Zoom frame synthesis.

### R2. Concurrency & Subprocess Robustness
- Guarantee cleanup of intermediate beat clips (beat_PXX_BXX.mp4) and concat lists in chunk_renderer.py using try...finally blocks upon both success and failure.
- Implement robust hardware encoding fallback in kenburns_asmr.py: if h264_nvenc fails due to session limits (NVIDIA 3-session cap) or driver error, automatically fall back to CPU libx264.

### R3. Environment Portability & Security Hardening
- Remove hardcoded developer host paths (/Users/hanario/...) in image_pipeline_worker.py and replace with dynamic resolution (Path.home() or repository-relative root) so the pipeline runs seamlessly on Linux, GitHub Actions, and macOS.
- Neutralize the Tar Slip arbitrary file write vulnerability (CVE-2007-4559) in download_drive_assets.py and render_single_part.py by validating extraction member targets.
- Ensure Gatekeeper GK3 in pipeline_orchestrator.py warns rather than terminating the pipeline when optional modules are absent.

### R4. Verification & Validation
- Validate that all modified Python source files pass syntax and bytecode compilation (python3 -m py_compile).
- Provide independent verification showing memory clamping, symlink/canonical storage, and path resolution behave correctly.

## Acceptance Criteria

### Storage & Concurrency
- [ ] pipeline_orchestrator.py retains a single canonical file copy for chunks and master video; redundant copies in multiple subdirectories are replaced with symlinks or direct references.
- [ ] Worker concurrency in chunk_renderer.py is safely bounded by detected RAM and GPU capabilities (maximum 2 NVENC sessions concurrently).
- [ ] Intermediate beat clips are deterministically removed from temp_dir once chunk assembly succeeds or aborts.

### Portability & Safety
- [ ] Zero instances of hardcoded /Users/hanario exist in any active project Python module.
- [ ] tarfile.extractall() is protected against path traversal across all download routines.
- [ ] NVENC encoding failures cleanly switch to libx264 without crashing the render worker.

### Code Quality & Non-Regression
- [ ] All modified scripts pass python -m py_compile with zero syntax or indentation errors.
- [ ] 4K output resolution (3840x2160), 30 fps framerate, and ASMR audio quality are strictly preserved.

## Follow-up — 2026-09-13T10:27:58Z

Deploy and containerize the HistorySnooze ecosystem from macOS (/Users/hanario/Documents/HistorySnooze/) to vpsg24gb:/media/vpsg24gb/DATA/historysnooze/ adhering to /home/vpsg24gb/Documents/Structure/ (00_TONG_QUAN.md & 03_SECURE_ISOLATION_VAULT.md).

Working directory: /Users/hanario/Documents/HistorySnooze/hsnooze.render
Destination host: vpsg24gb
Destination directory: /media/vpsg24gb/DATA/historysnooze/

## Core Principle & Mandates:
1. ROLE BOUNDARY: VPS (vpsg24gb) is strictly the Image Generation Station (gflow Node.js + headless Chrome) and Central Orchestrator/Dispatcher. ZERO video rendering occurs on the VPS. All video rendering is offloaded to GitHub Actions (render_parallel.yml) and Google Colab (colab_render_runner.py).
2. DUAL-OPERATION PARITY MANDATE: "Mọi sự thay đổi một cách tích cực, đều được cập nhật trên cả 2 operation versions." Every positive improvement, optimization, or fix must be strictly maintained across BOTH GitHub Actions (.github/workflows/render_parallel.yml) and Google Colab (colab_render_runner.py).

## Requirements:

### R1. Clean Synchronized Migration via rsync
- Synchronize all HistorySnooze submodules (hsnooze.render, hsnooze.scripting, hsnooze.gflow, assets, 00.codebases, tests) from macOS (/Users/hanario/Documents/HistorySnooze/) to vpsg24gb:/media/vpsg24gb/DATA/historysnooze/ over SSH.
- Exclude platform-specific and transient files: .DS_Store, __pycache__, *.pyc, .pytest_cache, .ruff_cache, local temp/ directories, and intermediate video files.
- Ensure proper directory permissions on the VPS (owner vpsg24gb:vpsg24gb, uid:gid 1000:1000).

### R2. Secure Containerization per Documents/Structure Standards
- Implement the 4-file container specification defined in /home/vpsg24gb/Documents/Structure/03_SECURE_ISOLATION_VAULT.md:
  1. docker/Dockerfile: Python 3.10+, FFmpeg probe/utility, Node.js/npm for gflow, non-root user (vscode or appuser with uid:gid 1000:1000), and headless Chrome runtime dependencies.
  2. docker/docker-compose.yml: Non-root execution, security_opt: [no-new-privileges:true], cap_drop: [ALL], workspace volume mount, and RAM-Only temporary storage (tmpfs: /dev/shm:rw,noexec,nosuid,size=64m).
  3. docker/entrypoint.sh & run.sh: Automated startup script enforcing --rm ephemeral lifecycle and read-only secrets mounting (:ro).
  4. .devcontainer/devcontainer.json: Standardized non-root VS Code / DevContainer development configuration.
- Implement project architecture governance documents:
  - AGENTS.md: Defining pipeline boundaries (VPS = gflow & dispatch only; zero heavy video rendering on host VPS), strict modularity, and human-in-the-loop rules.
  - GATEKEEPERS.md: Documenting Gatekeepers GK1 through GK7, the JPEG HITL pause, and dual dispatch protocols for GHA & Colab.

### R3. Dual-Operation Parity Mandate & Automated Validation
- Ensure 100% operational parity between:
  - Operation Version A (GitHub Actions): .github/workflows/render_parallel.yml
  - Operation Version B (Google Colab): colab_render_runner.py
- Verify both platforms implement:
  - Google Drive folder ID & GitHub Release CDN asset download with safe tarball extraction (CVE-2007-4559 patched).
  - Cosine stardust fade-in at "dim the lights" and uniform screen dimming (no black oval vignette).
  - Human-in-the-Loop GK6 Cover check: blocks if status is JPEG, continues when Cover is placed and status is Image.
  - Stream copy (-c copy) master assembly with 5.0s inter-part silences.
  - Gatekeeper GK7 audit: duration >= 80 mins and size > 500 MB.
  - Output hierarchy: chunk_part_*.mp4 and master_final_90min.mp4 in output/.
- Write an automated dual-parity validation test (tests/test_dual_operation_parity.py) confirming step-by-step equivalence between GHA and Colab.

### R4. Container Build & Remote Smoke Testing
- Build and boot the Docker container on vpsg24gb via run.sh or docker compose.
- Inside the container, execute smoke tests:
  - Verify non-root user (whoami, id).
  - Verify python3 -m py_compile across all Python files with 0 errors.
  - Verify Node.js and gflow prerequisites.
  - Run the test suite (test_phase1_remediation.py, test_hitl_and_dimming.py, test_dual_operation_parity.py).
- Deliver a comprehensive deployment summary report.

