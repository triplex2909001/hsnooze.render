"""
HistorySnooze Director - Chunk Intermediates Cleaner
Guaranteed cleanup of temporary beat clips and manifests (Rule <= 150 lines).
"""

import glob
import logging
import os
from typing import List, Set

logger = logging.getLogger("hsnooze.render.chunk_cleaner")


def cleanup_chunk_intermediates(
    temp_dir: str,
    part_index: int,
    beat_clips: List[str],
    expected_beat_clips: List[str],
    concat_list_path: str,
    temp_video_only: str,
    temp_chunk_path: str,
    chunk_path: str,
    success: bool
) -> None:
    """Removes intermediate clips and manifests upon render completion or failure."""
    all_clips: Set[str] = set(
        beat_clips
        + expected_beat_clips
        + glob.glob(os.path.join(temp_dir, f"beat_P{part_index:02d}_B*.*"))
    )
    for clip_path in all_clips:
        if os.path.lexists(clip_path):
            try:
                os.remove(clip_path)
            except OSError as e:
                logger.warning(f"Could not remove intermediate beat clip {clip_path}: {e}")

    for temp_file in (concat_list_path, temp_video_only):
        if os.path.lexists(temp_file):
            try:
                os.remove(temp_file)
            except OSError as e:
                logger.warning(f"Could not remove {temp_file}: {e}")

    if os.path.lexists(temp_chunk_path):
        try:
            os.remove(temp_chunk_path)
        except OSError:
            pass

    if not success and os.path.lexists(chunk_path):
        try:
            os.remove(chunk_path)
        except OSError:
            pass
