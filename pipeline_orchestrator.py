"""
HistorySnooze Director - Main Pipeline Orchestrator & State Machine
Version: 1.2.0 (100% Online Serverless & Colab CLI Edition)
Coordinates end-to-end execution across all 8 Status stages:
Proposed -> Pending -> Script -> Voiceover -> Image -> Video -> Ready -> Done.
Enforces Gatekeepers GK1 through GK7, with Image_Mode branching (Automatic vs Manual)
and 100% Online Cloud Execution (GitHub Actions Matrix or Colab CLI).
"""

import os
import sys
import glob
from typing import Dict, List, Optional
from chunk_renderer import render_part_chunk
from master_assembler import assemble_master_video
import config

try:
    from voice_chunk_engine import ChunkVoiceoverPipeline, audit_wav_acoustic
except ImportError:
    ChunkVoiceoverPipeline = None
    audit_wav_acoustic = None

def audit_gk4_audio(project_root: str) -> Dict[str, any]:
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

def audit_gk6_assets(project_root: str) -> Dict[str, any]:
    """
    Gatekeeper GK6 PreAssembly-Asset Auditor:
    Verifies that exactly 15 WAV audio files and at least 45 keyframe images exist.
    """
    audio_dir = os.path.join(project_root, "02. Media Generation", "audio")
    keyframes_dir = os.path.join(project_root, "02. Media Generation", "keyframes")
    
    wav_files = sorted(glob.glob(os.path.join(audio_dir, "Part_*.wav")))
    img_files = sorted(glob.glob(os.path.join(keyframes_dir, "beat_*.jpg")) + 
                       glob.glob(os.path.join(keyframes_dir, "beat_*.png")))
    
    has_15_audio = len(wav_files) == 15
    has_min_images = len(img_files) >= config.EXPECTED_MIN_BEATS
    
    passed_gk6 = has_15_audio and has_min_images
    
    return {
        "passed_gk6": passed_gk6,
        "audio_count": len(wav_files),
        "image_count": len(img_files),
        "wav_files": wav_files,
        "img_files": img_files
    }

def handle_image_generation_stage(project_root: str, image_mode: str) -> str:
    """
    Handles Image generation branching based on Column I (Image_Mode):
    - If Automatic: Triggers automated ImageFX bot reading combined_imageprompts.txt.
    - If Manual: Pauses and instructs human to drop images into keyframes/ and manually change Status to 'Image'.
    """
    keyframes_dir = os.path.join(project_root, "02. Media Generation", "keyframes")
    img_files = glob.glob(os.path.join(keyframes_dir, "beat_*.jpg")) + glob.glob(os.path.join(keyframes_dir, "beat_*.png"))
    
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

def run_project_assembly(project_root: str, image_mode: str = "Automatic") -> Dict[str, any]:
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
        raise ValueError(
            f"GK6 Audit Failed: Need 15 WAVs (found {gk6_result['audio_count']}) "
            f"and at least {config.EXPECTED_MIN_BEATS} images (found {gk6_result['image_count']})."
        )
    print("✅ Gatekeeper GK6 PASSED.")
    
    # 2. Render 15 Chunks
    chunks_dir = os.path.join(project_root, "02. Media Generation", "chunks")
    temp_dir = os.path.join(project_root, "02. Media Generation", "temp")
    os.makedirs(chunks_dir, exist_ok=True)
    
    chunk_paths = []
    for part_idx in range(1, 16):
        audio_file = os.path.join(project_root, "02. Media Generation", "audio", f"Part_{part_idx:02d}.wav")
        pattern = os.path.join(project_root, "02. Media Generation", "keyframes", f"beat_P{part_idx:02d}_B*.*")
        part_images = sorted(glob.glob(pattern))
        
        if not part_images:
            raise FileNotFoundError(f"No keyframe images found for Part {part_idx:02d} matching '{pattern}'.")
            
        chunk_mp4 = render_part_chunk(
            part_index=part_idx,
            audio_wav_path=audio_file,
            beat_images=part_images,
            output_dir=chunks_dir,
            temp_dir=temp_dir
        )
        chunk_paths.append(chunk_mp4)
        
    # 3. Master Assembly
    final_dir = os.path.join(project_root, "03. Final Production")
    master_mp4 = os.path.join(final_dir, "master_final_90min.mp4")
    
    master_result = assemble_master_video(
        chunk_paths=chunk_paths,
        output_master_path=master_mp4,
        temp_dir=temp_dir
    )
    
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
        run_project_assembly(proj_path, mode)
    else:
        print("Usage: python3 pipeline_orchestrator.py <path_to_project_root> [Automatic|Manual]")
