"""
HistorySnooze Director - Chunk Part Renderer
Renders individual 5-6 minute part chunks (chunk_part_01.mp4 ... chunk_part_15.mp4).
Rule <= 150 lines compliant facade.
"""

import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional

_DIR = str(Path(__file__).resolve().parent)
if _DIR not in sys.path:
    sys.path.insert(0, _DIR)

from beat_aligner import align_part_beats
from kenburns_asmr import render_kenburns_beat
from chunk_resource_manager import get_available_ram_gb, get_safe_max_workers
from chunk_asset_resolver import (
    DEFAULT_P01_CUE_START_SEC,
    DEFAULT_P01_CUE_END_SEC,
    resolve_stardust_asset_path,
    resolve_part01_cue_timestamps
)
from chunk_cleaner import cleanup_chunk_intermediates

logger = logging.getLogger("hsnooze.render.chunk_renderer")
MIN_VALID_CHUNK_BYTES = 10 * 1024 * 1024


def is_chunk_valid(chunk_path: str) -> bool:
    """Checks if a chunk MP4 exists, is > 10MB, and duration > 60s."""
    if not os.path.exists(chunk_path) or os.path.getsize(chunk_path) < MIN_VALID_CHUNK_BYTES:
        return False
    try:
        cmd = [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", chunk_path
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        return float(res.stdout.strip()) > 60.0
    except Exception:
        return False


def render_part_chunk(
    part_index: int, audio_wav_path: str, beat_images: List[str],
    output_dir: str, temp_dir: str, cues_json_path: Optional[str] = None,
    overlay_asset_path: Optional[str] = None, force_cpu: bool = False, max_workers: int = 1
) -> str:
    """Renders an individual part into a standalone MP4 chunk."""
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
    if not temp_dir:
        import tempfile
        temp_dir = tempfile.mkdtemp(prefix=f"hsnooze_chunk_P{part_index:02d}_")
    os.makedirs(temp_dir, exist_ok=True)

    max_workers = get_safe_max_workers(requested_workers=max_workers, force_cpu=force_cpu)
    chunk_path = os.path.join(output_dir, f"chunk_part_{part_index:02d}.mp4")

    if is_chunk_valid(chunk_path):
        logger.info(f"[SMART DELTA RESTART] Part {part_index:02d} already rendered. Skipping.")
        return chunk_path

    dim_start_sec, dim_end_sec, p01_b1_duration = 0.0, 0.0, None
    if part_index == 1:
        cues = resolve_part01_cue_timestamps(audio_wav_path, cues_json_path)
        dim_start_sec, dim_end_sec = cues["cue_start_sec"], cues["cue_end_sec"]
        p01_b1_duration = round(dim_end_sec + 2.0, 3)

    alignment = align_part_beats(
        part_index=part_index, audio_wav_path=audio_wav_path, beat_images=beat_images,
        dim_start_sec=dim_start_sec, dim_end_sec=dim_end_sec, p01_b01_duration=p01_b1_duration
    )
    beats = alignment["beats"]
    stardust_path = resolve_stardust_asset_path(overlay_asset_path)

    beat_clips = []
    expected_clips = [os.path.join(temp_dir, f"beat_P{part_index:02d}_B{i:02d}.mp4") for i in range(1, len(beats) + 1)]
    concat_list = os.path.join(temp_dir, f"part_{part_index:02d}_concat.txt")
    temp_vid = os.path.join(temp_dir, f"part_{part_index:02d}_video.mp4")
    temp_chunk = f"{chunk_path}.tmp.mp4"
    success = False

    try:
        def _worker(item):
            idx, beat = item
            clip = os.path.join(temp_dir, f"beat_P{part_index:02d}_B{idx:02d}.mp4")
            if not os.path.exists(clip) or os.path.getsize(clip) < 1024 * 1024:
                render_kenburns_beat(
                    image_path=beat["image_path"], duration=beat["duration"], output_clip_path=clip,
                    zoom_in=(idx % 2 != 0), is_transition_beat=beat.get("is_transition_beat", False),
                    dim_start_sec=beat.get("dim_start_sec", 0.0), dim_end_sec=beat.get("dim_end_sec", 0.0),
                    sleep_mode=beat.get("sleep_mode", False), overlay_asset_path=stardust_path, force_cpu=force_cpu
                )
            return idx, clip

        if max_workers > 1 and len(beats) > 1:
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                rendered = list(executor.map(_worker, enumerate(beats, start=1)))
        else:
            rendered = [_worker(b) for b in enumerate(beats, start=1)]

        rendered.sort(key=lambda x: x[0])
        beat_clips = [path for _, path in rendered]

        with open(concat_list, "w", encoding="utf-8") as f_c:
            for path in beat_clips:
                f_c.write(f"file '{os.path.abspath(path)}'\n")

        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", concat_list, "-c", "copy", temp_vid], check=True)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", temp_vid, "-i", audio_wav_path, "-c:v", "copy", "-c:a", "aac", "-b:a", "256k", "-shortest", chunk_path], check=True)
        success = True
    finally:
        cleanup_chunk_intermediates(temp_dir, part_index, beat_clips, expected_clips, concat_list, temp_vid, temp_chunk, chunk_path, success)

    return chunk_path
