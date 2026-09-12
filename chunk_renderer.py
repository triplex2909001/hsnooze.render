"""
HistorySnooze Director - Chunk Part Renderer
Renders individual 5-6 minute part chunks (chunk_part_01.mp4 ... chunk_part_15.mp4).
Includes Smart Delta Restart logic, "Dim the Lights" Part 01 audio cue detection,
parameter forwarding into render_kenburns_beat, and multi-environment stardust resolution.
"""

import json
import logging
import os
import subprocess
from typing import List, Dict, Optional
from kenburns_asmr import render_kenburns_beat
from beat_aligner import align_part_beats

try:
    import config
except ImportError:
    config = None

logger = logging.getLogger("hsnooze.render.chunk_renderer")

MIN_VALID_CHUNK_BYTES = 10 * 1024 * 1024  # 10 MB minimum for 4K video

DEFAULT_P01_CUE_START_SEC = getattr(config, "DEFAULT_P01_CUE_START_SEC", 174.73) if config else 174.73
DEFAULT_P01_CUE_END_SEC = getattr(config, "DEFAULT_P01_CUE_END_SEC", 184.45) if config else 184.45


def is_chunk_valid(chunk_path: str) -> bool:
    """
    Checks if a chunk MP4 exists, is greater than 10MB, and has valid playable streams.
    """
    if not os.path.exists(chunk_path):
        return False
    if os.path.getsize(chunk_path) < MIN_VALID_CHUNK_BYTES:
        return False

    try:
        cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            chunk_path
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        dur = float(res.stdout.strip())
        return dur > 60.0  # Must be at least 1 minute long
    except Exception:
        return False


def resolve_stardust_asset_path(custom_path: Optional[str] = None) -> Optional[str]:
    """
    Resolves the absolute path to ambient_stardust_loop.mp4 across repository, local, and Colab paths.
    Returns the path if the asset exists, otherwise returns None (triggering graceful fallback).
    """
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
    """
    Retrieves cue_start_sec and cue_end_sec for Part 01.
    Checks custom_cue_path, then adjacent Part_01_cues.json, with deterministic fallback.
    """
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

    # Deterministic fallback timestamps
    return {
        "cue_start_sec": DEFAULT_P01_CUE_START_SEC,
        "cue_end_sec": DEFAULT_P01_CUE_END_SEC
    }


def render_part_chunk(
    part_index: int,
    audio_wav_path: str,
    beat_images: List[str],
    output_dir: str,
    temp_dir: str,
    cues_json_path: Optional[str] = None,
    overlay_asset_path: Optional[str] = None,
    force_cpu: bool = False,
    max_workers: int = 1
) -> str:
    """
    Renders an individual part into a standalone MP4 chunk:
    1. Check Smart Delta Restart: skip if already valid.
    2. Extract audio cues for Part 01 ("dim the lights").
    3. Align visual beats with voiceover audio.
    4. Render Ken Burns ASMR video for each beat with sleep shading & particle overlay.
    5. Stream-copy concatenate beat clips and mux audio track into chunk_part_XX.mp4.
    """
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
    if temp_dir:
        os.makedirs(temp_dir, exist_ok=True)

    chunk_filename = f"chunk_part_{part_index:02d}.mp4"
    chunk_path = os.path.join(output_dir, chunk_filename)

    # 1. Smart Delta Restart Check
    if is_chunk_valid(chunk_path):
        logger.info(f"[SMART DELTA RESTART] Part {part_index:02d} is already rendered and valid. Skipping.")
        return chunk_path

    logger.info(f"[RENDER] Beginning render for Part {part_index:02d} ({len(beat_images)} beats)...")

    # 2. Extract Cues for Part 01
    dim_start_sec = 0.0
    dim_end_sec = 0.0
    p01_b1_duration = None

    if part_index == 1:
        cues = resolve_part01_cue_timestamps(audio_wav_path, cues_json_path)
        dim_start_sec = cues["cue_start_sec"]
        dim_end_sec = cues["cue_end_sec"]
        p01_b1_duration = round(dim_end_sec + 2.0, 3)
        logger.info(
            f"[CUE] Part 01 'dim the lights' anchored: {dim_start_sec:.2f}s -> {dim_end_sec:.2f}s "
            f"(Beat 1 dur: {p01_b1_duration:.2f}s)"
        )

    # 3. Align Beats
    alignment = align_part_beats(
        part_index=part_index,
        audio_wav_path=audio_wav_path,
        beat_images=beat_images,
        dim_start_sec=dim_start_sec,
        dim_end_sec=dim_end_sec,
        p01_b01_duration=p01_b1_duration
    )
    beats = alignment["beats"]

    # 4. Resolve Stardust Overlay Asset
    stardust_path = resolve_stardust_asset_path(overlay_asset_path)
    if stardust_path:
        logger.info(f"[RENDER] Ambient stardust overlay: {stardust_path}")
    else:
        logger.info("[RENDER] Stardust overlay not found. Color grading will run without overlay.")

    def _render_beat_worker(beat_tuple):
        idx, beat = beat_tuple
        beat_clip_path = os.path.join(temp_dir, f"beat_P{part_index:02d}_B{idx:02d}.mp4")
        zoom_in = (idx % 2 != 0)  # Alternate zoom in and zoom out
        if not os.path.exists(beat_clip_path) or os.path.getsize(beat_clip_path) < 1024 * 1024:
            render_kenburns_beat(
                image_path=beat["image_path"],
                duration=beat["duration"],
                output_clip_path=beat_clip_path,
                zoom_in=zoom_in,
                is_transition_beat=beat.get("is_transition_beat", False),
                dim_start_sec=beat.get("dim_start_sec", 0.0),
                dim_end_sec=beat.get("dim_end_sec", 0.0),
                sleep_mode=beat.get("sleep_mode", False),
                overlay_asset_path=None if beat.get("is_transition_beat", False) else stardust_path,
                force_cpu=force_cpu
            )
        return idx, beat_clip_path

    if max_workers > 1 and len(beats) > 1:
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            rendered = list(executor.map(_render_beat_worker, enumerate(beats, start=1)))
    else:
        rendered = [_render_beat_worker(b) for b in enumerate(beats, start=1)]

    rendered.sort(key=lambda x: x[0])
    beat_clips = [path for _, path in rendered]

    concat_list_path = os.path.join(temp_dir, f"part_{part_index:02d}_concat.txt")
    with open(concat_list_path, "w", encoding="utf-8") as f_concat:
        for path in beat_clips:
            f_concat.write(f"file '{os.path.abspath(path)}'\n")

    # 5. Assemble Visual Beats + Audio into Part Chunk
    temp_video_only = os.path.join(temp_dir, f"part_{part_index:02d}_video.mp4")
    cmd_video = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "concat", "-safe", "0",
        "-i", concat_list_path,
        "-c", "copy",
        temp_video_only
    ]
    subprocess.run(cmd_video, check=True)

    # Mux video with audio WAV
    cmd_mux = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", temp_video_only,
        "-i", audio_wav_path,
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "256k",
        "-shortest",
        chunk_path
    ]
    subprocess.run(cmd_mux, check=True)

    # Cleanup temp intermediate video
    if os.path.exists(temp_video_only):
        os.remove(temp_video_only)

    logger.info(f"✅ Finished Part {part_index:02d} Chunk: {chunk_path}")
    return chunk_path
