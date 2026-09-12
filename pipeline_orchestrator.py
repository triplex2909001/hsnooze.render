"""
HistorySnooze Director - Main Pipeline Orchestrator & State Machine
Version: 1.3.0 (100% Online Serverless & Colab CLI Edition)
Coordinates end-to-end execution across all 8 Status stages:
Proposed -> Pending -> Script -> Voiceover -> Image -> Video -> Ready -> Done.
Enforces Gatekeepers GK1 through GK7, with Image_Mode branching (Automatic vs Manual)
and 100% Online Cloud Execution (GitHub Actions Matrix or Colab CLI).
Supports 150-160 high-density beat generation and audits (GK3 & GK6).
"""

import os
import sys
import glob
import re
from typing import Dict, List, Optional, Any
from chunk_renderer import render_part_chunk
from master_assembler import assemble_master_video
import config

try:
    from voice_chunk_engine import ChunkVoiceoverPipeline, audit_wav_acoustic
except ImportError:
    ChunkVoiceoverPipeline = None
    audit_wav_acoustic = None

try:
    from prompt_engine import validate_prompt
except ImportError:
    _scripting_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "hsnooze.scripting"))
    if os.path.isdir(_scripting_dir) and _scripting_dir not in sys.path:
        sys.path.insert(0, _scripting_dir)
    try:
        from prompt_engine import validate_prompt
    except ImportError:
        validate_prompt = None


