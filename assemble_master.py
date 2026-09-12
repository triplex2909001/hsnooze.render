"""
HistorySnooze Director - Master Concatenation Runner
Assembles 15 Part chunks into the final ~90-minute 4K ASMR documentary.
Uses FFmpeg Stream Copy (-c copy) for rapid concatenation in under 30 seconds.
Enforces Gatekeeper GK7 (Duration >= 80.0 mins, File Size > 500 MB).
"""

import os
import sys
import glob
import re
import argparse
from pathlib import Path
from typing import List, Dict, Any

from master_assembler import assemble_master_video
from chunk_renderer import is_chunk_valid
import config


def find_part_chunks(chunks_dir: str, expected_parts: int = 15) -> List[str]:
    """
    Finds and validates chunk_part_01.mp4 through chunk_part_15.mp4 within chunks_dir.
    Searches recursively to support different artifact download layouts.
    """
    root_p = Path(chunks_dir).resolve()
    all_mp4s = list(root_p.glob("**/*.mp4"))

    chunk_map = {}
    pattern = re.compile(r"chunk_part_(\d{1,2})\.mp4$", re.IGNORECASE)

    for p in all_mp4s:
        m = pattern.search(p.name)
        if m:
            part_idx = int(m.group(1))
            if 1 <= part_idx <= expected_parts:
                chunk_map[part_idx] = str(p)

    missing = [p for p in range(1, expected_parts + 1) if p not in chunk_map]
    if missing:
        raise FileNotFoundError(
            f"Missing {len(missing)} chunks in {chunks_dir}: parts {missing}. Found: {list(chunk_map.keys())}"
        )

    ordered_chunks = [chunk_map[p] for p in range(1, expected_parts + 1)]

    # Validate each chunk
    invalid_chunks = []
    for idx, c_path in enumerate(ordered_chunks, start=1):
        if not is_chunk_valid(c_path):
            invalid_chunks.append((idx, c_path))

    if invalid_chunks:
        raise ValueError(f"Found invalid chunks that failed playback/size check: {invalid_chunks}")

    return ordered_chunks


def run_master_assembly(
    chunks_dir: str,
    output_master_path: str = "./output/master_final_90min.mp4",
    temp_dir: str = "./temp_master"
) -> Dict[str, Any]:
    """
    Executes master concatenation and Gatekeeper GK7 audit.
    """
    print("=" * 60)
    print("🎬 HistorySnooze Master Video Assembly")
    print(f"📁 Chunks Dir:         {chunks_dir}")
    print(f"📦 Output Master Path: {output_master_path}")
    print("=" * 60)

    total_parts = getattr(config, "TOTAL_PARTS", 15)
    chunk_paths = find_part_chunks(chunks_dir, expected_parts=total_parts)

    print(f"✓ Located all {len(chunk_paths)} validated Part chunks:")
    for idx, p in enumerate(chunk_paths, start=1):
        size_mb = os.path.getsize(p) / 1024 / 1024
        print(f"   [{idx:02d}] {os.path.basename(p)} ({size_mb:.1f} MB)")

    out_dir = os.path.dirname(os.path.abspath(output_master_path))
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    os.makedirs(temp_dir, exist_ok=True)

    audit_result = assemble_master_video(
        chunk_paths=chunk_paths,
        output_master_path=output_master_path,
        temp_dir=temp_dir
    )

    if not audit_result.get("passed_gk7", False):
        raise RuntimeError(
            f"Gatekeeper GK7 FAILED! Duration: {audit_result.get('duration_minutes')} mins, "
            f"Size: {audit_result.get('file_size_gb')} GB"
        )

    print("=" * 60)
    print("🏆 MASTER VIDEO ASSEMBLY COMPLETE!")
    print(f"🎬 File:      {audit_result['output_path']}")
    print(f"⏱️  Duration:  {audit_result['duration_minutes']} minutes ({audit_result['duration_seconds']}s)")
    print(f"💾 Size:      {audit_result['file_size_gb']} GB")
    print(f"🛡️  Gatekeeper: GK7 PASSED")
    print("=" * 60)

    return audit_result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Assemble 15 chunks into master 90-minute video")
    parser.add_argument("chunks_dir", nargs="?", default="./all_chunks", help="Directory containing chunk_part_*.mp4")
    parser.add_argument("output_master_path", nargs="?", default="./output/master_final_90min.mp4", help="Destination MP4")
    parser.add_argument("--temp_dir", default="./temp_master", help="Temp working directory")

    args = parser.parse_args()

    try:
        run_master_assembly(args.chunks_dir, args.output_master_path, args.temp_dir)
        sys.exit(0)
    except Exception as err:
        print(f"❌ Master assembly failed: {err}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
