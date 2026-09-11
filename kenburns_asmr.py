"""
HistorySnooze Director - Ken Burns ASMR Engine
Renders slow, hypnotic Ken Burns camera movements for deep sleep documentaries.
Features anti-jitter 8K prescaling and ultra-subtle 4% zoom over 75-90 seconds.
"""

import os
import subprocess
from typing import Optional

def render_kenburns_beat(
    image_path: str,
    duration: float,
    output_clip_path: str,
    zoom_in: bool = True,
    fps: int = 30,
    width: int = 3840,
    height: int = 2160
) -> str:
    """
    Renders a single 4K still image into an ultra-slow Ken Burns video clip.
    
    Technical Highlights:
    1. Scale to 8000x4500: Prevents FFmpeg sub-pixel raster jitter on slow movements.
    2. Dynamic zoompan expression: Increments zoom at micro-steps per frame.
    3. Output in native 4K UHD (3840x2160) at 30 fps, YUV420p.
    """
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"Image not found: {image_path}")
        
    os.makedirs(os.path.dirname(output_clip_path), exist_ok=True)
    
    total_frames = max(1, int(duration * fps))
    # Zoom range: 1.00 to 1.04 (4% total delta)
    max_zoom = 1.04
    zoom_delta = max_zoom - 1.00
    zoom_step = zoom_delta / total_frames
    
    if zoom_in:
        # Push-in slowly from 1.00 to 1.04
        zoom_expr = f"min(zoom+{zoom_step:.8f},{max_zoom})"
        x_expr = "iw/2-(iw/zoom/2)"
        y_expr = "ih/2-(ih/zoom/2)"
    else:
        # Pull-out slowly from 1.04 to 1.00
        zoom_expr = f"if(eq(on,1),{max_zoom},max(zoom-{zoom_step:.8f},1.00))"
        x_expr = "iw/2-(iw/zoom/2)"
        y_expr = "ih/2-(ih/zoom/2)"
        
    # FFmpeg video filter graph:
    # 1. Scale up to 8000x4500 (preserving 16:9)
    # 2. zoompan with micro-increment over total_frames
    # 3. Output at target width x height
    vf_filter = (
        f"scale=8000x4500:force_original_aspect_ratio=increase,"
        f"crop=8000:4500,"
        f"zoompan=z='{zoom_expr}':x='{x_expr}':y='{y_expr}':"
        f"d={total_frames}:s={width}x{height}:fps={fps}"
    )
    
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-loop", "1", "-i", image_path,
        "-t", f"{duration:.3f}",
        "-vf", vf_filter,
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", "18",
        "-pix_fmt", "yuv420p",
        output_clip_path
    ]
    
    subprocess.run(cmd, check=True)
    return output_clip_path
