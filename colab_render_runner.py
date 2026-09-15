"""
HISTORYSNOOZE: GOOGLE COLAB VIDEO RENDER RUNNER (COLAB-CLI COMPLIANT)
Module: colab_render_runner.py
Version: 1.0.0
Purpose:
  - Official Colab runner for 90-minute video rendering on GPU (T4/L4 NVENC / CUDA).
  - Native Google Drive mount (/content/drive/MyDrive/) eliminating upload/download overhead.
  - Sequential or selective Part rendering (--parts 1,2,3) with Smart Delta Restart.
  - Sub-pixel anti-jitter Ken Burns zoompan with micro-step precision.
  - 5.0-second silence insertion between parts for sleep pacing.
  - Gatekeeper GK7 Video Quality & Duration Audit (80-95 min).
  - Updates Google Sheet Dashboard (Col M: Video -> Done, Col D: Status -> Video).
"""

import os
import sys
import glob
import time
import argparse
from pathlib import Path
from datetime import datetime
from typing import List, Optional, Dict

import config
from chunk_renderer import render_part_chunk, is_chunk_valid
from master_assembler import assemble_master_video
from kenburns_asmr import check_nvenc_available


def mount_colab_drive() -> Path:
    """Mounts Google Drive natively in Colab environment."""
    try:
        from google.colab import drive
        print("[Colab] Mounting Google Drive to /content/drive...")
        drive.mount('/content/drive')
        return Path("/content/drive/MyDrive")
    except ImportError:
        print("[Colab] Running outside Google Colab environment.")
        return Path("./gdrive_mount")


def find_project_dir(base_name: str) -> Optional[Path]:
    """Finds project folder under /content/drive/MyDrive/historysnooze posts/"""
    candidates = [
        Path("/content/drive/MyDrive/historysnooze posts") / base_name,
        Path("/content/drive/MyDrive") / base_name,
        Path("./historysnooze posts") / base_name,
        Path(".") / base_name,
    ]
    for c in candidates:
        if c.exists() and (c / "02. Media Generation").exists():
            return c
    return None


