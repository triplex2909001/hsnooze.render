"""
HistorySnooze Director - Beat Aligner Module
Calculates timestamp durations for each visual beat within a part's voiceover.
Each visual beat extends between 75 and 90 seconds to match the slow, meditative pacing.
"""

import json
import os
import subprocess
from typing import List, Dict, Optional

def get_audio_duration(audio_wav_path: str) -> float:
    """
    Retrieves the exact duration of a WAV file in seconds using ffprobe.
    """
    if not os.path.exists(audio_wav_path):
        raise FileNotFoundError(f"Audio file not found: {audio_wav_path}")
        
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        audio_wav_path
    ]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
    return float(result.stdout.strip())

def align_part_beats(
    part_index: int,
    audio_wav_path: str,
    beat_images: List[str],
    output_json_path: Optional[str] = None
) -> Dict[str, any]:
    """
    Distributes the total part audio duration equally across the beat images.
    Formula: Beat Duration = Total Audio Duration / Number of Beats.
    """
    total_duration = get_audio_duration(audio_wav_path)
    num_beats = len(beat_images)
    
    if num_beats == 0:
        raise ValueError(f"No beat images provided for Part {part_index}.")
        
    base_duration = total_duration / num_beats
    beats_data = []
    
    current_time = 0.0
    for idx, img_path in enumerate(beat_images, start=1):
        # Assign duration with slight float precision balance for the final beat
        dur = total_duration - current_time if idx == num_beats else round(base_duration, 3)
        beat_info = {
            "part_index": part_index,
            "beat_index": idx,
            "beat_id": f"P{part_index:02d}_B{idx:02d}",
            "image_path": img_path,
            "start_time": round(current_time, 3),
            "end_time": round(current_time + dur, 3),
            "duration": dur
        }
        beats_data.append(beat_info)
        current_time += dur
        
    result = {
        "part_index": part_index,
        "audio_path": audio_wav_path,
        "total_duration": total_duration,
        "num_beats": num_beats,
        "beats": beats_data
    }
    
    if output_json_path:
        os.makedirs(os.path.dirname(output_json_path), exist_ok=True)
        with open(output_json_path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
            
    return result
