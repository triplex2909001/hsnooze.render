"""
HistorySnooze Director - Chunk Part Renderer
Renders individual 5-6 minute part chunks (chunk_part_01.mp4 ... chunk_part_15.mp4).
Includes Smart Delta Restart logic to avoid re-rendering valid existing parts.
"""

import os
import subprocess
from typing import List, Dict
from kenburns_asmr import render_kenburns_beat
from beat_aligner import align_part_beats

MIN_VALID_CHUNK_BYTES = 10 * 1024 * 1024  # 10 MB minimum for 4K video

def is_chunk_valid(chunk_path: str) -> bool:
    """
    Checks if a chunk MP4 exists, is greater than 10MB, and has valid playable streams.
    """
    if not os.path.exists(chunk_path):
        return False
    if os.path.getsize(chunk_path) < MIN_VALID_CHUNK_BYTES:
        return False
        
    try:
        cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            chunk_path
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        dur = float(res.stdout.strip())
        return dur > 60.0  # Must be at least 1 minute long
    except Exception:
        return False

def render_part_chunk(
    part_index: int,
    audio_wav_path: str,
    beat_images: List[str],
    output_dir: str,
    temp_dir: str
) -> str:
    """
    Renders an individual part into a standalone MP4 chunk:
    1. Check Smart Delta Restart: skip if already valid.
    2. Render Ken Burns ASMR video for each beat (alternating zoom in/out).
    3. Concat beat video clips with audio track.
    4. Save to output_dir/chunk_part_XX.mp4.
    """
    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(temp_dir, exist_ok=True)
    
    chunk_filename = f"chunk_part_{part_index:02d}.mp4"
    chunk_path = os.path.join(output_dir, chunk_filename)
    
    # 1. Smart Delta Restart Check
    if is_chunk_valid(chunk_path):
        print(f"[SMART DELTA RESTART] Part {part_index:02d} is already rendered and valid. Skipping.")
        return chunk_path
        
    print(f"[RENDER] Beginning render for Part {part_index:02d} ({len(beat_images)} beats)...")
    
    # 2. Align Beats
    alignment = align_part_beats(part_index, audio_wav_path, beat_images)
    beats = alignment["beats"]
    
    beat_clips = []
    concat_list_path = os.path.join(temp_dir, f"part_{part_index:02d}_concat.txt")
    
    with open(concat_list_path, "w", encoding="utf-8") as f_concat:
        for idx, beat in enumerate(beats, start=1):
            beat_clip_path = os.path.join(temp_dir, f"beat_P{part_index:02d}_B{idx:02d}.mp4")
            zoom_in = (idx % 2 != 0)  # Alternate zoom in and zoom out
            
            # Check if individual beat clip already rendered
            if not os.path.exists(beat_clip_path) or os.path.getsize(beat_clip_path) < 1024 * 1024:
                render_kenburns_beat(
                    image_path=beat["image_path"],
                    duration=beat["duration"],
                    output_clip_path=beat_clip_path,
                    zoom_in=zoom_in
                )
                
            beat_clips.append(beat_clip_path)
            f_concat.write(f"file '{os.path.abspath(beat_clip_path)}'\n")
            
    # 3. Assemble Visual Beats + Audio into Part Chunk
    temp_video_only = os.path.join(temp_dir, f"part_{part_index:02d}_video.mp4")
    cmd_video = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "concat", "-safe", "0",
        "-i", concat_list_path,
        "-c", "copy",
        temp_video_only
    ]
    subprocess.run(cmd_video, check=True)
    
    # Mux video with audio WAV
    cmd_mux = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", temp_video_only,
        "-i", audio_wav_path,
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "256k",
        "-shortest",
        chunk_path
    ]
    subprocess.run(cmd_mux, check=True)
    
    # Cleanup temp intermediate video
    if os.path.exists(temp_video_only):
        os.remove(temp_video_only)
        
    print(f"✅ Finished Part {part_index:02d} Chunk: {chunk_path}")
    return chunk_path