def audit_gk3_prompts(project_root: str, prompts_file_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Gatekeeper GK3 Script & Visual Prompts Auditor:
    Verifies that:
    1. combined_imageprompts.txt exists.
    2. Total prompt count is >= config.EXPECTED_MIN_BEATS (150) and <= config.EXPECTED_MAX_BEATS (160).
    3. Each of the 15 parts contains at least config.TARGET_BEATS_PER_PART (10) beats.
    4. Each prompt adheres to syntax rules (valid beat format).
    """
    if prompts_file_path is None:
        candidates = [
            os.path.join(project_root, "01. Pre-Production", "combined_imageprompts.txt"),
            os.path.join(project_root, "01. Preproduction", "combined_imageprompts.txt"),
            os.path.join(project_root, "combined_imageprompts.txt"),
            os.path.join(project_root, "02. Media Generation", "combined_imageprompts.txt"),
            os.path.join(project_root, "02. Media Generation", "combined", "combined_imageprompts.txt"),
        ]
        for c in candidates:
            if os.path.exists(c):
                prompts_file_path = c
                break
                
    total_parts = getattr(config, "TOTAL_PARTS", 15)
    min_beats = getattr(config, "EXPECTED_MIN_BEATS", 150)
    max_beats = getattr(config, "EXPECTED_MAX_BEATS", 160)
    target_per_part = getattr(config, "TARGET_BEATS_PER_PART", 10)

    if not prompts_file_path or not os.path.exists(prompts_file_path):
        return {
            "passed_gk3": False,
            "total_count": 0,
            "part_counts": {p: 0 for p in range(1, total_parts + 1)},
            "deficient_parts": list(range(1, total_parts + 1)),
            "prompts_file_path": prompts_file_path,
            "details": [f"combined_imageprompts.txt not found in {project_root}"]
        }
        
    with open(prompts_file_path, "r", encoding="utf-8") as f:
        content = f.read()
        
    part_beats = {p: [] for p in range(1, total_parts + 1)}
    total_beats = 0
    details = []
    
    beat_pattern = re.compile(r"^beat_P(\d{2})_B(\d{2})(?:\.jpg|\.png|\.jpeg)?\s*:\s*(.*)$", re.IGNORECASE)
    
    for line_num, raw_line in enumerate(content.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
            
        m = beat_pattern.match(line)
        if m:
            part_idx = int(m.group(1))
            beat_idx = int(m.group(2))
            prompt_text = m.group(3).strip()
            total_beats += 1
            if part_idx in part_beats:
                part_beats[part_idx].append({
                    "beat_idx": beat_idx,
                    "prompt": prompt_text,
                    "line_num": line_num
                })
            else:
                details.append(f"Line {line_num}: Part {part_idx:02d} outside expected range 1..{total_parts}")

            # Prompt syntax & quality validation via prompt_engine.validate_prompt
            if validate_prompt is not None:
                val_res = validate_prompt(prompt_text)
                if not val_res.get("is_valid", False):
                    issues = val_res.get("issues", [])
                    if issues:
                        for issue in issues:
                            details.append(
                                f"Line {line_num} (Part {part_idx:02d} Beat {beat_idx:02d}): {issue}"
                            )
                    else:
                        details.append(
                            f"Line {line_num} (Part {part_idx:02d} Beat {beat_idx:02d}): Prompt validation failed"
                        )
            else:
                details.append(
                    f"Line {line_num} (Part {part_idx:02d} Beat {beat_idx:02d}): prompt_engine.validate_prompt is unavailable"
                )
        elif ":" in line and line.lower().startswith("beat_"):
            details.append(f"Line {line_num}: Malformed beat line format: '{line[:50]}'")
            
    has_valid_total = (min_beats <= total_beats <= max_beats)
    if not has_valid_total:
        details.append(
            f"Total prompt count {total_beats} outside required range [{min_beats}, {max_beats}]"
        )
        
    part_counts = {p: len(beats) for p, beats in part_beats.items()}
    deficient_parts = []
    for p in range(1, total_parts + 1):
        cnt = part_counts[p]
        if cnt < target_per_part:
            deficient_parts.append(p)
            details.append(
                f"Part {p:02d} has {cnt} prompts, expected at least {target_per_part}"
            )
            
    passed_gk3 = has_valid_total and (len(deficient_parts) == 0) and (len(details) == 0)
    
    return {
        "passed_gk3": passed_gk3,
        "total_count": total_beats,
        "part_counts": part_counts,
        "deficient_parts": deficient_parts,
        "prompts_file_path": prompts_file_path,
        "details": details
    }


def audit_gk4_audio(project_root: str) -> Dict[str, Any]:
    """
    Gatekeeper GK4 Acoustic Deep Auditor:
    Verifies that exactly 15 WAV files exist, each with size >= 10 KB and valid acoustic parameters.
    """
    audio_dir = os.path.join(project_root, "02. Media Generation", "audio")
    wav_files = sorted(glob.glob(os.path.join(audio_dir, "Part_*.wav")))
    
    passed_all = True
    details = []
    if len(wav_files) != 15:
        passed_all = False
        details.append(f"Expected 15 WAV files, found {len(wav_files)}")
        
    for wav_path in wav_files:
        if audit_wav_acoustic:
            valid, msg = audit_wav_acoustic(wav_path, min_size_kb=config.GK4_MIN_WAV_SIZE_KB, min_rms=config.GK4_RMS_THRESHOLD)
            if not valid:
                passed_all = False
                details.append(f"{os.path.basename(wav_path)} failed: {msg}")
        else:
            size_kb = os.path.getsize(wav_path) / 1024.0
            if size_kb < config.GK4_MIN_WAV_SIZE_KB:
                passed_all = False
                details.append(f"{os.path.basename(wav_path)} size too small: {size_kb:.1f} KB")
                
    return {
        "passed_gk4": passed_all,
        "count": len(wav_files),
        "details": details
    }


def audit_gk6_assets(project_root: str) -> Dict[str, Any]:
    """
    Gatekeeper GK6 PreAssembly-Asset Auditor:
    Verifies that:
    1. Exactly 15 WAV audio files exist (Part_01.wav .. Part_15.wav).
    2. At least config.EXPECTED_MIN_BEATS (150) keyframe images exist.
    3. Each part contains at least config.TARGET_BEATS_PER_PART (10) keyframes.
    """
    audio_candidates = [
        os.path.join(project_root, "02. Media Generation", "audio"),
        os.path.join(project_root, "audio"),
    ]
    audio_dir = next((c for c in audio_candidates if os.path.isdir(c) and glob.glob(os.path.join(c, "Part_*.wav"))), audio_candidates[0])

    keyframes_candidates = [
        os.path.join(project_root, "02. Media Generation", "keyframes"),
        os.path.join(project_root, "keyframes"),
        os.path.join(project_root, "hsnooze.render", "keyframes"),
    ]
    keyframes_dir = next((c for c in keyframes_candidates if os.path.isdir(c) and glob.glob(os.path.join(c, "beat_*.*"))), keyframes_candidates[0])
    
    total_parts = getattr(config, "TOTAL_PARTS", 15)
    min_beats = getattr(config, "EXPECTED_MIN_BEATS", 150)
    target_per_part = getattr(config, "TARGET_BEATS_PER_PART", 10)
    
    wav_files = sorted(glob.glob(os.path.join(audio_dir, "Part_*.wav")))
    raw_img_files = sorted(
        glob.glob(os.path.join(keyframes_dir, "beat_*.jpg")) + 
        glob.glob(os.path.join(keyframes_dir, "beat_*.jpeg")) +
        glob.glob(os.path.join(keyframes_dir, "beat_*.png"))
    )
    # Deduplicate stems so dual extensions (.jpg and .jpeg) for the same beat do not double-count
    seen_stems = set()
    img_files = []
    for f in raw_img_files:
        stem = os.path.splitext(os.path.basename(f))[0]
        if stem not in seen_stems:
            seen_stems.add(stem)
            img_files.append(f)
    
    details = []
    has_15_audio_count = (len(wav_files) == total_parts)
    if not has_15_audio_count:
        details.append(f"Expected {total_parts} WAV files, found {len(wav_files)}")

    # Enforce individual audio part checks (Part_01.wav through Part_15.wav)
    missing_audio_parts = []
    for part_idx in range(1, total_parts + 1):
        expected_wav = os.path.join(audio_dir, f"Part_{part_idx:02d}.wav")
        if not os.path.isfile(expected_wav):
            missing_audio_parts.append(part_idx)
            details.append(f"Missing required audio part: Part_{part_idx:02d}.wav")

    has_all_audio = has_15_audio_count and (len(missing_audio_parts) == 0)
        
    has_min_images = (len(img_files) >= min_beats)
    if not has_min_images:
        details.append(f"Expected at least {min_beats} images, found {len(img_files)}")
        
    # Per-part distribution check
    part_counts = {}
    deficient_parts = []
    for part_idx in range(1, total_parts + 1):
        prefix = f"beat_P{part_idx:02d}_"
        part_imgs = [f for f in img_files if prefix in os.path.basename(f)]
        cnt = len(part_imgs)
        part_counts[part_idx] = cnt
        if cnt < target_per_part:
            deficient_parts.append(part_idx)
            details.append(
                f"Part {part_idx:02d} has {cnt} keyframes, expected at least {target_per_part}"
            )
            
    passed_gk6 = has_all_audio and has_min_images and (len(deficient_parts) == 0) and (len(details) == 0)
    
    return {
        "passed_gk6": passed_gk6,
        "audio_count": len(wav_files),
        "missing_audio_parts": missing_audio_parts,
        "image_count": len(img_files),
        "part_counts": part_counts,
        "deficient_parts": deficient_parts,
        "wav_files": wav_files,
        "img_files": img_files,
        "details": details
    }


def audit_gk7_master(project_root: str, master_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Gatekeeper GK7 Master Concatenation & Duration Auditor:
    Verifies that master_final_90min.mp4 exists, duration >= 80.0 minutes, and size > 500 MB.
    """
    import subprocess
    if not master_path:
        candidates = [
            os.path.join(project_root, "03. Final Production", "master_final_90min.mp4"),
            os.path.join(project_root, "02. Media Generation", "video", "master_final_90min.mp4"),
            os.path.join(project_root, "hsnooze.render", "output", "master_final_90min.mp4"),
            os.path.join(project_root, "master_final_90min.mp4")
        ]
        for c in candidates:
            if os.path.exists(c):
                master_path = c
                break
        if not master_path:
            master_path = candidates[0]

    if not os.path.exists(master_path):
        return {
            "passed_gk7": False,
            "output_path": master_path,
            "duration_minutes": 0.0,
            "duration_seconds": 0.0,
            "file_size_gb": 0.0,
            "details": [f"Master file not found: {master_path}"]
        }

    try:
        cmd_probe = [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration:format=size",
            "-of", "default=noprint_wrappers=1:nokey=1",
            master_path
        ]
        res = subprocess.run(cmd_probe, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        lines = res.stdout.strip().split("\n")
        duration_sec = float(lines[0])
        size_bytes = int(lines[1])
        duration_min = duration_sec / 60.0

        min_dur = getattr(config, "GK7_MIN_VIDEO_DURATION_MIN", 80.0)
        passed_gk7 = (duration_min >= min_dur) and (size_bytes > 500 * 1024 * 1024)

        return {
            "output_path": master_path,
            "duration_minutes": round(duration_min, 2),
            "duration_seconds": round(duration_sec, 2),
            "file_size_gb": round(size_bytes / (1024 ** 3), 2),
            "passed_gk7": passed_gk7
        }
    except Exception as e:
        return {
            "passed_gk7": False,
            "output_path": master_path,
            "duration_minutes": 0.0,
            "duration_seconds": 0.0,
            "file_size_gb": 0.0,
            "details": [f"ffprobe probe error: {str(e)}"]
        }


def handle_image_generation_stage(project_root: str, image_mode: str) -> str:
    """
    Handles Image generation branching based on Column I (Image_Mode):
    - If Automatic: Triggers automated ImageFX bot reading combined_imageprompts.txt.
    - If Manual: Pauses and instructs human to drop images into keyframes/ and manually change Status to 'Image'.
    """
    keyframes_dir = os.path.join(project_root, "02. Media Generation", "keyframes")
    img_files = (
        glob.glob(os.path.join(keyframes_dir, "beat_*.jpg")) +
        glob.glob(os.path.join(keyframes_dir, "beat_*.jpeg")) +
        glob.glob(os.path.join(keyframes_dir, "beat_*.png"))
    )
    
    if image_mode.lower() == "automatic":
        print("[ORCHESTRATOR] Image_Mode is 'Automatic'. Initiating ImageFX 4K generation...")
        return "Image"
    else:
        print("[ORCHESTRATOR] Image_Mode is 'Manual'.")
        if len(img_files) >= config.EXPECTED_MIN_BEATS:
            print(f"✅ Found {len(img_files)} keyframes uploaded manually. Proceeding to 'Image'.")
            return "Image"
        else:
            print(f"⏸️ [MANUAL WAIT] Currently found {len(img_files)}/{config.EXPECTED_MIN_BEATS} keyframes in {keyframes_dir}.")
            print("👉 Please open 'combined_imageprompts.txt', generate 4K images, and drop them into 'keyframes/'.")
            print("👉 Once uploaded, change Status on Google Sheet from 'Voiceover' to 'Image' to resume.")
            return "Voiceover"


def run_project_assembly(project_root: str, image_mode: str = "Automatic", max_workers: int = 8) -> Dict[str, Any]:
    """
    Runs video assembly once Status reaches 'Image':
    1. GK6 Audit
    2. Render 15 Chunk Parts (Slow Ken Burns ASMR with Smart Delta Restart)
    3. Assemble Master Video (Stream Copy with 5s Silences)
    4. GK7 Audit -> Transitions to 'Ready'
    """
    print(f"==================================================")
    print(f"Starting HistorySnooze Director Pipeline for:")
    print(f"📁 {project_root}")
    print(f"🎨 Image Mode: {image_mode}")
    print(f"==================================================")
    
    # 1. GK6 Audit
    gk6_result = audit_gk6_assets(project_root)
    print(f"[GK6 AUDIT] Audio: {gk6_result['audio_count']}/15, Images: {gk6_result['image_count']}/{config.EXPECTED_MIN_BEATS}")
    if not gk6_result["passed_gk6"]:
        details_str = "; ".join(gk6_result.get("details", []))
        raise ValueError(
            f"GK6 Audit Failed: Need 15 WAVs (found {gk6_result['audio_count']}) "
            f"and at least {config.EXPECTED_MIN_BEATS} images (found {gk6_result['image_count']}). Details: {details_str}"
        )
    print("✅ Gatekeeper GK6 PASSED.")
    
    # 2. Render 15 Chunks
    video_dir = os.path.join(project_root, "02. Media Generation", "video")
    chunks_dir = os.path.join(project_root, "02. Media Generation", "chunks")
    render_output_dir = os.path.join(project_root, "hsnooze.render", "output")
    temp_dir = os.path.join(project_root, "02. Media Generation", "temp")
    
    os.makedirs(video_dir, exist_ok=True)
    os.makedirs(chunks_dir, exist_ok=True)
    os.makedirs(render_output_dir, exist_ok=True)
    os.makedirs(temp_dir, exist_ok=True)
    
    chunk_paths = []
    for part_idx in range(1, 16):
        audio_file = os.path.join(project_root, "02. Media Generation", "audio", f"Part_{part_idx:02d}.wav")
        if not os.path.exists(audio_file):
            alt_audio = os.path.join(project_root, "audio", f"Part_{part_idx:02d}.wav")
            if os.path.exists(alt_audio):
                audio_file = alt_audio
        
        # Deduplicate keyframes per beat (handling dual .jpg and .jpeg files)
        part_images_map = {}
        for kf_dir in [
            os.path.join(project_root, "02. Media Generation", "keyframes"),
            os.path.join(project_root, "keyframes"),
            os.path.join(project_root, "hsnooze.render", "keyframes")
        ]:
            if not os.path.isdir(kf_dir):
                continue
            for f in sorted(glob.glob(os.path.join(kf_dir, f"beat_P{part_idx:02d}_B*.*"))):
                stem = os.path.splitext(os.path.basename(f))[0]
                if stem not in part_images_map:
                    part_images_map[stem] = f
                    
        part_images = [part_images_map[k] for k in sorted(part_images_map.keys())]
        
        if not part_images:
            raise FileNotFoundError(f"No keyframe images found for Part {part_idx:02d}.")
            
        chunk_mp4 = render_part_chunk(
            part_index=part_idx,
            audio_wav_path=audio_file,
            beat_images=part_images,
            output_dir=video_dir,
            temp_dir=temp_dir,
            max_workers=max_workers
        )
        chunk_paths.append(chunk_mp4)
        
        # Mirror chunk to chunks_dir and hsnooze.render/output/
        chunk_name = os.path.basename(chunk_mp4)
        for target_dir in [chunks_dir, render_output_dir]:
            target_path = os.path.join(target_dir, chunk_name)
            if os.path.abspath(target_path) != os.path.abspath(chunk_mp4):
                if not os.path.exists(target_path) or os.path.getsize(target_path) != os.path.getsize(chunk_mp4):
                    try:
                        import shutil
                        shutil.copy2(chunk_mp4, target_path)
                    except Exception as e:
                        print(f"Warning: Failed to mirror {chunk_name} to {target_dir}: {e}")
        
    # 3. Master Assembly
    final_dir = os.path.join(project_root, "03. Final Production")
    master_mp4 = os.path.join(final_dir, "master_final_90min.mp4")
    
    master_result = assemble_master_video(
        chunk_paths=chunk_paths,
        output_master_path=master_mp4,
        temp_dir=temp_dir
    )
    
    # Mirror master video to video_dir and render_output_dir
    for target_dir in [video_dir, render_output_dir]:
        target_path = os.path.join(target_dir, "master_final_90min.mp4")
        if os.path.abspath(target_path) != os.path.abspath(master_mp4):
            if not os.path.exists(target_path) or os.path.getsize(target_path) != os.path.getsize(master_mp4):
                try:
                    import shutil
                    shutil.copy2(master_mp4, target_path)
                except Exception as e:
                    print(f"Warning: Failed to mirror master_final_90min.mp4 to {target_dir}: {e}")
    
    print(f"==================================================")
    print(f"🎉 Pipeline Execution Complete! Status -> READY")
    print(f"Output Master: {master_mp4}")
    print(f"Duration: {master_result['duration_minutes']} minutes (GK7: {'PASSED' if master_result['passed_gk7'] else 'FAILED'})")
    print(f"Size: {master_result['file_size_gb']} GB")
    print(f"==================================================")
    
    return master_result


if __name__ == "__main__":
    if len(sys.argv) > 1:
        proj_path = sys.argv[1]
        mode = sys.argv[2] if len(sys.argv) > 2 else "Automatic"
        workers = int(sys.argv[3]) if len(sys.argv) > 3 else 8
        run_project_assembly(proj_path, mode, max_workers=workers)
    else:
        print("Usage: python3 pipeline_orchestrator.py <path_to_project_root> [Automatic|Manual] [max_workers]")

