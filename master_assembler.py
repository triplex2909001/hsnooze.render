"""
HistorySnooze Director - Master Concatenation & Gatekeeper GK7 Auditor
Concatenates 15 chunk parts with 5.0-second ambient inter-part silences.
Uses FFmpeg Stream Copy (-c copy) for rapid assembly in under 30 seconds without re-encoding.
"""

import os
import subprocess
from typing import List, Dict

def create_5s_silence_clip(output_path: str, width: int = 3840, height: int = 2160, fps: int = 30, sample_rate: int = 24000, channels: int = 1) -> str:
    """
    Generates a 5.0s 4K black video clip with silent AAC audio matching chunk stream parameters.
    """
    if os.path.exists(output_path):
        try:
            os.remove(output_path)
        except OSError:
            pass

    out_dir = os.path.dirname(output_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    ch_layout = "mono" if channels == 1 else "stereo"
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "lavfi", "-i", f"color=c=black:s={width}x{height}:d=5.0:r={fps}",
        "-f", "lavfi", "-i", f"anullsrc=r={sample_rate}:cl={ch_layout}",
        "-t", "5.0",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-ar", str(sample_rate), "-ac", str(channels),
        output_path
    ]
    subprocess.run(cmd, check=True)
    return output_path

def audit_master_video_gk7(output_master_path: str) -> Dict[str, any]:
    """
    Validates Gatekeeper GK7: duration >= 80.0 mins and file size > 500 MB.
    """
    cmd_probe = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration:format=size",
        "-of", "default=noprint_wrappers=1:nokey=1",
        output_master_path
    ]
    res = subprocess.run(cmd_probe, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
    lines = res.stdout.strip().split("\n")
    duration_sec = float(lines[0])
    size_bytes = int(lines[1])
    duration_min = duration_sec / 60.0

    passed_gk7 = (duration_min >= 80.0) and (size_bytes > 500 * 1024 * 1024)

    audit_result = {
        "output_path": output_master_path,
        "duration_minutes": round(duration_min, 2),
        "duration_seconds": round(duration_sec, 2),
        "file_size_gb": round(size_bytes / (1024 ** 3), 2),
        "passed_gk7": passed_gk7
    }
    return audit_result


def assemble_master_video(
    chunk_paths: List[str],
    output_master_path: str,
    temp_dir: str
) -> Dict[str, any]:
    """
    Concatenates all 15 Part chunks with 5-second silences between them.
    Performs Stream Copy (-c copy) to assemble the final 90-minute MP4 without re-encoding.
    """
    if len(chunk_paths) != 15:
        print(f"⚠️ Warning: Expected 15 chunks, received {len(chunk_paths)}.")

    if temp_dir:
        os.makedirs(temp_dir, exist_ok=True)
    out_master_dir = os.path.dirname(output_master_path)
    if out_master_dir:
        os.makedirs(out_master_dir, exist_ok=True)

    sample_rate = 24000
    channels = 1
    if chunk_paths and os.path.exists(chunk_paths[0]):
        try:
            probe_cmd = ["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=sample_rate,channels", "-of", "default=noprint_wrappers=1:nokey=1", chunk_paths[0]]
            out_probe = subprocess.check_output(probe_cmd, text=True).strip().split()
            if len(out_probe) >= 2:
                sample_rate = int(out_probe[0])
                channels = int(out_probe[1])
        except Exception:
            pass

    silence_clip_path = os.path.join(temp_dir, "silence_5s.mp4")
    create_5s_silence_clip(silence_clip_path, sample_rate=sample_rate, channels=channels)

    def _esc(p: str) -> str:
        return os.path.abspath(p).replace("'", "'\\''")

    concat_list_path = os.path.join(temp_dir, "master_concat_list.txt")
    with open(concat_list_path, "w", encoding="utf-8") as f_list:
        for idx, chunk in enumerate(chunk_paths, start=1):
            f_list.write(f"file '{_esc(chunk)}'\n")
            # Interleave 5s silence between parts (except after the final part)
            if idx < len(chunk_paths):
                f_list.write(f"file '{_esc(silence_clip_path)}'\n")

    print(f"[ASSEMBLER] Concatenating master video via stream copy...")
    cmd_concat = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "concat", "-safe", "0",
        "-i", concat_list_path,
        "-c", "copy",
        output_master_path
    ]
    subprocess.run(cmd_concat, check=True)

    audit_result = audit_master_video_gk7(output_master_path)
    print(f"🎬 Master Assembly Complete: {audit_result['duration_minutes']:.1f} mins, {audit_result['file_size_gb']} GB (GK7: {'PASSED' if audit_result['passed_gk7'] else 'FAILED'})")
    return audit_result
