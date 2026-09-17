"""
Colab Render Environment, Drive Mounting, and Asset Audit Submodule.
Adheres to Documents/Structure/01_ARCHITECTURE_CONSTRAINED_AI.md (Rule <= 150 lines/file).
"""

import os
import re
from pathlib import Path
from typing import List, Optional

import config


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
    """Finds project folder under Colab Drive or local project roots."""
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


def get_part_images(keyframes_dir: Path, part_idx: int) -> List[Path]:
    """Retrieves and deduplicates keyframe images for a specific Part."""
    raw = sorted(
        list(keyframes_dir.glob(f"beat_P{part_idx:02d}_B*.jp*g"))
        + list(keyframes_dir.glob(f"beat_P{part_idx:02d}_B*.JP*G"))
        + list(keyframes_dir.glob(f"beat_P{part_idx:02d}_B*.png"))
        + list(keyframes_dir.glob(f"beat_P{part_idx:02d}_B*.PNG"))
    )
    seen_stems = set()
    part_images = []
    for f in raw:
        if f.stem not in seen_stems:
            seen_stems.add(f.stem)
            part_images.append(f)
    return part_images


def audit_render_assets(proj_dir: Path, audio_dir: Path, keyframes_dir: Path, force_render: bool) -> None:
    """Audits 15 WAV files, keyframe count, and HITL Cover image (GK6 Parity)."""
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

    has_cover = any(bool(re.search(r"beat_P0?1_B0?1(?:\.|$|_)", k)) for k in kf_map.keys())
    if not has_cover:
        print("=" * 75)
        print("⏸️ [HUMAN-IN-THE-LOOP CHECKPOINT: COVER MISSING]")
        print("👉 Part 01 Beat 01 Cover image ('beat_P01_B01.*') is missing from keyframes!")
        print("👉 Please upload custom Cover into '02. Media Generation/keyframes/'")
        print("=" * 75)
        if not force_render:
            raise FileNotFoundError("Manual Cover image 'beat_P01_B01' is required before rendering.")
