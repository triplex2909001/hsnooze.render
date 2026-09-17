"""
HistorySnooze Director - Cue PCM Silence Scanner
Scans stitched Part_01.wav for PCM digital zero-silence intervals (Rule <= 150 lines).
"""

import os
import struct
import wave
from typing import List, Tuple


def scan_wav_silence_intervals(
    part_01_wav_path: str,
    intra_silence_sec: float = 1.0
) -> List[Tuple[float, float]]:
    """
    Scans a stitched WAV file for PCM digital zero-silence intervals >= 0.8 * intra_silence_sec.
    Streams samples in 1-second chunks to bound memory usage to < 1 MB RAM.
    Returns list of (start_seconds, end_seconds) tuples for detected silences.
    """
    if not part_01_wav_path or not os.path.exists(part_01_wav_path):
        return []

    zero_intervals: List[Tuple[float, float]] = []
    try:
        with wave.open(part_01_wav_path, "rb") as wf:
            framerate = wf.getframerate()
            n_frames = wf.getnframes()
            n_channels = wf.getnchannels()
            sampwidth = wf.getsampwidth()

            zero_threshold = int(framerate * (intra_silence_sec * 0.8))
            current_zero_count = 0
            frame_offset = 0
            chunk_size = framerate

            while frame_offset < n_frames:
                frames_to_read = min(chunk_size, n_frames - frame_offset)
                raw = wf.readframes(frames_to_read)
                if not raw:
                    break

                try:
                    import numpy as np
                    chunk_samples = np.frombuffer(raw, dtype=np.int16)
                    if n_channels > 1:
                        chunk_samples = chunk_samples.reshape(-1, n_channels)[:, 0]
                    is_silence = (np.abs(chunk_samples) <= 10)
                except Exception:
                    num_samps = len(raw) // (sampwidth or 2)
                    chunk_samples = struct.unpack(f"<{num_samps}h", raw)
                    if n_channels > 1:
                        chunk_samples = chunk_samples[::n_channels]
                    is_silence = [abs(s) <= 10 for s in chunk_samples]

                for s_silence in is_silence:
                    if s_silence:
                        current_zero_count += 1
                    else:
                        if current_zero_count >= zero_threshold:
                            start_s = (frame_offset - current_zero_count) / framerate
                            end_s = frame_offset / framerate
                            zero_intervals.append((start_s, end_s))
                        current_zero_count = 0
                    frame_offset += 1

            if current_zero_count >= zero_threshold:
                start_s = (frame_offset - current_zero_count) / framerate
                end_s = frame_offset / framerate
                zero_intervals.append((start_s, end_s))

    except Exception:
        pass

    return zero_intervals
