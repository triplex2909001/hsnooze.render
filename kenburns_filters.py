"""
HistorySnooze Director - Ken Burns Filter Graph Builder
Constructs centered zoompan expressions and dynamic sleep shading filter graphs (Rule <= 150 lines).
"""

import math
import re
from typing import Optional, Tuple

try:
    import config
except ImportError:
    config = None

DEFAULT_CONTRAST = getattr(config, "SLEEP_CONTRAST", 0.96) if config else 0.96
DEFAULT_BRIGHTNESS = getattr(config, "SLEEP_BRIGHTNESS", -0.04) if config else -0.04
DEFAULT_GAMMA = getattr(config, "SLEEP_GAMMA", 0.95) if config else 0.95
DEFAULT_SATURATION = getattr(config, "SLEEP_SATURATION", 0.92) if config else 0.92
DEFAULT_VIGNETTE = getattr(config, "SLEEP_VIGNETTE", "none") if config else "none"
DEFAULT_STARDUST_OPACITY = getattr(config, "STARDUST_OPACITY", 0.35) if config else 0.35
DEFAULT_ZOOM_BASE = getattr(config, "ZOOM_BASE", 1.10) if config else 1.10
DEFAULT_ZOOM_MAX = getattr(config, "ZOOM_MAX", 1.15) if config else 1.15


def build_zoompan_expr(
    zoom_in: bool,
    total_frames: int,
    base_zoom: float = DEFAULT_ZOOM_BASE,
    max_zoom: float = DEFAULT_ZOOM_MAX
) -> Tuple[str, str, str]:
    """Constructs centered jitter-free zoompan expressions (zoom_expr, x_expr, y_expr).

    Watermark-safe: the view starts at base_zoom (default 1.10), so the outer edge
    zone holding watermarks/borders/corner artifacts never enters the frame.
    """
    total_frames = max(1, total_frames)
    base_zoom = max(1.0, float(base_zoom))
    max_zoom = max(base_zoom, float(max_zoom))
    zoom_delta = max_zoom - base_zoom
    zoom_step = zoom_delta / total_frames

    if zoom_in:
        zoom_expr = f"min(max(zoom+{zoom_step:.8f},{base_zoom:.2f}),{max_zoom:.2f})"
    else:
        zoom_expr = f"if(eq(on,1),{max_zoom:.2f},max(zoom-{zoom_step:.8f},{base_zoom:.2f}))"

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
    """Constructs FFmpeg filter graph (filter_string, output_label_or_None)."""
    total_frames = max(1, total_frames)
    zoom_expr, x_expr, y_expr = build_zoompan_expr(zoom_in, total_frames)

    pad_w = int(width * 1.10)
    pad_h = int(height * 1.10)
    if pad_w % 2 != 0:
        pad_w += 1
    if pad_h % 2 != 0:
        pad_h += 1

    kb_filter = (
        f"scale={pad_w}x{pad_h}:force_original_aspect_ratio=increase,"
        f"crop={pad_w}:{pad_h},"
        f"zoompan=z='{zoom_expr}':x='{x_expr}':y='{y_expr}':"
        f"d={total_frames}:s={width}x{height}:fps={fps}"
    )

    if is_transition_beat:
        t0 = max(0.0, float(dim_start_sec))
        t1 = float(dim_end_sec)
        delta = max(0.1, round(t1 - t0, 3))

        eq_dynamic = (
            f"eq=contrast='if(lte(t,{t0:.3f}),1.0,if(gte(t,{t1:.3f}),{contrast:.2f},1.0+({contrast:.2f}-1.0)*(0.5*(1-cos(PI*(t-{t0:.3f})/{delta:.3f})))))':"
            f"brightness='if(lte(t,{t0:.3f}),0.0,if(gte(t,{t1:.3f}),{brightness:.2f},{brightness:.2f}*(0.5*(1-cos(PI*(t-{t0:.3f})/{delta:.3f})))))':"
            f"saturation='if(lte(t,{t0:.3f}),1.0,if(gte(t,{t1:.3f}),{saturation:.2f},1.0+({saturation:.2f}-1.0)*(0.5*(1-cos(PI*(t-{t0:.3f})/{delta:.3f})))))':"
            f"gamma='if(lte(t,{t0:.3f}),1.0,if(gte(t,{t1:.3f}),{gamma:.2f},1.0+({gamma:.2f}-1.0)*(0.5*(1-cos(PI*(t-{t0:.3f})/{delta:.3f})))))'"
        )

        if has_overlay:
            filter_complex = (
                f"[0:v] {kb_filter},{eq_dynamic} [kb_graded]; "
                f"[1:v] scale={width}:{height},format=yuva420p,colorkey=0x000000:0.05:0.1,colorchannelmixer=aa={stardust_opacity:.2f},fade=t=in:st={t0:.3f}:d={delta:.3f}:alpha=1 [pts_alpha]; "
                f"[kb_graded][pts_alpha] overlay=shortest=1:format=auto [out]"
            )
            return filter_complex, "[out]"
        else:
            return f"{kb_filter},{eq_dynamic}", None

    elif sleep_mode:
        grade_filter = f"eq=contrast={contrast:.2f}:brightness={brightness:.2f}:saturation={saturation:.2f}:gamma={gamma:.2f}"
        if has_overlay:
            filter_complex = (
                f"[0:v] {kb_filter},{grade_filter} [kb_graded]; "
                f"[1:v] scale={width}:{height},format=yuva420p,colorkey=0x000000:0.05:0.1,colorchannelmixer=aa={stardust_opacity:.2f} [pts_alpha]; "
                f"[kb_graded][pts_alpha] overlay=shortest=1:format=auto [out]"
            )
            return filter_complex, "[out]"
        else:
            return f"{kb_filter},{grade_filter}", None

    return kb_filter, None
