"""
HistorySnooze Director - Ken Burns ASMR Engine
Renders slow, hypnotic Ken Burns camera movements for deep sleep documentaries.
Rule <= 150 lines compliant facade.
"""

import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import List, Optional, Tuple

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
    build_zoompan_expr,
    build_filter_graph
)
from kenburns_command_builder import build_render_command as _build_cmd

logger = logging.getLogger("hsnooze.render.kenburns_asmr")
_HAS_NVENC: Optional[bool] = None


def check_nvenc_available() -> bool:
    """Checks if ffmpeg has h264_nvenc encoder enabled and working."""
    global _HAS_NVENC
    if _HAS_NVENC is not None:
        return _HAS_NVENC
    try:
        res = subprocess.run(
            ["ffmpeg", "-hide_banner", "-encoders"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        if "h264_nvenc" in res.stdout:
            test_cmd = [
                "ffmpeg", "-y", "-loglevel", "error",
                "-f", "lavfi", "-i", "color=c=black:s=64x64:d=0.1",
                "-c:v", "h264_nvenc", "-f", "null", "-"
            ]
            test_res = subprocess.run(test_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            _HAS_NVENC = (test_res.returncode == 0)
        else:
            _HAS_NVENC = False
    except Exception:
        _HAS_NVENC = False
    return _HAS_NVENC


def build_render_command(
    image_path: str, duration: float, output_clip_path: str,
    zoom_in: bool = True, fps: int = 30, width: int = 3840, height: int = 2160,
    force_cpu: bool = False, is_transition_beat: bool = False,
    dim_start_sec: float = 0.0, dim_end_sec: float = 0.0,
    sleep_mode: bool = False, overlay_asset_path: Optional[str] = None
) -> List[str]:
    """Builds complete FFmpeg argument list with hardware NVENC auto-detection."""
    use_nvenc = (not force_cpu) and check_nvenc_available()
    return _build_cmd(
        image_path=image_path, duration=duration, output_clip_path=output_clip_path,
        zoom_in=zoom_in, fps=fps, width=width, height=height, force_cpu=force_cpu,
        is_transition_beat=is_transition_beat, dim_start_sec=dim_start_sec,
        dim_end_sec=dim_end_sec, sleep_mode=sleep_mode,
        overlay_asset_path=overlay_asset_path, use_nvenc=use_nvenc
    )


def render_kenburns_beat(
    image_path: str, duration: float, output_clip_path: str,
    zoom_in: bool = True, width: int = 3840, height: int = 2160, fps: int = 30,
    is_transition_beat: bool = False, dim_start_sec: float = 0.0, dim_end_sec: float = 0.0,
    sleep_mode: bool = False, overlay_asset_path: Optional[str] = None, force_cpu: bool = False
) -> str:
    """Renders a single still image into a Ken Burns video clip with sleep grading."""
    if duration <= 0.0:
        raise ValueError(f"duration must be strictly positive, got {duration}")
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"Image not found: {image_path}")

    out_dir = os.path.dirname(output_clip_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    use_nvenc = (not force_cpu) and check_nvenc_available()
    cmd = build_render_command(
        image_path=image_path, duration=duration, output_clip_path=output_clip_path,
        zoom_in=zoom_in, fps=fps, width=width, height=height, force_cpu=force_cpu,
        is_transition_beat=is_transition_beat, dim_start_sec=dim_start_sec,
        dim_end_sec=dim_end_sec, sleep_mode=sleep_mode,
        overlay_asset_path=overlay_asset_path
    )

    try:
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as e:
            if use_nvenc:
                logger.warning("NVENC failed. Retrying with CPU libx264 fallback...")
                if os.path.lexists(output_clip_path):
                    try:
                        os.remove(output_clip_path)
                    except OSError:
                        pass
                cpu_cmd = build_render_command(
                    image_path=image_path, duration=duration, output_clip_path=output_clip_path,
                    zoom_in=zoom_in, fps=fps, width=width, height=height, force_cpu=True,
                    is_transition_beat=is_transition_beat, dim_start_sec=dim_start_sec,
                    dim_end_sec=dim_end_sec, sleep_mode=sleep_mode,
                    overlay_asset_path=overlay_asset_path
                )
                subprocess.run(cpu_cmd, check=True, capture_output=True, text=True)
            else:
                raise
    except BaseException:
        if os.path.lexists(output_clip_path):
            try:
                os.remove(output_clip_path)
            except OSError:
                pass
        raise

    return output_clip_path
