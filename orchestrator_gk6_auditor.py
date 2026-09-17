"""
HistorySnooze Director - Gatekeepers GK6 & GK7 Auditor
Validates pre-assembly keyframes/audio and master 90-min concatenation (Rule <= 150 lines).
"""

import glob
import os
import subprocess
from typing import Any, Dict, List, Optional

try:
    import config
except ImportError:
    config = None


def audit_gk6_assets(project_root: str) -> Dict[str, Any]:
    """Gatekeeper GK6 PreAssembly-Asset Auditor."""
    audio_candidates = [
        os.path.join(project_root, "02. Media Generation", "audio"),
        os.path.join(project_root, "audio"),
    ]
    audio_dir = next((c for c in audio_candidates if os.path.isdir(c) and glob.glob(os.path.join(c, "Part_*.wav"))), audio_candidates[0])

    keyframes_candidates = [
        os.path.join(project_root, "02. Media Generation", "keyframes"),
        os.path.join(project_root, "keyframes"),
        os.path.join(project_root, "hsnooze.render", "keyframes"),
    ]
    keyframes_dir = next((c for c in keyframes_candidates if os.path.isdir(c) and glob.glob(os.path.join(c, "beat_*.*"))), keyframes_candidates[0])

    total_parts = getattr(config, "TOTAL_PARTS", 15) if config else 15
    min_beats = getattr(config, "EXPECTED_MIN_BEATS", 150) if config else 150
    target_per_part = getattr(config, "TARGET_BEATS_PER_PART", 10) if config else 10

    wav_files = sorted(glob.glob(os.path.join(audio_dir, "Part_*.wav")))
    raw_imgs: List[str] = []
    for ext in ("*.jpg", "*.jpeg", "*.png", "*.JPG", "*.JPEG", "*.PNG"):
        raw_imgs.extend(glob.glob(os.path.join(keyframes_dir, f"beat_{ext}")))
    raw_imgs.sort()

    seen_stems = set()
    img_files = []
    for f in raw_imgs:
        stem = os.path.splitext(os.path.basename(f))[0]
        if stem not in seen_stems:
            seen_stems.add(stem)
            img_files.append(f)

    details = []
    has_15_audio = (len(wav_files) == total_parts)
    if not has_15_audio:
        details.append(f"Expected {total_parts} WAV files, found {len(wav_files)}")

    missing_audio = []
    for p_idx in range(1, total_parts + 1):
        if not os.path.isfile(os.path.join(audio_dir, f"Part_{p_idx:02d}.wav")):
            missing_audio.append(p_idx)
            details.append(f"Missing required audio part: Part_{p_idx:02d}.wav")

    has_all_audio = has_15_audio and (len(missing_audio) == 0)
    if len(img_files) < min_beats:
        details.append(f"Expected at least {min_beats} images, found {len(img_files)}")

    part_counts = {}
    deficient_parts = []
    for p_idx in range(1, total_parts + 1):
        prefix = f"beat_P{p_idx:02d}_"
        cnt = len([f for f in img_files if prefix in os.path.basename(f)])
        part_counts[p_idx] = cnt
        if cnt < target_per_part:
            deficient_parts.append(p_idx)
            details.append(f"Part {p_idx:02d} has {cnt} keyframes, expected at least {target_per_part}")

    has_cover = any(("beat_P01_B01" in os.path.basename(f)) or ("beat_P01_B1." in os.path.basename(f)) for f in img_files)
    if not has_cover:
        details.append("Missing required manual Cover image: beat_P01_B01.*")

    passed_gk6 = has_all_audio and (len(img_files) >= min_beats) and (len(deficient_parts) == 0) and has_cover and (len(details) == 0)
    return {
        "passed_gk6": passed_gk6, "audio_count": len(wav_files), "missing_audio_parts": missing_audio,
        "image_count": len(img_files), "part_counts": part_counts, "deficient_parts": deficient_parts,
        "wav_files": wav_files, "img_files": img_files, "details": details
    }


def audit_gk7_master(project_root: str, master_path: Optional[str] = None) -> Dict[str, Any]:
    """Gatekeeper GK7 Master Concatenation & Duration Auditor."""
    if not master_path:
        candidates = [
            os.path.join(project_root, "03. Final Production", "master_final_90min.mp4"),
            os.path.join(project_root, "02. Media Generation", "video", "master_final_90min.mp4"),
            os.path.join(project_root, "hsnooze.render", "output", "master_final_90min.mp4"),
            os.path.join(project_root, "master_final_90min.mp4")
        ]
        master_path = next((c for c in candidates if os.path.exists(c)), candidates[0])

    if not os.path.exists(master_path):
        return {
            "passed_gk7": False, "output_path": master_path, "duration_minutes": 0.0,
            "duration_seconds": 0.0, "file_size_gb": 0.0, "details": [f"Master file not found: {master_path}"]
        }

    try:
        cmd = [
            "ffprobe", "-v", "error", "-show_entries", "format=duration:format=size",
            "-of", "default=noprint_wrappers=1:nokey=1", master_path
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        lines = res.stdout.strip().split("\n")
        dur_sec, size_bytes = float(lines[0]), int(lines[1])
        dur_min = dur_sec / 60.0
        min_dur = getattr(config, "GK7_MIN_VIDEO_DURATION_MIN", 80.0) if config else 80.0
        max_dur = getattr(config, "GK7_MAX_VIDEO_DURATION_MIN", 95.0) if config else 95.0
        passed = (min_dur <= dur_min <= max_dur) and (size_bytes > 500 * 1024 * 1024)
        return {
            "output_path": master_path, "duration_minutes": round(dur_min, 2),
            "duration_seconds": round(dur_sec, 2), "file_size_gb": round(size_bytes / (1024 ** 3), 2),
            "passed_gk7": passed
        }
    except Exception as e:
        return {
            "passed_gk7": False, "output_path": master_path, "duration_minutes": 0.0,
            "duration_seconds": 0.0, "file_size_gb": 0.0, "details": [f"ffprobe probe error: {str(e)}"]
        }
