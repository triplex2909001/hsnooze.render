"""
HISTORYSNOOZE: GOOGLE COLAB VIDEO RENDER RUNNER (COLAB-CLI COMPLIANT)
Module: colab_render_runner.py
Version: 1.1.0
Adheres to Documents/Structure/01_ARCHITECTURE_CONSTRAINED_AI.md (Rule <= 150 lines/file).
"""

import os
import sys
import time
from pathlib import Path
from typing import List, Optional

_CUR_DIR = Path(__file__).resolve().parent
if str(_CUR_DIR) not in sys.path:
    sys.path.insert(0, str(_CUR_DIR))

import config
from chunk_renderer import render_part_chunk, is_chunk_valid
from master_assembler import assemble_master_video
from kenburns_asmr import check_nvenc_available
from pipeline_orchestrator import link_or_copy_artifact
from colab_render_env import mount_colab_drive, find_project_dir, audit_render_assets, get_part_images
from colab_render_cli import parse_colab_render_args


def _setup_directories(proj_dir: Path):
    """Sets up chunks, scratch temp, final production, and output directories."""
    chunks_dir = proj_dir / "02. Media Generation" / "chunks"
    final_dir = proj_dir / "03. Final Production"
    output_dir = proj_dir / "output"
    temp_dir = Path("/content/temp_render") if os.path.exists("/content") else proj_dir / "02. Media Generation" / "temp"
    for d in (chunks_dir, temp_dir, final_dir, output_dir):
        d.mkdir(parents=True, exist_ok=True)
    return chunks_dir, final_dir, output_dir, temp_dir


def _render_chunks(parts, chunks_dir, audio_dir, keyframes_dir, output_dir, temp_dir, force_cpu, max_workers):
    """Iterates through parts 1..15, rendering each chunk and mirroring to output/."""
    chunk_paths = []
    for part_idx in range(1, 16):
        chunk_file = chunks_dir / f"chunk_part_{part_idx:02d}.mp4"
        if part_idx not in parts:
            if chunk_file.exists() and is_chunk_valid(str(chunk_file)):
                print(f"[SKIP] Part {part_idx:02d} already valid and not requested in filter.")
                chunk_paths.append(str(chunk_file))
                try:
                    link_or_copy_artifact(str(chunk_file), str(output_dir))
                except Exception:
                    pass
            continue

        audio_file = audio_dir / f"Part_{part_idx:02d}.wav"
        part_images = get_part_images(keyframes_dir, part_idx)
        if not audio_file.exists():
            raise FileNotFoundError(f"Missing audio file: {audio_file}")
        if not part_images:
            raise FileNotFoundError(f"No keyframes found for Part {part_idx:02d}")

        print(f"\n>>> [PART {part_idx:02d}/15] Rendering chunk with {len(part_images)} beats...")
        part_t0 = time.time()
        chunk_mp4 = render_part_chunk(
            part_index=part_idx,
            audio_wav_path=str(audio_file),
            beat_images=[str(img) for img in part_images],
            output_dir=str(chunks_dir),
            temp_dir=str(temp_dir),
            force_cpu=force_cpu,
            max_workers=max_workers
        )
        chunk_paths.append(chunk_mp4)
        try:
            link_or_copy_artifact(chunk_mp4, str(output_dir))
        except Exception:
            pass
        print(f"✓ [PART {part_idx:02d}/15] Rendered in {time.time() - part_t0:.1f}s")
    return chunk_paths


def run_colab_render(
    project_folder_path: str,
    parts_to_process: Optional[List[int]] = None,
    force_cpu: bool = False,
    folder_id: Optional[str] = None,
    sheet_id: Optional[str] = None,
    row_index: Optional[int] = None,
    max_workers: int = 2,
    force_render: bool = False
):
    proj_dir = Path(project_folder_path).resolve()
    audio_dir = proj_dir / "02. Media Generation" / "audio"
    keyframes_dir = proj_dir / "02. Media Generation" / "keyframes"
    if folder_id and (not audio_dir.exists() or len(list(audio_dir.glob("Part_*.wav"))) < 15):
        print(f"[Colab] Syncing assets from Drive folder: {folder_id}...")
        from download_drive_assets import download_project_assets
        download_project_assets(folder_id, str(proj_dir))

    if not proj_dir.exists():
        raise FileNotFoundError(f"Project directory does not exist: {proj_dir}")

    chunks_dir, final_dir, output_dir, temp_dir = _setup_directories(proj_dir)
    output_dir = proj_dir / "output"
    has_nvenc = (not force_cpu) and check_nvenc_available()
    print("=" * 75)
    print(f"COLAB VIDEO RENDERER: {proj_dir.name} | NVENC: {'YES' if has_nvenc else 'NO (CPU)'}")
    print("=" * 75)

    audit_render_assets(proj_dir, audio_dir, keyframes_dir, force_render)
    parts = parts_to_process if parts_to_process else list(range(1, 16))
    chunk_paths = _render_chunks(parts, chunks_dir, audio_dir, keyframes_dir, output_dir, temp_dir, force_cpu, max_workers)

    if len(chunk_paths) == 15:
        master_mp4 = final_dir / "master_final_90min.mp4"
        print(f"\n>>> [MASTER ASSEMBLY] Concatenating 15 parts with {config.INTER_PART_SILENCE_SEC}s silence...")
        master_result = assemble_master_video(chunk_paths=chunk_paths, output_master_path=str(master_mp4), temp_dir=str(temp_dir))
        try:
            link_or_copy_artifact(str(master_mp4), str(output_dir))
        except Exception:
            pass
        return master_result
    return None


def main():
    args = parse_colab_render_args()
    if args.mount_drive:
        mount_colab_drive()
    proj_dir = args.project_dir_opt or args.project_dir or "./project_assets"
    parts = [int(p.strip()) for p in args.parts.split(",") if p.strip()] if args.parts else None
    run_colab_render(
        project_folder_path=proj_dir,
        parts_to_process=parts,
        force_cpu=args.cpu,
        folder_id=args.folder_id or None,
        max_workers=args.workers,
        force_render=args.force
    )


if __name__ == "__main__":
    main()
