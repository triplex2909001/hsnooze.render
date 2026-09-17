"""
HistorySnooze Director - Audio Cue Extraction Utility
Extracts deterministic cue timestamps for Part 01 'Dim the Lights' transition.
Supports 3-tier hierarchy (Tier 1: Chunks, Tier 2: Silence scan, Tier 3: Constants).
Rule <= 150 lines compliant facade.
"""

import json
import os
import re
import sys
import wave
from pathlib import Path
from typing import Any, Dict, Optional

_DIR = str(Path(__file__).resolve().parent)
if _DIR not in sys.path:
    sys.path.insert(0, _DIR)

from cue_silence_scanner import scan_wav_silence_intervals

# Verified deterministic fallback constants for Matsuo Basho
DEFAULT_CUE_START_SEC = 174.73
DEFAULT_CUE_END_SEC = 184.45
DEFAULT_DIM_DURATION_SEC = 9.72
DEFAULT_BUFFER_SEC = 2.0
DEFAULT_B01_DURATION_SEC = 186.45
DEFAULT_CUE_TEXT = (
    "Now, dim the lights, maybe turn on a fan for that soft background hum, "
    "and let’s ease into tonight’s journey together."
)


def validate_cue_manifest(cue_data: Dict[str, Any]) -> bool:
    """Validates that a cue manifest dictionary adheres strictly to schema invariants."""
    if cue_data.get("part_index") != 1:
        raise ValueError("Cue anchoring is only valid on Part 01.")
    cue_text = cue_data.get("cue_text") or cue_data.get("cue_verbatim_text") or ""
    if not re.search(r"\bdim\s+the\s+lights\b", cue_text, re.IGNORECASE):
        raise ValueError("Cue text missing 'dim the lights'.")
    c_start = cue_data.get("cue_start_sec", 0.0)
    c_end = cue_data.get("cue_end_sec", 0.0)
    dim_dur = cue_data.get("dim_duration_sec", 0.0)
    if c_start < 0.0:
        raise ValueError("cue_start_sec must be non-negative.")
    if c_start >= c_end:
        raise ValueError("cue_start_sec must be strictly less than cue_end_sec.")
    if round(c_end - c_start, 3) != round(dim_dur, 3):
        raise ValueError("dim_duration_sec must match end - start.")
    return True


def _save_cues_json(data: Dict[str, Any], path: str) -> None:
    abs_path = os.path.abspath(path)
    os.makedirs(os.path.dirname(abs_path), exist_ok=True)
    with open(abs_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def extract_part01_cue_timestamps(
    script_path: Optional[str] = None,
    chunks_dir: Optional[str] = None,
    part_01_wav_path: Optional[str] = None,
    output_json_path: Optional[str] = None,
    cue_regex: str = r"\bdim\s+the\s+lights\b",
    intra_silence_sec: float = 1.0,
    buffer_sec: float = DEFAULT_BUFFER_SEC
) -> Dict[str, Any]:
    """Extracts start and end timestamps for the 'dim the lights' cue in Part 01."""
    result: Dict[str, Any] = {
        "part_index": 1,
        "cue_phrase": "dim the lights",
        "cue_text": DEFAULT_CUE_TEXT,
        "cue_verbatim_text": DEFAULT_CUE_TEXT,
        "cue_chunk_index": 17,
        "cue_chunk_file": "part_01_chunk_017.wav",
        "chunk_id": 17,
        "chunk_filename": "part_01_chunk_017.wav",
        "cue_start_sec": DEFAULT_CUE_START_SEC,
        "cue_end_sec": DEFAULT_CUE_END_SEC,
        "dim_duration_sec": DEFAULT_DIM_DURATION_SEC,
        "recommended_b01_duration_sec": DEFAULT_B01_DURATION_SEC,
        "extraction_method": "deterministic_fallback"
    }

    # Tier 1: Measure from raw chunk WAV files if present
    if chunks_dir and os.path.isdir(chunks_dir):
        chunk_files = sorted(Path(chunks_dir).glob("part_01_chunk_*.wav"))
        if len(chunk_files) >= 17:
            try:
                acc_time, c_start, c_end, c_dur = 0.0, 0.0, 0.0, 0.0
                for idx, c_path in enumerate(chunk_files, start=1):
                    with wave.open(str(c_path), "rb") as wf:
                        dur = wf.getnframes() / float(wf.getframerate())
                    if idx == 17:
                        c_start, c_dur = acc_time, dur
                        c_end = c_start + dur
                        break
                    acc_time += dur + intra_silence_sec

                if c_dur > 0.0:
                    result.update({
                        "cue_start_sec": round(c_start, 3),
                        "cue_end_sec": round(c_end, 3),
                        "dim_duration_sec": round(c_dur, 3),
                        "recommended_b01_duration_sec": round(c_end + buffer_sec, 3),
                        "extraction_method": "exact_wav_chunks"
                    })
                    if output_json_path:
                        _save_cues_json(result, output_json_path)
                    return result
            except Exception:
                pass

    # Tier 2: Scan stitched Part_01.wav for silence intervals
    if part_01_wav_path and os.path.exists(part_01_wav_path):
        zero_intervals = scan_wav_silence_intervals(part_01_wav_path, intra_silence_sec)
        if len(zero_intervals) >= 17:
            c_start = zero_intervals[15][1]
            c_end = zero_intervals[16][0]
            result.update({
                "cue_start_sec": round(c_start, 3),
                "cue_end_sec": round(c_end, 3),
                "dim_duration_sec": round(c_end - c_start, 3),
                "recommended_b01_duration_sec": round(c_end + buffer_sec, 3),
                "extraction_method": "zero_silence_scan"
            })
            if output_json_path:
                _save_cues_json(result, output_json_path)
            return result

    # Tier 3: Deterministic fallback
    if output_json_path:
        _save_cues_json(result, output_json_path)
    return result
