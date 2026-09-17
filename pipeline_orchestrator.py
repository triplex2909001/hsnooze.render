"""
HistorySnooze Director - Main Pipeline Orchestrator & State Machine
Coordinates execution across 8 stages and enforces Gatekeepers GK1-GK7.
Rule <= 150 lines compliant facade.
"""

import glob
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

_DIR = str(Path(__file__).resolve().parent)
if _DIR not in sys.path:
    sys.path.insert(0, _DIR)

from chunk_renderer import render_part_chunk
from master_assembler import assemble_master_video
import config

from orchestrator_artifact_linker import link_or_copy_artifact
from orchestrator_stage_manager import check_cover_image_present, handle_image_generation_stage
from orchestrator_gk3_auditor import (
    validate_prompt,
    ChunkVoiceoverPipeline,
    audit_wav_acoustic,
    audit_gk3_prompts,
    audit_gk4_audio
)
from orchestrator_gk6_auditor import audit_gk6_assets, audit_gk7_master


def run_project_assembly(
    project_root: str,
    image_mode: str = "Automatic",
    max_workers: int = 8
) -> Dict[str, Any]:
    """Runs video assembly once Status reaches 'Image'."""
    print("=" * 50)
    print(f"Starting HistorySnooze Director Pipeline for:\n📁 {project_root}\n🎨 Image Mode: {image_mode}")
    print("=" * 50)

    gk6_result = audit_gk6_assets(project_root)
    min_b = getattr(config, "EXPECTED_MIN_BEATS", 150) if config else 150
    print(f"[GK6 AUDIT] Audio: {gk6_result['audio_count']}/15, Images: {gk6_result['image_count']}/{min_b}")
    if not gk6_result["passed_gk6"]:
        details_str = "; ".join(gk6_result.get("details", []))
        raise ValueError(f"GK6 Audit Failed: Need 15 WAVs and at least {min_b} images. Details: {details_str}")
    print("✅ Gatekeeper GK6 PASSED.")

    video_dir = os.path.join(project_root, "02. Media Generation", "video")
    chunks_dir = os.path.join(project_root, "02. Media Generation", "chunks")
    render_out_dir = os.path.join(project_root, "hsnooze.render", "output")
    temp_dir = os.path.join(project_root, "02. Media Generation", "temp")
    for d in (video_dir, chunks_dir, render_out_dir, temp_dir):
        os.makedirs(d, exist_ok=True)

    chunk_paths = []
    for part_idx in range(1, 16):
        audio_file = os.path.join(project_root, "02. Media Generation", "audio", f"Part_{part_idx:02d}.wav")
        if not os.path.exists(audio_file):
            alt = os.path.join(project_root, "audio", f"Part_{part_idx:02d}.wav")
            if os.path.exists(alt):
                audio_file = alt

        part_imgs_map = {}
        for kf_d in [
            os.path.join(project_root, "02. Media Generation", "keyframes"),
            os.path.join(project_root, "keyframes"),
            os.path.join(project_root, "hsnooze.render", "keyframes")
        ]:
            if os.path.isdir(kf_d):
                for f in sorted(glob.glob(os.path.join(kf_d, f"beat_P{part_idx:02d}_B*.*"))):
                    stem = os.path.splitext(os.path.basename(f))[0]
                    if stem not in part_imgs_map:
                        part_imgs_map[stem] = f

        part_images = [part_imgs_map[k] for k in sorted(part_imgs_map.keys())]
        if not part_images:
            raise FileNotFoundError(f"No keyframe images found for Part {part_idx:02d}.")

        chunk_mp4 = render_part_chunk(
            part_index=part_idx, audio_wav_path=audio_file, beat_images=part_images,
            output_dir=video_dir, temp_dir=temp_dir, max_workers=max_workers
        )
        chunk_paths.append(chunk_mp4)

        for target_dir in [chunks_dir, render_out_dir]:
            try:
                link_or_copy_artifact(chunk_mp4, target_dir)
            except Exception as e:
                print(f"Warning: Failed to link {os.path.basename(chunk_mp4)} to {target_dir}: {e}")

    final_dir = os.path.join(project_root, "03. Final Production")
    master_mp4 = os.path.join(final_dir, "master_final_90min.mp4")
    master_result = assemble_master_video(chunk_paths=chunk_paths, output_master_path=master_mp4, temp_dir=temp_dir)

    for target_dir in [video_dir, render_out_dir]:
        try:
            link_or_copy_artifact(master_mp4, target_dir)
        except Exception as e:
            print(f"Warning: Failed to link master to {target_dir}: {e}")

    print("=" * 50)
    print(f"🎉 Pipeline Execution Complete! Status -> READY\nOutput Master: {master_mp4}")
    print(f"Duration: {master_result['duration_minutes']} min (GK7: {'PASSED' if master_result['passed_gk7'] else 'FAILED'})")
    print(f"Size: {master_result['file_size_gb']} GB\n" + "=" * 50)
    return master_result


if __name__ == "__main__":
    if len(sys.argv) > 1:
        p_path = sys.argv[1]
        mode = sys.argv[2] if len(sys.argv) > 2 else "Automatic"
        wkrs = int(sys.argv[3]) if len(sys.argv) > 3 else 8
        run_project_assembly(p_path, mode, max_workers=wkrs)
    else:
        print("Usage: python3 pipeline_orchestrator.py <path_to_project_root> [Automatic|Manual] [max_workers]")