def run_colab_render(
    project_folder_path: str,
    parts_to_process: Optional[List[int]] = None,
    force_cpu: bool = False,
    folder_id: Optional[str] = None,
    sheet_id: Optional[str] = None,
    row_index: Optional[int] = None,
    max_workers: int = 2,
    force_render: bool = False
):
    proj_dir = Path(project_folder_path).resolve()

    # If folder_id is supplied and assets are missing, download via download_drive_assets (GHA parity)
    audio_dir = proj_dir / "02. Media Generation" / "audio"
    keyframes_dir = proj_dir / "02. Media Generation" / "keyframes"
    if folder_id and (not audio_dir.exists() or len(list(audio_dir.glob("Part_*.wav"))) < 15):
        print(f"[Colab] Syncing assets from Drive folder: {folder_id}...")
        from download_drive_assets import download_project_assets
        download_project_assets(folder_id, str(proj_dir))

    if not proj_dir.exists():
        raise FileNotFoundError(f"Project directory does not exist: {proj_dir}")

    chunks_dir = proj_dir / "02. Media Generation" / "chunks"
    final_dir = proj_dir / "03. Final Production"
    output_dir = proj_dir / "output"

    # Optimization: Use fast local NVMe/SSD (/content/temp_render) on Colab instead of slow Drive FUSE
    if os.path.exists("/content"):
        temp_dir = Path("/content/temp_render")
    else:
        temp_dir = proj_dir / "02. Media Generation" / "temp"

    chunks_dir.mkdir(parents=True, exist_ok=True)
    temp_dir.mkdir(parents=True, exist_ok=True)
    final_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    has_nvenc = (not force_cpu) and check_nvenc_available()
    print("=" * 75)
    print(f"HISTORYSNOOZE COLAB VIDEO RENDERER (v1.1.0 - GHA Parity): {proj_dir.name}")
    print(f"GPU NVENC Acceleration: {'ENABLED (Fast GPU)' if has_nvenc else 'DISABLED (CPU libx264)'}")
    print(f"Target Resolution: {config.RESOLUTION} @ {config.FPS} FPS")
    print(f"Inter-part Silence: {config.INTER_PART_SILENCE_SEC}s")
    print(f"Scratch Temp Directory: {temp_dir} (Fast Local I/O)")
    print("=" * 75)

    # 1. Asset audit & Human-in-the-Loop Cover Check (GK6 Parity)
    wav_files = sorted(audio_dir.glob("Part_*.wav"))
    kf_map = {}
    for ext in ("*.jpg", "*.jpeg", "*.png", "*.JPG", "*.JPEG", "*.PNG"):
        for f in sorted(keyframes_dir.glob(f"beat_{ext}")):
            if f.stem not in kf_map:
                kf_map[f.stem] = f
    keyframe_files = [kf_map[k] for k in sorted(kf_map.keys())]

    print(f"[ASSET CHECK] Found {len(wav_files)}/15 audio parts, {len(keyframe_files)} keyframes.")
    if len(wav_files) != 15:
        print(f"⚠️ Warning: Expected 15 WAV files, found {len(wav_files)}.")
    if len(keyframe_files) < config.EXPECTED_MIN_BEATS:
        print(f"⚠️ Warning: Found {len(keyframe_files)} keyframes (min recommended: {config.EXPECTED_MIN_BEATS}).")

    # Cover Image Verification (HITL)
    import re
    has_cover = any(
        bool(re.search(r"beat_P0?1_B0?1(?:\.|$|_)", k))
        for k in kf_map.keys()
    )
    if not has_cover:
        print("=" * 75)
        print("⏸️ [HUMAN-IN-THE-LOOP CHECKPOINT: COVER MISSING]")
        print("👉 Part 01 Beat 01 Cover image ('beat_P01_B01.*') is missing from keyframes!")
        print("👉 Please upload your custom Cover image into '02. Media Generation/keyframes/'")
        print("   and change Status on Google Sheet to 'Image' before rendering.")
        print("=" * 75)
        if not force_render:
            raise FileNotFoundError("Manual Cover image 'beat_P01_B01' is required before rendering.")

    parts = parts_to_process if parts_to_process else list(range(1, 16))
    print(f"Processing Parts: {parts}")

    # 2. Render Chunks with Smart Delta Restart
    from pipeline_orchestrator import link_or_copy_artifact
    chunk_paths = []
    t_start = time.time()

    for part_idx in range(1, 16):
        chunk_file = chunks_dir / f"chunk_part_{part_idx:02d}.mp4"

        if part_idx not in parts:
            if chunk_file.exists() and is_chunk_valid(str(chunk_file)):
                print(f"[SKIP] Part {part_idx:02d} already valid and not requested in filter.")
                chunk_paths.append(str(chunk_file))
                try:
                    link_or_copy_artifact(str(chunk_file), str(output_dir))
                except Exception:
                    pass
            continue

        audio_file = audio_dir / f"Part_{part_idx:02d}.wav"
        raw_part_images = sorted(
            list(keyframes_dir.glob(f"beat_P{part_idx:02d}_B*.jp*g"))
            + list(keyframes_dir.glob(f"beat_P{part_idx:02d}_B*.JP*G"))
            + list(keyframes_dir.glob(f"beat_P{part_idx:02d}_B*.png"))
            + list(keyframes_dir.glob(f"beat_P{part_idx:02d}_B*.PNG"))
        )
        seen_stems = set()
        part_images = []
        for f in raw_part_images:
            if f.stem not in seen_stems:
                seen_stems.add(f.stem)
                part_images.append(f)

        if not audio_file.exists():
            raise FileNotFoundError(f"Missing audio file: {audio_file}")
        if not part_images:
            raise FileNotFoundError(f"No keyframes found for Part {part_idx:02d}")

        print(f"\n>>> [PART {part_idx:02d}/15] Rendering chunk with {len(part_images)} beats...")
        part_t0 = time.time()
        chunk_mp4 = render_part_chunk(
            part_index=part_idx,
            audio_wav_path=str(audio_file),
            beat_images=[str(img) for img in part_images],
            output_dir=str(chunks_dir),
            temp_dir=str(temp_dir),
            force_cpu=force_cpu,
            max_workers=max_workers
        )
        chunk_paths.append(chunk_mp4)

        # GHA Parity: Mirror output chunk to output/
        try:
            link_or_copy_artifact(chunk_mp4, str(output_dir))
        except Exception:
            pass

        elapsed = time.time() - part_t0
        print(f"✓ [PART {part_idx:02d}/15] Rendered in {elapsed:.1f}s ({os.path.getsize(chunk_mp4)/1024/1024:.1f} MB)")

    total_render_time = time.time() - t_start
    print(f"\nAll 15 Chunks rendered/verified in {total_render_time/60:.1f} minutes.")

    # 3. Assemble Master Video
    if len(chunk_paths) == 15:
        master_mp4 = final_dir / "master_final_90min.mp4"
        print(f"\n>>> [MASTER ASSEMBLY] Concatenating 15 parts with {config.INTER_PART_SILENCE_SEC}s silence...")
        master_result = assemble_master_video(
            chunk_paths=chunk_paths,
            output_master_path=str(master_mp4),
            temp_dir=str(temp_dir)
        )

        # GHA Parity: Mirror master output to output/master_final_90min.mp4
        try:
            link_or_copy_artifact(str(master_mp4), str(output_dir))
        except Exception:
            pass

        print("=" * 75)
        print(f"MASTER VIDEO GENERATION COMPLETE!")
        print(f"File: {master_mp4}")
        print(f"Output Artifact: {output_dir / 'master_final_90min.mp4'}")
        print(f"Duration: {master_result.get('duration_minutes', 0):.2f} minutes")
        print(f"Size: {master_result.get('file_size_gb', 0):.2f} GB")
        print(f"Gatekeeper GK7 Audit: {'PASSED ✓' if master_result.get('passed_gk7') else 'FAILED ✗'}")
        print("=" * 75)

        return master_result
    else:
        print(f"[NOTICE] Processed partial parts ({len(chunk_paths)}/15). Run with all parts to assemble master.")
        return None


