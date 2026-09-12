"""
HistorySnooze Director - Single Part Chunk Renderer
Standalone CLI tool for distributed rendering in GitHub Actions Matrix or local runners.
Renders one 4K ASMR Part chunk (e.g. Part 01 -> chunk_part_01.mp4) with Ken Burns motion,
audio cue alignment, and sleep grading.
"""

import os
import sys
import glob
import re
import shutil
import argparse
import urllib.request
import tarfile
from pathlib import Path
from typing import List, Optional

import config
from chunk_renderer import render_part_chunk, is_chunk_valid

KEYFRAMES_RELEASE_URL = "https://github.com/triplex2909001/hsnooze.render/releases/download/v-assets-basho/keyframes_bundle.tar.gz"
AUDIO_RELEASE_URL = "https://github.com/triplex2909001/hsnooze.render/releases/download/v-assets-basho/audio_bundle.tar.gz"


def ensure_part_assets(project_root: str, part_index: int) -> tuple[str, List[str], Optional[str]]:
    """
    Ensures the audio WAV, keyframe images, and Part 01 cues exist for the given part.
    Downloads from GitHub Release CDN if not already present.
    """
    root_path = Path(project_root).resolve()
    media_dir = root_path / "02. Media Generation"
    audio_dir = media_dir / "audio"
    keyframes_dir = media_dir / "keyframes"

    audio_dir.mkdir(parents=True, exist_ok=True)
    keyframes_dir.mkdir(parents=True, exist_ok=True)

    part_prefix = f"beat_P{part_index:02d}_B"
    existing_kfs = [
        str(p) for p in sorted(list(keyframes_dir.glob(f"{part_prefix}*.jp*g")) + list(keyframes_dir.glob(f"{part_prefix}*.png")))
    ]

    target_beats = getattr(config, "TARGET_BEATS_PER_PART", 10)

    # 1. Fetch keyframes if deficient
    if len(existing_kfs) < target_beats:
        print(f"[ASSET] Part {part_index:02d} has {len(existing_kfs)}/{target_beats} keyframes. Fetching bundle from CDN...")
        bundle_tar = root_path / "keyframes_bundle.tar.gz"
        if not bundle_tar.exists():
            req = urllib.request.Request(KEYFRAMES_RELEASE_URL, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req) as resp, open(bundle_tar, "wb") as f_out:
                shutil.copyfileobj(resp, f_out)
        with tarfile.open(bundle_tar, "r:gz") as tar:
            tar.extractall(path=str(keyframes_dir))
        existing_kfs = [
            str(p) for p in sorted(list(keyframes_dir.glob(f"{part_prefix}*.jp*g")) + list(keyframes_dir.glob(f"{part_prefix}*.png")))
        ]
        print(f"✓ Extracted {len(existing_kfs)} keyframes for Part {part_index:02d}")

    # 2. Fetch audio if missing
    expected_wav_name = f"Part_{part_index:02d}.wav"
    audio_path = audio_dir / expected_wav_name
    if not audio_path.exists() or audio_path.stat().st_size < 1024 * 1024:
        # Check parent search
        found_wavs = list(root_path.glob(f"**/{expected_wav_name}"))
        if found_wavs and found_wavs[0].stat().st_size > 1024 * 1024:
            shutil.copy2(found_wavs[0], audio_path)
        else:
            print(f"[ASSET] {expected_wav_name} not found. Fetching audio bundle from CDN...")
            audio_tar = root_path / "audio_bundle.tar.gz"
            if not audio_tar.exists():
                req = urllib.request.Request(AUDIO_RELEASE_URL, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req) as resp, open(audio_tar, "wb") as f_out:
                    shutil.copyfileobj(resp, f_out)
            with tarfile.open(audio_tar, "r:gz") as tar:
                tar.extractall(path=str(audio_dir))

    if not audio_path.exists():
        raise FileNotFoundError(f"Audio file {expected_wav_name} not found in {audio_dir}")

    # 3. Part 01 cues
    cues_path = None
    if part_index == 1:
        candidate_cues = audio_dir / "Part_01_cues.json"
        if candidate_cues.exists():
            cues_path = str(candidate_cues)
        else:
            found_cues = list(root_path.glob("**/Part_01_cues.json"))
            if found_cues:
                cues_path = str(found_cues[0])

    return str(audio_path), existing_kfs, cues_path


def render_single_part(project_root: str, part_index: int, max_workers: int = 4) -> str:
    """
    Renders one Part chunk.
    """
    print("=" * 60)
    print(f"🚀 HistorySnooze Single Part Renderer: Part {part_index:02d}")
    print(f"📁 Project Root: {project_root}")
    print(f"⚡ Max Workers:  {max_workers}")
    print("=" * 60)

    audio_wav, beat_images, cues_json = ensure_part_assets(project_root, part_index)

    print(f"[SETUP] Audio:      {audio_wav} ({os.path.getsize(audio_wav) / 1024 / 1024:.2f} MB)")
    print(f"[SETUP] Keyframes:  {len(beat_images)} images")
    if cues_json:
        print(f"[SETUP] Cues JSON:  {cues_json}")

    target_beats = getattr(config, "TARGET_BEATS_PER_PART", 10)
    if len(beat_images) < target_beats:
        raise ValueError(f"Insufficient keyframes for Part {part_index:02d}: found {len(beat_images)}, expected >= {target_beats}")

    # Setup directories
    chunks_dir = os.path.join(project_root, "02. Media Generation", "chunks")
    output_dir = os.path.join("output")
    temp_dir = os.path.join(project_root, "02. Media Generation", f"temp_p{part_index:02d}")

    os.makedirs(chunks_dir, exist_ok=True)
    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(temp_dir, exist_ok=True)

    chunk_filename = f"chunk_part_{part_index:02d}.mp4"
    target_chunk_path = os.path.join(chunks_dir, chunk_filename)
    final_output_path = os.path.join(output_dir, chunk_filename)

    # Render part chunk
    rendered_chunk = render_part_chunk(
        part_index=part_index,
        audio_wav_path=audio_wav,
        beat_images=beat_images,
        output_chunk_path=target_chunk_path,
        temp_dir=temp_dir,
        cues_json_path=cues_json,
        max_workers=max_workers,
        force_cpu=True
    )

    if not is_chunk_valid(rendered_chunk):
        raise RuntimeError(f"Rendered chunk {rendered_chunk} failed validation!")

    # Copy to output/
    if os.path.abspath(rendered_chunk) != os.path.abspath(final_output_path):
        shutil.copy2(rendered_chunk, final_output_path)

    print("=" * 60)
    print(f"🎉 PART {part_index:02d} RENDER COMPLETE!")
    print(f"📦 Output Chunk: {final_output_path} ({os.path.getsize(final_output_path) / 1024 / 1024:.1f} MB)")
    print("=" * 60)

    return final_output_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Render a single 4K ASMR Part Chunk")
    parser.add_argument("project_root", nargs="?", default="./project_assets", help="Path to project assets")
    parser.add_argument("part_index", type=int, help="Part index (1..15)")
    parser.add_argument("max_workers", nargs="?", type=int, default=4, help="Max FFmpeg parallel workers")

    args = parser.parse_args()

    try:
        render_single_part(args.project_root, args.part_index, args.max_workers)
        sys.exit(0)
    except Exception as err:
        print(f"❌ Error rendering Part {args.part_index}: {err}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
