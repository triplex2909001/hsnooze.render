"""
HistorySnooze Director - Beat Aligner Module
Calculates timestamp durations for each visual beat within a part's voiceover.
Each visual beat extends between 25 and 45 seconds (~30-45s) to match the
high-density visual pacing (10 beats per part, 150-160 total beats across 15 parts).
Supports Part 01 Beat 1 anchoring for "Dim the Lights" dynamic transitions.
"""

import json
import logging
import os
import subprocess
import warnings
from typing import List, Dict, Any, Optional

try:
    import config
except ImportError:
    config = None

logger = logging.getLogger("hsnooze.render.beat_aligner")


def get_audio_duration(audio_wav_path: str) -> float:
    """
    Retrieves the exact duration of a WAV file in seconds using ffprobe.
    """
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
    """
    Calculates timestamp durations for visual beats within a part.

    Standard parts (P02-P15) and unanchored P01 distribute total duration equally
    across all beats (~30-45s per beat, 10 beats per part).

    Part 01 Beat 1 Anchoring:
    When part_index == 1 and p01_b01_duration is specified (or dim_end_sec > 0),
    Beat 1 is anchored to that specific duration to cover the intro up to the
    "dim the lights" cue transition. If not provided, it attempts to discover
    Part_01_cues.json. The remaining audio duration is then distributed across
    Beats 2..N.

    Sleep Mode Flag:
    - P01_B01: is_transition_beat = True, sleep_mode = False
    - P01_B02..B10: is_transition_beat = False, sleep_mode = True
    - P02..P15 (all beats): is_transition_beat = False, sleep_mode = True
    """
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
        if p01_b01_duration is not None and p01_b01_duration > 0.0:
            anchor_b1 = True
            b1_target_dur = p01_b01_duration
        elif dim_end_sec > 0.0:
            anchor_b1 = True
            b1_target_dur = dim_end_sec
        else:
            # Auto-discover Part_01_cues.json if present
            audio_dir = os.path.dirname(os.path.abspath(audio_wav_path)) if audio_wav_path else ""
            cues_candidates = [
                os.path.join(audio_dir, "Part_01_cues.json"),
                os.path.join(audio_dir, "audio", "Part_01_cues.json"),
                os.path.join("02. Media Generation", "audio", "Part_01_cues.json")
            ]
            for c_cand in cues_candidates:
                if c_cand and os.path.exists(c_cand):
                    try:
                        with open(c_cand, "r", encoding="utf-8") as f_cue:
                            c_data = json.load(f_cue)
                        dim_start_sec = float(c_data.get("cue_start_sec", 174.73))
                        dim_end_sec = float(c_data.get("cue_end_sec", 184.45))
                        b1_target_dur = float(c_data.get("recommended_b01_duration_sec", dim_end_sec + 2.0))
                        anchor_b1 = True
                        break
                    except Exception:
                        pass

    if anchor_b1 and num_beats > 1:
        if b1_target_dur >= total_duration:
            raise ValueError(
                f"Anchored Beat 1 duration ({b1_target_dur}s) must be less than total duration ({total_duration}s)."
            )
        dur_b1 = round(b1_target_dur, 3)
        remaining_duration = total_duration - dur_b1
        remaining_beats = num_beats - 1
        base_remaining = remaining_duration / remaining_beats
    else:
        dur_b1 = round(total_duration / num_beats, 3)
        base_remaining = total_duration / num_beats

    beats_data = []
    current_time = 0.0

    for idx, img_path in enumerate(beat_images, start=1):
        is_transition = (is_part_1 and idx == 1)
        sleep_mode = not is_transition
        beat_dim_start = dim_start_sec if is_transition else 0.0
        beat_dim_end = dim_end_sec if is_transition else 0.0

        if idx == 1 and anchor_b1 and num_beats > 1:
            dur = dur_b1
        elif idx == num_beats:
            dur = round(total_duration - current_time, 3)
        elif anchor_b1 and num_beats > 1:
            dur = round(base_remaining, 3)
        else:
            dur = round(total_duration / num_beats, 3)

        dur = round(dur, 3)
        start_t = round(current_time, 3)
        end_t = round(current_time + dur, 3)

        if dur < min_dur or dur > max_dur:
            warnings.warn(
                f"Beat P{part_index:02d}_B{idx:02d} duration {dur:.2f}s is outside target range "
                f"[{min_dur:.1f}s, {max_dur:.1f}s]. Total audio: {total_duration:.1f}s, beats: {num_beats}."
            )

        beat_info = {
            "part_index": part_index,
            "beat_index": idx,
            "beat_id": f"P{part_index:02d}_B{idx:02d}",
            "image_path": img_path,
            "start_time": start_t,
            "end_time": end_t,
            "duration": dur,
            "is_transition_beat": is_transition,
            "dim_start_sec": round(beat_dim_start, 3),
            "dim_end_sec": round(beat_dim_end, 3),
            "sleep_mode": sleep_mode
        }
        beats_data.append(beat_info)
        current_time += dur

    result = {
        "part_index": part_index,
        "audio_path": audio_wav_path,
        "total_duration": round(total_duration, 3),
        "num_beats": num_beats,
        "beats": beats_data
    }

    if output_json_path:
        dirname = os.path.dirname(output_json_path)
        if dirname:
            os.makedirs(dirname, exist_ok=True)
        with open(output_json_path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)

    return result
