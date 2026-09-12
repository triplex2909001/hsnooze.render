"""
HistorySnooze Director - Ken Burns ASMR Engine
Renders slow, hypnotic Ken Burns camera movements for deep sleep documentaries.
Features anti-jitter 8K prescaling, ultra-subtle 4% zoom over 25-45 seconds,
dynamic cosine lighting dimming ("Dim the Lights" Part 01 Beat 1), static dark sleep
mood grading with ambient stardust overlay, and automatic GPU NVENC / CPU libx264 selection.
"""

import logging
import os
import subprocess
from typing import Optional, Tuple, List

try:
    import config
except ImportError:
    config = None

logger = logging.getLogger("hsnooze.render.kenburns_asmr")

_HAS_NVENC: Optional[bool] = None

# Sleep Shading Parameters (Requirement R3)
DEFAULT_CONTRAST = getattr(config, "SLEEP_CONTRAST", 0.90) if config else 0.90
DEFAULT_BRIGHTNESS = getattr(config, "SLEEP_BRIGHTNESS", -0.05) if config else -0.05
DEFAULT_GAMMA = getattr(config, "SLEEP_GAMMA", 0.85) if config else 0.85
DEFAULT_SATURATION = getattr(config, "SLEEP_SATURATION", 0.88) if config else 0.88
DEFAULT_VIGNETTE = getattr(config, "SLEEP_VIGNETTE", "PI/4:aspect=16/9") if config else "PI/4:aspect=16/9"
DEFAULT_STARDUST_OPACITY = getattr(config, "STARDUST_OPACITY", 0.35) if config else 0.35


