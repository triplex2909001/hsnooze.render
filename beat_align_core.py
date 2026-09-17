"""
Core logic and data structures for beat alignment calculations.
Supports Part 01 Beat 1 anchoring and high-density beat pacing (Rule <= 150 lines).
"""

import json
import os
import warnings
from typing import Any, Dict, List, Optional, Tuple


def discover_part01_cues(audio_wav_path: str) -> Tuple[float, float, float, bool]:
    """Attempts auto-discovery of Part_01_cues.json adjacent to audio file."""
    if not audio_wav_path:
        return 0.0, 0.0, 0.0, False
    raw_dir = os.path.dirname(audio_wav_path)
    if not raw_dir:
        return 0.0, 0.0, 0.0, False
    audio_dir = os.path.abspath(raw_dir)
    candidates = [
        os.path.join(audio_dir, "Part_01_cues.json"),
        os.path.join(audio_dir, "audio", "Part_01_cues.json"),
        os.path.join(os.path.dirname(audio_dir), "audio", "Part_01_cues.json")
    ]
    for cand in candidates:
        if cand and os.path.exists(cand):
            try:
                with open(cand, "r", encoding="utf-8") as f_cue:
                    c_data = json.load(f_cue)
                c_start = float(c_data.get("cue_start_sec", 174.73))
                c_end = float(c_data.get("cue_end_sec", 184.45))
                rec_dur = float(c_data.get("recommended_b01_duration_sec", c_end + 2.0))
                return c_start, c_end, rec_dur, True
            except Exception:
                pass
    return 0.0, 0.0, 0.0, False


def calculate_durations(
    total_duration: float,
    num_beats: int,
    anchor_b1: bool,
    b1_target_dur: float
) -> Tuple[float, float]:
    """Calculates dur_b1 and base_remaining for beat distribution."""
    if anchor_b1 and num_beats > 1:
        if b1_target_dur >= total_duration:
            raise ValueError(
                f"Anchored Beat 1 duration ({b1_target_dur}s) must be less than total duration ({total_duration}s)."
            )
        dur_b1 = round(b1_target_dur, 3)
        rem_dur = total_duration - dur_b1
        base_rem = rem_dur / (num_beats - 1)
        return dur_b1, base_rem
    dur_b1 = round(total_duration / num_beats, 3)
    return dur_b1, total_duration / num_beats


def build_beat_records(
    part_index: int,
    beat_images: List[str],
    total_duration: float,
    dur_b1: float,
    base_remaining: float,
    anchor_b1: bool,
    dim_start_sec: float,
    dim_end_sec: float,
    min_dur: float,
    max_dur: float
) -> List[Dict[str, Any]]:
    """Builds the list of beat dictionaries for the aligned part."""
    num_beats = len(beat_images)
    is_part_1 = (part_index == 1)
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

        beats_data.append({
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
        })
        current_time += dur

    return beats_data


def save_beat_alignment_json(output_json_path: Optional[str], result: Dict[str, Any]) -> None:
    """Writes beat alignment results to JSON file if path specified."""
    if output_json_path:
        dirname = os.path.dirname(output_json_path)
        if dirname:
            os.makedirs(dirname, exist_ok=True)
        with open(output_json_path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
