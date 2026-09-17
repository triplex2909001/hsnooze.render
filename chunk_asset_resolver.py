"""
HistorySnooze Director - Chunk Asset Resolver
Resolves stardust overlay paths and Part 01 audio cue timestamps (Rule <= 150 lines).
"""

import json
import logging
import os
from typing import Dict, Optional

try:
    import config
except ImportError:
    config = None

logger = logging.getLogger("hsnooze.render.chunk_asset_resolver")

DEFAULT_P01_CUE_START_SEC = getattr(config, "DEFAULT_P01_CUE_START_SEC", 174.73) if config else 174.73
DEFAULT_P01_CUE_END_SEC = getattr(config, "DEFAULT_P01_CUE_END_SEC", 184.45) if config else 184.45


def resolve_stardust_asset_path(custom_path: Optional[str] = None) -> Optional[str]:
    """Resolves absolute path to ambient_stardust_loop.mp4 across repo, local, and Colab paths."""
    def _is_valid(p: Optional[str]) -> bool:
        return bool(p and os.path.isfile(p) and os.access(p, os.R_OK) and os.path.getsize(p) > 0)

    if custom_path is not None:
        return os.path.abspath(custom_path) if _is_valid(custom_path) else None

    base_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(base_dir)

    candidates = [
        custom_path,
        os.path.join(os.getcwd(), "assets", "ambient_stardust_loop.mp4"),
        os.path.join(base_dir, "assets", "ambient_stardust_loop.mp4"),
        os.path.join(project_root, "assets", "ambient_stardust_loop.mp4"),
        "/content/assets/ambient_stardust_loop.mp4",
        "/content/drive/MyDrive/assets/ambient_stardust_loop.mp4"
    ]

    for cand in candidates:
        if cand and _is_valid(cand):
            return os.path.abspath(cand)

    return None


def resolve_part01_cue_timestamps(
    audio_wav_path: str,
    custom_cue_path: Optional[str] = None
) -> Dict[str, float]:
    """Retrieves cue_start_sec and cue_end_sec for Part 01 with deterministic fallback."""
    cue_file = custom_cue_path
    if not cue_file or not os.path.exists(cue_file):
        audio_dir = os.path.dirname(os.path.abspath(audio_wav_path))
        candidates = [
            os.path.join(audio_dir, "Part_01_cues.json"),
            os.path.join(audio_dir, "cues.json"),
            os.path.join(os.path.dirname(audio_dir), "audio", "Part_01_cues.json"),
            os.path.join("02. Media Generation", "audio", "Part_01_cues.json")
        ]
        for c in candidates:
            if os.path.exists(c):
                cue_file = c
                break

    if cue_file and os.path.exists(cue_file):
        try:
            with open(cue_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                return {
                    "cue_start_sec": float(data.get("cue_start_sec", DEFAULT_P01_CUE_START_SEC)),
                    "cue_end_sec": float(data.get("cue_end_sec", DEFAULT_P01_CUE_END_SEC))
                }
        except Exception as e:
            logger.warning(f"Failed reading cue manifest '{cue_file}': {e}. Using default timestamps.")

    return {
        "cue_start_sec": DEFAULT_P01_CUE_START_SEC,
        "cue_end_sec": DEFAULT_P01_CUE_END_SEC
    }
