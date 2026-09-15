"""
HistorySnooze Director - Ambient Stardust Procedural Generator
Generates a 15.0-second seamless looping 4K UHD (3840x2160) ambient stardust particle overlay
for deep sleep video compositing (Requirement R3).
Features:
- Perfectly seamless periodic drift & twinkle across 15.0 seconds (450 frames @ 30fps).
- Toroidal coordinate wrapping and integer harmonic sinusoidal sway (zero jump at boundary).
- Multi-scale soft Gaussian glowing motes in warm amber/golden bedtime tones.
- Direct rawvideo pipe into FFmpeg for clean H.264 YUV420p master encoding.
"""

import os
import math
import time
import shutil
import argparse
import subprocess


try:
    import numpy as np
except ImportError:
    np = None

try:
    import cv2
except ImportError:
    cv2 = None

try:
    import config
except ImportError:
    config = None

DEFAULT_WIDTH = getattr(config, "WIDTH", 3840) if config else 3840
DEFAULT_HEIGHT = getattr(config, "HEIGHT", 2160) if config else 2160
DEFAULT_FPS = getattr(config, "FPS", 30) if config else 30
DEFAULT_DURATION = 15.0  # 15 seconds loop = 450 frames @ 30fps
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
    """
    Renders 15-second seamless looping 4K ambient stardust video.
    """
    if np is None or cv2 is None:
        raise ImportError(
            "numpy and opencv-python (cv2) are required to generate the stardust video. "
            "Please install them or run in an environment with OpenCV available."
        )

    ffmpeg_bin = shutil.which("ffmpeg")
    if not ffmpeg_bin:
        raise RuntimeError("ffmpeg binary not found in PATH. ffmpeg is required to encode the video stream.")

    abs_output = os.path.abspath(output_path)
    os.makedirs(os.path.dirname(abs_output), exist_ok=True)
    total_frames = int(duration * fps)

    print(f"[STARDUST] Generating {duration}s ({total_frames} frames) 4K stardust loop @ {fps} FPS...")
    print(f"[STARDUST] Output target: {abs_output}")

    # Initialize deterministic particle simulation
    rng = np.random.RandomState(seed)

    particles = []
    for _ in range(num_particles):
        x0 = rng.uniform(0, width)
        y0 = rng.uniform(0, height)
        # Integer toroidal drift wraps (guarantees exact position match at t=0 and t=1)
        k_y = rng.choice([-2, -1, 0])
        k_x = rng.choice([-1, 0, 1])
        # Harmonic sway amplitudes (pixels) and integer frequencies
        amp_x = rng.uniform(15.0, 45.0)
        amp_y = rng.uniform(10.0, 30.0)
        freq_x = rng.choice([1, 2, 3])
        freq_y = rng.choice([1, 2])
        phase_x = rng.uniform(0, 2 * math.pi)
        phase_y = rng.uniform(0, 2 * math.pi)
        # Twinkle pulse
        twinkle_freq = rng.choice([1, 2, 3, 4])
        twinkle_phase = rng.uniform(0, 2 * math.pi)
        twinkle_depth = rng.uniform(0.2, 0.5)

        # Particle aesthetic categories
        p_type = rng.choice(["sharp", "glow", "bokeh"], p=[0.55, 0.35, 0.10])
        if p_type == "sharp":
            radius = rng.randint(2, 5)
            # Warm ivory / pale gold (BGR)
            base_color = (rng.randint(180, 220), rng.randint(220, 245), rng.randint(245, 255))
            base_alpha = rng.uniform(0.5, 0.9)
        elif p_type == "glow":
            radius = rng.randint(6, 11)
            # Golden amber (BGR)
            base_color = (rng.randint(120, 170), rng.randint(190, 225), rng.randint(240, 255))
            base_alpha = rng.uniform(0.35, 0.7)
        else:  # bokeh
            radius = rng.randint(14, 26)
            # Deep soft amber (BGR)
            base_color = (rng.randint(80, 130), rng.randint(150, 195), rng.randint(220, 245))
            base_alpha = rng.uniform(0.15, 0.35)

        particles.append({
            "x0": x0, "y0": y0,
            "k_x": k_x, "k_y": k_y,
            "amp_x": amp_x, "amp_y": amp_y,
            "freq_x": freq_x, "freq_y": freq_y,
            "phase_x": phase_x, "phase_y": phase_y,
            "twinkle_freq": twinkle_freq,
            "twinkle_phase": twinkle_phase,
            "twinkle_depth": twinkle_depth,
            "radius": radius,
            "base_color": base_color,
            "base_alpha": base_alpha
        })

    # Setup FFmpeg rawvideo pipe
    ffmpeg_cmd = [
        ffmpeg_bin, "-y", "-loglevel", "warning",
        "-f", "rawvideo",
        "-vcodec", "rawvideo",
        "-s", f"{width}x{height}",
        "-pix_fmt", "bgr24",
        "-r", str(fps),
        "-i", "-",
        "-c:v", "libx264",
        "-preset", "slow",
        "-crf", "18",
        "-pix_fmt", "yuv420p",
        abs_output
    ]

    t0 = time.time()
    pipe = subprocess.Popen(ffmpeg_cmd, stdin=subprocess.PIPE)
    success = False

    try:
        for frame_idx in range(total_frames):
            t_norm = frame_idx / total_frames  # [0.0, 1.0)

            # Pure black canvas
            canvas = np.zeros((height, width, 3), dtype=np.uint8)

            # Draw particles
            for p in particles:
                # Linear periodic toroidal wrap
                x = (p["x0"] + p["k_x"] * width * t_norm) % width
                y = (p["y0"] + p["k_y"] * height * t_norm) % height

                # Harmonic sinusoidal sway (exact 0 at t_norm=0 and t_norm=1)
                x += p["amp_x"] * math.sin(2 * math.pi * p["freq_x"] * t_norm + p["phase_x"])
                y += p["amp_y"] * math.sin(2 * math.pi * p["freq_y"] * t_norm + p["phase_y"])
                x = int(x) % width
                y = int(y) % height

                # Twinkle modulation (exact match at t_norm=0 and t_norm=1)
                pulse = 1.0 + p["twinkle_depth"] * math.sin(2 * math.pi * p["twinkle_freq"] * t_norm + p["twinkle_phase"])
                cur_alpha = min(1.0, max(0.0, p["base_alpha"] * pulse))

                # Scaled color
                b, g, r = p["base_color"]
                col = (int(b * cur_alpha), int(g * cur_alpha), int(r * cur_alpha))

                cv2.circle(canvas, (x, y), p["radius"], col, -1, cv2.LINE_AA)

            # Gentle subtle blur on large/medium particles to create hypnotic glowing bokeh
            canvas = cv2.GaussianBlur(canvas, (5, 5), 0)

            # Write to FFmpeg stdin
            pipe.stdin.write(canvas.tobytes())

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
    file_size_mb = os.path.getsize(abs_output) / (1024 * 1024)
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
        output_path=args.output,
        width=args.width,
        height=args.height,
        fps=args.fps,
        duration=args.duration,
        num_particles=args.particles
    )
