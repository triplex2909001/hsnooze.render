"""
HistorySnooze Director - Ken Burns FFmpeg Command Builder
Constructs CLI argument vectors for video encoding (Rule <= 150 lines).
"""

import os
import sys
from pathlib import Path
from typing import List, Optional

_DIR = str(Path(__file__).resolve().parent)
if _DIR not in sys.path:
    sys.path.insert(0, _DIR)

from kenburns_filters import (
    DEFAULT_CONTRAST,
    DEFAULT_BRIGHTNESS,
    DEFAULT_GAMMA,
    DEFAULT_SATURATION,
    DEFAULT_VIGNETTE,
    DEFAULT_STARDUST_OPACITY,
    build_filter_graph
)

try:
    import config
except ImportError:
    config = None


def build_render_command(
    image_path: str,
    duration: float,
    output_clip_path: str,
    zoom_in: bool = True,
    fps: int = 30,
    width: int = 3840,
    height: int = 2160,
    force_cpu: bool = False,
    is_transition_beat: bool = False,
    dim_start_sec: float = 0.0,
    dim_end_sec: float = 0.0,
    sleep_mode: bool = False,
    overlay_asset_path: Optional[str] = None,
    use_nvenc: bool = False
) -> List[str]:
    """Builds the complete FFmpeg argument list for rendering a beat clip."""
    if duration <= 0.0:
        raise ValueError(f"duration must be strictly positive, got {duration}")

    has_overlay = bool(
        overlay_asset_path
        and os.path.isfile(overlay_asset_path)
        and os.access(overlay_asset_path, os.R_OK)
        and os.path.getsize(overlay_asset_path) > 0
    )

    total_frames = max(1, int(duration * fps))

    filt, out_label = build_filter_graph(
        zoom_in=zoom_in,
        total_frames=total_frames,
        width=width,
        height=height,
        fps=fps,
        is_transition_beat=is_transition_beat,
        dim_start_sec=dim_start_sec,
        dim_end_sec=dim_end_sec,
        sleep_mode=sleep_mode,
        has_overlay=has_overlay
    )

    if (not force_cpu) and use_nvenc:
        codec_args = ["-c:v", "h264_nvenc", "-preset", "p4", "-cq", "18"]
    else:
        cpu_preset = getattr(config, "CPU_PRESET", "veryfast") if config else "veryfast"
        codec_args = ["-c:v", "libx264", "-preset", cpu_preset, "-crf", "18"]

    cmd = ["ffmpeg", "-y", "-loglevel", "error"]
    cmd += ["-framerate", str(fps), "-loop", "1", "-i", image_path]

    if has_overlay and out_label is not None:
        cmd += ["-stream_loop", "-1", "-i", overlay_asset_path]

    cmd += ["-t", f"{duration:.3f}"]

    if out_label is not None:
        cmd += ["-filter_complex", filt, "-map", out_label]
    else:
        cmd += ["-vf", filt]

    cmd += codec_args
    cmd += ["-pix_fmt", "yuv420p", output_clip_path]
    return cmd
