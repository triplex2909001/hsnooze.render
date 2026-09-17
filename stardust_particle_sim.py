"""
HistorySnooze Director - Stardust Particle Simulation
Periodic drifting particle simulation and frame rasterization (Rule <= 150 lines).
"""

import math
import random
from typing import Any, Dict, List

try:
    import numpy as np
except ImportError:
    np = None

try:
    import cv2
except ImportError:
    cv2 = None


def init_stardust_particles(
    num_particles: int,
    width: int,
    height: int,
    seed: int = 42
) -> List[Dict[str, Any]]:
    """Initializes deterministic harmonic particles for seamless looping."""
    rng = np.random.RandomState(seed) if np is not None else random.Random(seed)
    particles = []
    for _ in range(num_particles):
        uniform = rng.uniform if hasattr(rng, "uniform") else rng.uniform
        randint = rng.randint if hasattr(rng, "randint") else rng.randint
        choice = rng.choice if hasattr(rng, "choice") else rng.choice

        x0 = uniform(0, width)
        y0 = uniform(0, height)
        k_y = choice([-2, -1, 0])
        k_x = choice([-1, 0, 1])
        amp_x = uniform(15.0, 45.0)
        amp_y = uniform(10.0, 30.0)
        freq_x = choice([1, 2, 3])
        freq_y = choice([1, 2])
        phase_x = uniform(0, 2 * math.pi)
        phase_y = uniform(0, 2 * math.pi)
        twinkle_freq = choice([1, 2, 3, 4])
        twinkle_phase = uniform(0, 2 * math.pi)
        twinkle_depth = uniform(0.2, 0.5)

        p_type = choice(["sharp", "glow", "bokeh"])
        if p_type == "sharp":
            radius = randint(2, 5)
            base_color = (randint(180, 220), randint(220, 245), randint(245, 255))
            base_alpha = uniform(0.5, 0.9)
        elif p_type == "glow":
            radius = randint(6, 11)
            base_color = (randint(120, 170), randint(190, 225), randint(240, 255))
            base_alpha = uniform(0.35, 0.7)
        else:
            radius = randint(14, 26)
            base_color = (randint(80, 130), randint(150, 195), randint(220, 245))
            base_alpha = uniform(0.15, 0.35)

        particles.append({
            "x0": x0, "y0": y0, "k_x": k_x, "k_y": k_y,
            "amp_x": amp_x, "amp_y": amp_y,
            "freq_x": freq_x, "freq_y": freq_y,
            "phase_x": phase_x, "phase_y": phase_y,
            "twinkle_freq": twinkle_freq,
            "twinkle_phase": twinkle_phase,
            "twinkle_depth": twinkle_depth,
            "radius": radius, "base_color": base_color,
            "base_alpha": base_alpha
        })
    return particles


def render_stardust_frame(
    particles: List[Dict[str, Any]],
    frame_idx: int,
    total_frames: int,
    width: int,
    height: int
) -> bytes:
    """Renders a single frame of procedural stardust particles to raw BGR bytes."""
    if np is None or cv2 is None:
        return b"\x00" * (width * height * 3)

    t_norm = frame_idx / total_frames
    canvas = np.zeros((height, width, 3), dtype=np.uint8)

    for p in particles:
        x = (p["x0"] + p["k_x"] * width * t_norm) % width
        y = (p["y0"] + p["k_y"] * height * t_norm) % height
        x += p["amp_x"] * math.sin(2 * math.pi * p["freq_x"] * t_norm + p["phase_x"])
        y += p["amp_y"] * math.sin(2 * math.pi * p["freq_y"] * t_norm + p["phase_y"])
        x = int(x) % width
        y = int(y) % height

        pulse = 1.0 + p["twinkle_depth"] * math.sin(2 * math.pi * p["twinkle_freq"] * t_norm + p["twinkle_phase"])
        cur_alpha = min(1.0, max(0.0, p["base_alpha"] * pulse))
        b, g, r = p["base_color"]
        col = (int(b * cur_alpha), int(g * cur_alpha), int(r * cur_alpha))
        cv2.circle(canvas, (x, y), p["radius"], col, -1, cv2.LINE_AA)

    canvas = cv2.GaussianBlur(canvas, (5, 5), 0)
    return canvas.tobytes()
