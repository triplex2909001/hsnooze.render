"""
HistorySnooze Director - Gatekeepers GK3 & GK4 Auditor
Validates 150-160 beat prompt syntax and acoustic WAV integrity (Rule <= 150 lines).
"""

import glob
import os
import re
import sys
from typing import Any, Dict, List, Optional

try:
    import config
except ImportError:
    config = None

try:
    from voice_chunk_engine import ChunkVoiceoverPipeline, audit_wav_acoustic
except ImportError:
    ChunkVoiceoverPipeline = None
    audit_wav_acoustic = None

try:
    from prompt_engine import validate_prompt
except ImportError:
    _s_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "hsnooze.scripting"))
    if os.path.isdir(_s_dir) and _s_dir not in sys.path:
        sys.path.insert(0, _s_dir)
    try:
        from prompt_engine import validate_prompt
    except ImportError:
        validate_prompt = None


def audit_gk3_prompts(project_root: str, prompts_file_path: Optional[str] = None) -> Dict[str, Any]:
    """Audits combined_imageprompts.txt for 150-160 beat count and syntax adherence."""
    if prompts_file_path is None:
        candidates = [
            os.path.join(project_root, "01. Pre-Production", "combined_imageprompts.txt"),
            os.path.join(project_root, "01. Preproduction", "combined_imageprompts.txt"),
            os.path.join(project_root, "combined_imageprompts.txt"),
            os.path.join(project_root, "02. Media Generation", "combined_imageprompts.txt"),
            os.path.join(project_root, "02. Media Generation", "combined", "combined_imageprompts.txt"),
        ]
        for c in candidates:
            if os.path.exists(c):
                prompts_file_path = c
                break

    total_parts = getattr(config, "TOTAL_PARTS", 15) if config else 15
    min_beats = getattr(config, "EXPECTED_MIN_BEATS", 150) if config else 150
    max_beats = getattr(config, "EXPECTED_MAX_BEATS", 160) if config else 160
    target_per_part = getattr(config, "TARGET_BEATS_PER_PART", 10) if config else 10

    if not prompts_file_path or not os.path.exists(prompts_file_path):
        return {
            "passed_gk3": False, "total_count": 0, "part_counts": {p: 0 for p in range(1, total_parts + 1)},
            "deficient_parts": list(range(1, total_parts + 1)), "prompts_file_path": prompts_file_path,
            "details": [f"combined_imageprompts.txt not found in {project_root}"], "warnings": []
        }

    with open(prompts_file_path, "r", encoding="utf-8") as f:
        content = f.read()

    part_beats = {p: [] for p in range(1, total_parts + 1)}
    total_beats, details, warnings = 0, [], []
    _warned_prompt_engine = False
    beat_pattern = re.compile(r"^beat_P(\d{2})_B(\d{2})(?:\.jpg|\.png|\.jpeg)?\s*:\s*(.*)$", re.IGNORECASE)

    mod_orch = sys.modules.get("pipeline_orchestrator")
    val_fn = getattr(mod_orch, "validate_prompt", validate_prompt) if mod_orch else validate_prompt

    for line_num, raw_line in enumerate(content.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        m = beat_pattern.match(line)
        if m:
            part_idx, beat_idx, prompt_text = int(m.group(1)), int(m.group(2)), m.group(3).strip()
            total_beats += 1
            if part_idx in part_beats:
                part_beats[part_idx].append({"beat_idx": beat_idx, "prompt": prompt_text, "line_num": line_num})
            else:
                details.append(f"Line {line_num}: Part {part_idx:02d} outside expected range 1..{total_parts}")

            if val_fn is not None:
                val_res = val_fn(prompt_text)
                if not val_res.get("is_valid", False):
                    issues = val_res.get("issues", [])
                    if issues:
                        for issue in issues:
                            details.append(f"Line {line_num} (Part {part_idx:02d} Beat {beat_idx:02d}): {issue}")
                    else:
                        details.append(f"Line {line_num} (Part {part_idx:02d} Beat {beat_idx:02d}): Prompt validation failed")
            else:
                if not _warned_prompt_engine:
                    msg = "prompt_engine is unavailable; skipping semantic prompt syntax audit."
                    warnings.append(msg)
                    _warned_prompt_engine = True
        elif ":" in line and line.lower().startswith("beat_"):
            details.append(f"Line {line_num}: Malformed beat line format: '{line[:50]}'")

    has_valid_total = (min_beats <= total_beats <= max_beats)
    if not has_valid_total:
        details.append(f"Total prompt count {total_beats} outside required range [{min_beats}, {max_beats}]")

    part_counts = {p: len(b) for p, b in part_beats.items()}
    deficient_parts = [p for p in range(1, total_parts + 1) if part_counts[p] < target_per_part]
    for p in deficient_parts:
        details.append(f"Part {p:02d} has {part_counts[p]} prompts, expected at least {target_per_part}")

    passed_gk3 = has_valid_total and (len(deficient_parts) == 0) and (len(details) == 0)
    return {
        "passed_gk3": passed_gk3, "total_count": total_beats, "part_counts": part_counts,
        "deficient_parts": deficient_parts, "prompts_file_path": prompts_file_path,
        "details": details, "warnings": warnings
    }


def audit_gk4_audio(project_root: str) -> Dict[str, Any]:
    """Audits 15 WAV files for acoustic integrity and minimum size."""
    audio_dir = os.path.join(project_root, "02. Media Generation", "audio")
    wav_files = sorted(glob.glob(os.path.join(audio_dir, "Part_*.wav")))
    passed_all, details = True, []
    if len(wav_files) != 15:
        passed_all = False
        details.append(f"Expected 15 WAV files, found {len(wav_files)}")

    min_kb = getattr(config, "GK4_MIN_WAV_SIZE_KB", 10.0) if config else 10.0
    rms_thresh = getattr(config, "GK4_RMS_THRESHOLD", 0.005) if config else 0.005

    for wav_path in wav_files:
        if audit_wav_acoustic:
            valid, msg = audit_wav_acoustic(wav_path, min_size_kb=min_kb, min_rms=rms_thresh)
            if not valid:
                passed_all = False
                details.append(f"{os.path.basename(wav_path)} failed: {msg}")
        else:
            size_kb = os.path.getsize(wav_path) / 1024.0
            if size_kb < min_kb:
                passed_all = False
                details.append(f"{os.path.basename(wav_path)} size too small: {size_kb:.1f} KB")

    return {"passed_gk4": passed_all, "count": len(wav_files), "details": details}