def main():
    parser = argparse.ArgumentParser(description="HistorySnooze Colab Video Render Runner")
    parser.add_argument("project_dir", nargs="?", default="", help="Path to project root directory (default: ./project_assets)")
    parser.add_argument("--project-dir", dest="project_dir_opt", type=str, default="", help="Alternative project dir option")
    parser.add_argument("--folder-id", type=str, default="", help="Google Drive Project Folder ID (GHA input parity)")
    parser.add_argument("--parts", type=str, default="", help="Comma-separated parts to render (e.g. 1,2,3)")
    parser.add_argument("--cpu", action="store_true", help="Force CPU libx264 encoding")
    parser.add_argument("--workers", type=int, default=2, help="Max FFmpeg parallel workers (default: 2)")
    parser.add_argument("--mount-drive", action="store_true", help="Mount Colab Drive before running")
    parser.add_argument("--force", action="store_true", help="Force render even if Cover check warns")
    args = parser.parse_args()

    if args.mount_drive:
        mount_colab_drive()

    proj_dir = args.project_dir_opt or args.project_dir or "./project_assets"
    parts = [int(p.strip()) for p in args.parts.split(",") if p.strip()] if args.parts else None

    run_colab_render(
        project_folder_path=proj_dir,
        parts_to_process=parts,
        force_cpu=args.cpu,
        folder_id=args.folder_id or None,
        max_workers=args.workers,
        force_render=args.force
    )


if __name__ == "__main__":
    main()
