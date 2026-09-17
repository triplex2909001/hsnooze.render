"""
HistorySnooze Director - Beat Aligner Module
Calculates timestamp durations for visual beats within a part's voiceover.
High-density visual pacing: 10 beats per part, 150-160 total beats across 15 parts.
Rule <= 150 lines compliant facade.
"""

import json
import logging
import os
import subprocess
import sys
import warnings
from pathlib import Path
from typing import Any, Dict, List, Optional

_DIR = str(Path(__file__).resolve().parent)
if _DIR not in sys.path:
    sys.path.insert(0, _DIR)

from beat_align_core import (
    discover_part01_cues,
    calculate_durations,
    build_beat_records,
    save_beat_alignment_json
)

try:
    import config
except ImportError:
    config = None

logger = logging.getLogger("hsnooze.render.beat_aligner")


def get_audio_duration(audio_wav_path: str) -> float:
    """Retrieves exact duration of WAV file in seconds using ffprobe."""
    if not os.path.exists(audio_wav_path):
        raise FileNotFoundError(f"Audio file not found: {audio_wav_path}")

    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        audio_wav_path
    ]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
    return float(result.stdout.strip())


def align_part_beats(
    part_index: int,
    audio_wav_path: str,
    beat_images: List[str],
    output_json_path: Optional[str] = None,
    dim_start_sec: float = 0.0,
    dim_end_sec: float = 0.0,
    p01_b01_duration: Optional[float] = None
) -> Dict[str, Any]:
    """Calculates timestamp durations for visual beats within a part."""
    total_duration = get_audio_duration(audio_wav_path)
    num_beats = len(beat_images)

    if num_beats == 0:
        raise ValueError(f"No beat images provided for Part {part_index}.")

    min_dur = getattr(config, "BEAT_MIN_DURATION_SEC", 25.0) if config else 25.0
    max_dur = getattr(config, "BEAT_MAX_DURATION_SEC", 45.0) if config else 45.0

    is_part_1 = (part_index == 1)
    anchor_b1 = False
    b1_target_dur = 0.0

    if is_part_1:
        if p01_b01_duration is not None:
            if p01_b01_duration > 0.0:
                anchor_b1 = True
                b1_target_dur = p01_b01_duration
            else:
                anchor_b1 = False
        elif dim_end_sec > 0.0:
            anchor_b1 = True
            b1_target_dur = dim_end_sec
        elif dim_end_sec < 0.0:
            anchor_b1 = False
        else:
            c_start, c_end, rec_dur, found = discover_part01_cues(audio_wav_path)
            if found:
                dim_start_sec, dim_end_sec = c_start, c_end
                b1_target_dur = rec_dur
                anchor_b1 = True

    dur_b1, base_remaining = calculate_durations(total_duration, num_beats, anchor_b1, b1_target_dur)

    beats_data = build_beat_records(
        part_index=part_index,
        beat_images=beat_images,
        total_duration=total_duration,
        dur_b1=dur_b1,
        base_remaining=base_remaining,
        anchor_b1=anchor_b1,
        dim_start_sec=dim_start_sec,
        dim_end_sec=dim_end_sec,
        min_dur=min_dur,
        max_dur=max_dur
    )

    result = {
        "part_index": part_index,
        "audio_path": audio_wav_path,
        "total_duration": round(total_duration, 3),
        "num_beats": num_beats,
        "beats": beats_data
    }

    save_beat_alignment_json(output_json_path, result)
    return result
