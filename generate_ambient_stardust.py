"""
HistorySnooze Director - Ambient Stardust Procedural Generator
Generates a 15.0-second seamless looping 4K UHD (3840x2160) ambient stardust particle overlay.
Rule <= 150 lines compliant facade.
"""

import argparse
import logging
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

_DIR = str(Path(__file__).resolve().parent)
if _DIR not in sys.path:
    sys.path.insert(0, _DIR)

from stardust_particle_sim import init_stardust_particles, render_stardust_frame

try:
    import config
except ImportError:
    config = None

logger = logging.getLogger("hsnooze.render.generate_ambient_stardust")

DEFAULT_WIDTH = getattr(config, "WIDTH", 3840) if config else 3840
DEFAULT_HEIGHT = getattr(config, "HEIGHT", 2160) if config else 2160
DEFAULT_FPS = getattr(config, "FPS", 30) if config else 30
DEFAULT_DURATION = 15.0
DEFAULT_OUTPUT_PATH = "assets/ambient_stardust_loop.mp4"


def generate_ambient_stardust_loop(
    output_path: str = DEFAULT_OUTPUT_PATH,
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT,
    fps: int = DEFAULT_FPS,
    duration: float = DEFAULT_DURATION,
    num_particles: int = 220,
    seed: int = 42
) -> str:
    """Renders 15-second seamless looping 4K ambient stardust video."""
    ffmpeg_bin = shutil.which("ffmpeg")
    if not ffmpeg_bin:
        raise RuntimeError("ffmpeg binary not found in PATH.")

    abs_output = os.path.abspath(output_path)
    os.makedirs(os.path.dirname(abs_output), exist_ok=True)
    total_frames = int(duration * fps)

    print(f"[STARDUST] Generating {duration}s ({total_frames} frames) 4K stardust loop @ {fps} FPS...")
    particles = init_stardust_particles(num_particles, width, height, seed)

    ffmpeg_cmd = [
        ffmpeg_bin, "-y", "-loglevel", "warning",
        "-f", "rawvideo", "-vcodec", "rawvideo",
        "-s", f"{width}x{height}", "-pix_fmt", "bgr24",
        "-r", str(fps), "-i", "-",
        "-c:v", "libx264", "-preset", "slow", "-crf", "18",
        "-pix_fmt", "yuv420p", abs_output
    ]

    t0 = time.time()
    pipe = subprocess.Popen(ffmpeg_cmd, stdin=subprocess.PIPE)
    success = False
    try:
        for f_idx in range(total_frames):
            frame_bytes = render_stardust_frame(particles, f_idx, total_frames, width, height)
            pipe.stdin.write(frame_bytes)
        pipe.stdin.close()
        pipe.wait()
        if pipe.returncode != 0:
            raise RuntimeError(f"FFmpeg encoding failed with return code {pipe.returncode}")
        success = True
    except (BrokenPipeError, Exception) as exc:
        raise RuntimeError(f"Stardust generation aborted: {exc}") from exc
    finally:
        if pipe.stdin and not pipe.stdin.closed:
            try:
                pipe.stdin.close()
            except OSError:
                pass
        if pipe.poll() is None:
            pipe.kill()
            pipe.wait()
        if not success and os.path.lexists(abs_output):
            try:
                os.remove(abs_output)
            except OSError:
                pass

    elapsed = time.time() - t0
    file_size_mb = os.path.getsize(abs_output) / (1024 * 1024) if os.path.exists(abs_output) else 0.0
    print(f"✅ Generated seamless stardust loop in {elapsed:.1f}s ({file_size_mb:.2f} MB): {abs_output}")
    return abs_output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate Ambient Stardust Looping Overlay")
    parser.add_argument("--output", type=str, default=DEFAULT_OUTPUT_PATH, help="Output MP4 path")
    parser.add_argument("--width", type=int, default=DEFAULT_WIDTH, help="Width in pixels")
    parser.add_argument("--height", type=int, default=DEFAULT_HEIGHT, help="Height in pixels")
    parser.add_argument("--fps", type=int, default=DEFAULT_FPS, help="Frames per second")
    parser.add_argument("--duration", type=float, default=DEFAULT_DURATION, help="Duration in seconds")
    parser.add_argument("--particles", type=int, default=220, help="Number of particles")
    args = parser.parse_args()

    generate_ambient_stardust_loop(
        output_path=args.output, width=args.width, height=args.height,
        fps=args.fps, duration=args.duration, num_particles=args.particles
    )
