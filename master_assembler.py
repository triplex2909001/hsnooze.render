"""
HistorySnooze Director - Master Concatenation & Gatekeeper GK7 Auditor
Concatenates 15 chunk parts with 5.0-second ambient inter-part silences.
Uses FFmpeg Stream Copy (-c copy) for rapid assembly in under 30 seconds without re-encoding.
"""

import os
import subprocess
from typing import List, Dict

def create_5s_silence_clip(output_path: str, width: int = 3840, height: int = 2160, fps: int = 30) -> str:
    """
    Generates a 5.0s 4K black video clip with completely silent AAC stereo audio.
    """
    if os.path.exists(output_path) and os.path.getsize(output_path) > 1024 * 100:
        return output_path
        
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "lavfi", "-i", f"color=c=black:s={width}x{height}:d=5.0:r={fps}",
        "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
        "-t", "5.0",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "256k",
        output_path
    ]
    subprocess.run(cmd, check=True)
    return output_path

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
        
    os.makedirs(temp_dir, exist_ok=True)
    os.makedirs(os.path.dirname(output_master_path), exist_ok=True)
    
    silence_clip_path = os.path.join(temp_dir, "silence_5s.mp4")
    create_5s_silence_clip(silence_clip_path)
    
    concat_list_path = os.path.join(temp_dir, "master_concat_list.txt")
    with open(concat_list_path, "w", encoding="utf-8") as f_list:
        for idx, chunk in enumerate(chunk_paths, start=1):
            f_list.write(f"file '{os.path.abspath(chunk)}'\n")
            # Interleave 5s silence between parts (except after the final part)
            if idx < len(chunk_paths):
                f_list.write(f"file '{os.path.abspath(silence_clip_path)}'\n")
                
    print(f"[ASSEMBLER] Concatenating master video via stream copy...")
    cmd_concat = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "concat", "-safe", "0",
        "-i", concat_list_path,
        "-c", "copy",
        output_master_path
    ]
    subprocess.run(cmd_concat, check=True)
    
    # Audit Gatekeeper GK7
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
    
    passed_gk7 = (80.0 <= duration_min <= 95.0) and (size_bytes > 500 * 1024 * 1024)
    
    audit_result = {
        "output_path": output_master_path,
        "duration_minutes": round(duration_min, 2),
        "duration_seconds": round(duration_sec, 2),
        "file_size_gb": round(size_bytes / (1024 ** 3), 2),
        "passed_gk7": passed_gk7
    }
    
    print(f"🎬 Master Assembly Complete: {duration_min:.1f} mins, {audit_result['file_size_gb']} GB (GK7: {'PASSED' if passed_gk7 else 'FAILED'})")
    return audit_result