def check_nvenc_available() -> bool:
    """Checks if ffmpeg has h264_nvenc encoder enabled and working."""
    global _HAS_NVENC
    if _HAS_NVENC is not None:
        return _HAS_NVENC
    try:
        res = subprocess.run(
            ["ffmpeg", "-hide_banner", "-encoders"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        if "h264_nvenc" in res.stdout:
            test_cmd = [
                "ffmpeg", "-y", "-loglevel", "error",
                "-f", "lavfi", "-i", "color=c=black:s=64x64:d=0.1",
                "-c:v", "h264_nvenc",
                "-f", "null", "-"
            ]
            test_res = subprocess.run(test_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            _HAS_NVENC = (test_res.returncode == 0)
        else:
            _HAS_NVENC = False
    except Exception:
        _HAS_NVENC = False
    return _HAS_NVENC


def build_zoompan_expr(
    zoom_in: bool,
    total_frames: int,
    max_zoom: float = 1.04
) -> Tuple[str, str, str]:
    """
    Constructs centered jitter-free zoompan expressions.
    Returns (zoom_expr, x_expr, y_expr).
    """
    total_frames = max(1, total_frames)
    zoom_delta = max_zoom - 1.00
    zoom_step = zoom_delta / total_frames

    if zoom_in:
        zoom_expr = f"min(zoom+{zoom_step:.8f},{max_zoom:.2f})"
    else:
        zoom_expr = f"if(eq(on,1),{max_zoom:.2f},max(zoom-{zoom_step:.8f},1.00))"

    x_expr = "iw/2-(iw/zoom/2)"
    y_expr = "ih/2-(ih/zoom/2)"
    return zoom_expr, x_expr, y_expr


def build_filter_graph(
    zoom_in: bool = True,
    total_frames: int = 900,
    width: int = 3840,
    height: int = 2160,
    fps: int = 30,
    is_transition_beat: bool = False,
    dim_start_sec: float = 0.0,
    dim_end_sec: float = 0.0,
    sleep_mode: bool = False,
    has_overlay: bool = False,
    stardust_opacity: float = DEFAULT_STARDUST_OPACITY,
    contrast: float = DEFAULT_CONTRAST,
    brightness: float = DEFAULT_BRIGHTNESS,
    saturation: float = DEFAULT_SATURATION,
    gamma: float = DEFAULT_GAMMA,
    vignette: str = DEFAULT_VIGNETTE
) -> Tuple[str, Optional[str]]:
    """
    Constructs the appropriate FFmpeg filter graph based on beat characteristics.
    Returns (filter_string, output_label_or_None).
    """
    zoom_expr, x_expr, y_expr = build_zoompan_expr(zoom_in, total_frames)

    kb_filter = (
        f"scale=8000x4500:force_original_aspect_ratio=increase,"
        f"crop=8000:4500,"
        f"zoompan=z='{zoom_expr}':x='{x_expr}':y='{y_expr}':"
        f"d={total_frames}:s={width}x{height}:fps={fps}"
    )

    # Normalize vignette parameter to ensure aspect ratio
    vig_str = vignette
    if ":aspect=" not in vig_str:
        vig_str = f"{vig_str}:aspect=16/9"

    grade_filter = (
        f"eq=contrast={contrast:.2f}:brightness={brightness:.2f}:saturation={saturation:.2f}:gamma={gamma:.2f},"
        f"vignette={vig_str}"
    )

    if is_transition_beat:
        t0 = max(0.0, float(dim_start_sec))
        t1 = float(dim_end_sec)
        delta = round(t1 - t0, 3)
        if delta <= 0.0:
            t0, t1 = 38.0, 45.0
            delta = 7.0

        cosine_blend = (
            f"if(lte(T,{t0:.3f}),A,if(gte(T,{t1:.3f}),B,"
            f"A*(0.5*(1+cos(PI*(T-{t0:.3f})/{delta:.3f})))+"
            f"B*(0.5*(1-cos(PI*(T-{t0:.3f})/{delta:.3f})))))"
        )

        if has_overlay:
            filter_complex = (
                f"[0:v] {kb_filter} [kb]; "
                f"[kb] split=2 [kb_norm][kb_for_dark]; "
                f"[kb_for_dark] {grade_filter} [kb_dark]; "
                f"[kb_norm][kb_dark] blend=all_expr='{cosine_blend}',format=rgba [kb_dimmed]; "
                f"[1:v] format=rgba,colorchannelmixer=aa={stardust_opacity:.2f} [pts_alpha]; "
                f"[kb_dimmed][pts_alpha] blend=all_mode=screen:all_opacity="
                f"'if(lte(T,{t0:.3f}),0.0,if(gte(T,{t1:.3f}),1.0,0.5*(1-cos(PI*(T-{t0:.3f})/{delta:.3f}))))' [out]"
            )
            return filter_complex, "[out]"
        else:
            # Fallback: Dynamic transition without stardust overlay
            filter_complex = (
                f"[0:v] {kb_filter} [kb]; "
                f"[kb] split=2 [kb_norm][kb_for_dark]; "
                f"[kb_for_dark] {grade_filter} [kb_dark]; "
                f"[kb_norm][kb_dark] blend=all_expr='{cosine_blend}' [out]"
            )
            return filter_complex, "[out]"

    elif sleep_mode:
        if has_overlay:
            filter_complex = (
                f"[0:v] {kb_filter},{grade_filter},format=rgba [kb_dark]; "
                f"[1:v] format=rgba,colorchannelmixer=aa={stardust_opacity:.2f} [pts_alpha]; "
                f"[kb_dark][pts_alpha] blend=all_mode=screen,format=rgba [out]"
            )
            return filter_complex, "[out]"
        else:
            # Fallback: Static sleep grading without overlay
            vf = f"{kb_filter},{grade_filter}"
            return vf, None

    else:
        # Standard baseline Ken Burns motion
        return kb_filter, None


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
    overlay_asset_path: Optional[str] = None
) -> List[str]:
    """
    Builds the complete FFmpeg argument list for rendering a beat clip.
    Handles overlay asset existence verification, codec selection, and pixel format.
    """
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

    use_nvenc = (not force_cpu) and check_nvenc_available()
    if use_nvenc:
        codec_args = ["-c:v", "h264_nvenc", "-preset", "p4", "-cq", "18"]
    else:
        cpu_preset = getattr(config, "CPU_PRESET", "veryfast") if config else "veryfast"
        codec_args = ["-c:v", "libx264", "-preset", cpu_preset, "-crf", "18"]

    cmd = ["ffmpeg", "-y", "-loglevel", "error"]
    cmd += ["-loop", "1", "-i", image_path]

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


def render_kenburns_beat(
    image_path: str,
    duration: float,
    output_clip_path: str,
    zoom_in: bool = True,
    width: int = 3840,
    height: int = 2160,
    fps: int = 30,
    is_transition_beat: bool = False,
    dim_start_sec: float = 0.0,
    dim_end_sec: float = 0.0,
    sleep_mode: bool = False,
    overlay_asset_path: Optional[str] = None,
    force_cpu: bool = False
) -> str:
    """
    Renders a single still image into an ultra-slow Ken Burns video clip with sleep grading.
    Supports:
    - Normal beats: clean cover/story visual pacing.
    - Transition beats (P01_B01): dual-stream cosine easing dimming transition.
    - Sleep mode: darkened, non-destructive low-luma grading with ambient stardust composite.
    - Graceful fallback: renders without overlay if overlay asset is missing.
    """
    if duration <= 0.0:
        raise ValueError(f"duration must be strictly positive, got {duration}")

    if not os.path.exists(image_path):
        raise FileNotFoundError(f"Image not found: {image_path}")

    out_dir = os.path.dirname(output_clip_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    has_overlay = bool(
        overlay_asset_path
        and os.path.isfile(overlay_asset_path)
        and os.access(overlay_asset_path, os.R_OK)
        and os.path.getsize(overlay_asset_path) > 0
    )
    if overlay_asset_path and not has_overlay:
        logger.warning(
            f"Overlay asset not found, unreadable, or invalid at '{overlay_asset_path}'. "
            "Falling back to color grading only."
        )

    cmd = build_render_command(
        image_path=image_path,
        duration=duration,
        output_clip_path=output_clip_path,
        zoom_in=zoom_in,
        fps=fps,
        width=width,
        height=height,
        force_cpu=force_cpu,
        is_transition_beat=is_transition_beat,
        dim_start_sec=dim_start_sec,
        dim_end_sec=dim_end_sec,
        sleep_mode=sleep_mode,
        overlay_asset_path=overlay_asset_path
    )

    subprocess.run(cmd, check=True)
    return output_clip_path
