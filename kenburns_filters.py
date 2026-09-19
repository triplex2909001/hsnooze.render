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

DEFAULT_CONTRAST = getattr(config, "SLEEP_CONTRAST", 0.90) if config else 0.90
DEFAULT_BRIGHTNESS = getattr(config, "SLEEP_BRIGHTNESS", -0.05) if config else -0.05
DEFAULT_GAMMA = getattr(config, "SLEEP_GAMMA", 0.85) if config else 0.85
DEFAULT_SATURATION = getattr(config, "SLEEP_SATURATION", 0.88) if config else 0.88
DEFAULT_VIGNETTE = getattr(config, "SLEEP_VIGNETTE", "none") if config else "none"
DEFAULT_STARDUST_OPACITY = getattr(config, "STARDUST_OPACITY", 0.35) if config else 0.35


def build_zoompan_expr(
    zoom_in: bool,
    total_frames: int,
    max_zoom: float = 1.04
) -> Tuple[str, str, str]:
    """Constructs centered jitter-free zoompan expressions (zoom_expr, x_expr, y_expr)."""
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

    vig_str = vignette if vignette is not None else DEFAULT_VIGNETTE
    if vig_str and str(vig_str).strip().lower() not in ("none", "0", "false", ""):
        if ":aspect=" in str(vig_str):
            vig_str = re.sub(r":aspect=[0-9/.]+", f":aspect={width}/{height}", str(vig_str))
        else:
            vig_str = f"{vig_str}:aspect={width}/{height}"
        grade_filter = (
            f"eq=contrast={contrast:.2f}:brightness={brightness:.2f}:saturation={saturation:.2f}:gamma={gamma:.2f},"
            f"vignette={vig_str}"
        )
    else:
        grade_filter = (
            f"eq=contrast={contrast:.2f}:brightness={brightness:.2f}:saturation={saturation:.2f}:gamma={gamma:.2f}"
        )

    if is_transition_beat:
        t0 = max(0.0, float(dim_start_sec))
        t1 = float(dim_end_sec)
        delta = round(t1 - t0, 3)
        if delta <= 0.0:
            t0, t1, delta = 38.0, 45.0, 7.0

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
                f"[1:v] scale={width}:{height},format=rgba,colorchannelmixer=aa={stardust_opacity:.2f},fade=t=in:st={t0:.3f}:d={delta:.3f}:alpha=1 [pts_alpha]; "
                f"[kb_dimmed][pts_alpha] blend=all_mode=screen [out]"
            )
            return filter_complex, "[out]"
        else:
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
                f"[1:v] scale={width}:{height},format=rgba,colorchannelmixer=aa={stardust_opacity:.2f} [pts_alpha]; "
                f"[kb_dark][pts_alpha] blend=all_mode=screen,format=rgba [out]"
            )
            return filter_complex, "[out]"
        else:
            return f"{kb_filter},{grade_filter}", None

    return kb_filter, None
