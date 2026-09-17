"""
Prompt Parsing and GK3 Image Validation Submodule.
Adheres to Documents/Structure/01_ARCHITECTURE_CONSTRAINED_AI.md (Rule <= 150 lines/file).
"""

import re
from pathlib import Path
from typing import List, Dict, Tuple, Optional


def parse_prompts(prompt_file: Path, skip_cover: bool = True) -> Tuple[List[Dict[str, str]], Optional[str]]:
    """
    Parses prompts from combined_imageprompts.txt.
    If skip_cover is True, skips beat_P01_B01 (the first beat / Cover image),
    which is reserved for human custom design (HITL).
    """
    with open(prompt_file, "r", encoding="utf-8") as f:
        content = f.read()

    beats = []
    first_beat = True
    skipped_cover_id = None

    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        colon_idx = line.find(":")
        if colon_idx > 0:
            raw_id = line[:colon_idx].strip()
            prompt = line[colon_idx + 1:].strip()
            clean_id = re.sub(r"\.(jpg|jpeg|png|webp)$", "", raw_id, flags=re.IGNORECASE)

            is_cover = (clean_id.lower() == "beat_p01_b01") or first_beat
            first_beat = False

            if skip_cover and is_cover:
                skipped_cover_id = clean_id
                print(f"[HUMAN-IN-THE-LOOP] Skipping Cover image '{clean_id}' (reserved for manual design).")
                continue

            beats.append({"id": clean_id, "prompt": prompt})

    return beats, skipped_cover_id


def audit_image_gk3(filepath: Path, min_size_kb: float = 30.0) -> Tuple[bool, str]:
    """Audits generated keyframe image file existence and minimum size threshold."""
    if not filepath.exists():
        return False, f"File {filepath.name} does not exist"
    size_kb = filepath.stat().st_size / 1024.0
    if size_kb < min_size_kb:
        return False, f"Size too small: {size_kb:.1f} KB < {min_size_kb} KB"
    return True, f"Valid 1K beat image ({size_kb:.1f} KB)"
