"""
HistorySnooze Director - Single Part Chunk Renderer
Standalone CLI tool for distributed rendering in GitHub Actions Matrix or local runners.
Rule <= 150 lines compliant facade.
"""

import argparse
import os
import re
import sys
from pathlib import Path
from typing import List, Optional

_DIR = str(Path(__file__).resolve().parent)
if _DIR not in sys.path:
    sys.path.insert(0, _DIR)

from tar_archive_guard import SecurityError, safe_extract_tarball
from part_asset_resolver import ensure_part_assets

import config
from chunk_renderer import render_part_chunk, is_chunk_valid


def render_single_part(
    project_root: str,
    part_index: int,
    max_workers: int = 4,
    force_cpu: bool = False
) -> str:
    """Renders one Part chunk."""
    print("=" * 60)
    print(f"🚀 HistorySnooze Single Part Renderer: Part {part_index:02d}")
    print(f"📁 Project Root: {project_root}")
    print(f"⚡ Max Workers:  {max_workers}")
    print(f"🖥️ Force CPU:    {force_cpu}")
    print("=" * 60)

    audio_wav, beat_images, cues_json = ensure_part_assets(project_root, part_index)

    print(f"[SETUP] Audio:      {audio_wav} ({os.path.getsize(audio_wav) / 1024 / 1024:.2f} MB)")
    print(f"[SETUP] Keyframes:  {len(beat_images)} images")
    if cues_json:
        print(f"[SETUP] Cues JSON:  {cues_json}")

    target_beats = getattr(config, "TARGET_BEATS_PER_PART", 10) if config else 10
    if len(beat_images) < target_beats:
        raise ValueError(f"Insufficient keyframes for Part {part_index:02d}: found {len(beat_images)}, expected >= {target_beats}")

    # GK6 Parity: Cover Image Verification (HITL) on Part 01
    if part_index == 1:
        has_cover = any(bool(re.search(r"beat_P0?1_B0?1(?:\.|$|_)", img)) for img in beat_images)
        if not has_cover:
            print("=" * 60)
            print("⏸️ [HUMAN-IN-THE-LOOP CHECKPOINT: COVER MISSING]")
            print("👉 Part 01 Beat 01 Cover image ('beat_P01_B01.*') is missing from keyframes!")
            print("👉 Please upload your custom Cover image into '02. Media Generation/keyframes/'")
            print("   and change Status on Google Sheet to 'Image' before rendering.")
            print("=" * 60)
            raise FileNotFoundError("Manual Cover image 'beat_P01_B01' is required before rendering Part 01.")

    chunks_dir = os.path.join(project_root, "02. Media Generation", "chunks")
    output_dir = os.path.join("output")
    temp_dir = os.path.join(project_root, "02. Media Generation", f"temp_p{part_index:02d}")

    os.makedirs(chunks_dir, exist_ok=True)
    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(temp_dir, exist_ok=True)

    rendered_chunk = render_part_chunk(
        part_index=part_index,
        audio_wav_path=audio_wav,
        beat_images=beat_images,
        output_dir=chunks_dir,
        temp_dir=temp_dir,
        cues_json_path=cues_json,
        force_cpu=force_cpu,
        max_workers=max_workers
    )

    if not is_chunk_valid(rendered_chunk):
        raise RuntimeError(f"Rendered chunk {rendered_chunk} failed validation!")

    from pipeline_orchestrator import link_or_copy_artifact
    final_output_path = link_or_copy_artifact(rendered_chunk, output_dir)

    file_size_mb = (os.path.getsize(final_output_path) / 1024 / 1024) if os.path.exists(final_output_path) else 0.0
    print("=" * 60)
    print(f"🎉 PART {part_index:02d} RENDER COMPLETE!")
    print(f"📦 Output Chunk: {final_output_path} ({file_size_mb:.1f} MB)")
    print("=" * 60)
    return final_output_path


# Operational Alias for parity
render_part = render_single_part


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Render a single 4K ASMR Part Chunk")
    parser.add_argument("project_root", nargs="?", default="./project_assets", help="Path to project assets")
    parser.add_argument("part_index", type=int, help="Part index (1..15)")
    parser.add_argument("max_workers", nargs="?", type=int, default=4, help="Max FFmpeg parallel workers")
    parser.add_argument("--cpu", action="store_true", help="Force CPU libx264 encoding")
    args = parser.parse_args()

    try:
        render_single_part(args.project_root, args.part_index, args.max_workers, force_cpu=args.cpu)
        sys.exit(0)
    except Exception as err:
        print(f"❌ Error rendering Part {args.part_index}: {err}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
