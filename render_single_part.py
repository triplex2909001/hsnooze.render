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


class SecurityError(Exception):
    """Raised when an archive member attempts directory traversal (CVE-2007-4559)."""
    pass


def safe_extract_tarball(archive_path: Path, destination_dir: Path) -> None:
    """
    Safely extracts a tar archive ensuring no member path escapes the target directory (CVE-2007-4559).
    Validates regular files, directories, symlinks, and hardlinks against directory traversal.
    Blocks special device files (char, block, fifo), absolute paths, and chained link escapes.
    Strips dangerous permission bits and extracts member-by-member to ensure live filesystem validation.
    """
    if not destination_dir or not str(destination_dir).strip():
        raise ValueError("destination_dir cannot be empty or whitespace")

    dest_resolved = Path(destination_dir).resolve()
    dest_resolved.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive_path, "r:*") as tar:
        for member in tar.getmembers():
            norm_name = os.path.normpath(member.name)
            if not member.name.strip() or norm_name in (".", ""):
                continue

            # Disallow null bytes in member names
            if "\0" in member.name:
                raise SecurityError(
                    f"Null byte detected in archive member: '{member.name}'"
                )

            # Disallow absolute paths and Windows drive letters in member names
            import ntpath
            if (
                member.name.startswith(("/", "\\"))
                or os.path.isabs(member.name)
                or bool(ntpath.splitdrive(member.name)[0])
            ):
                raise SecurityError(
                    f"Absolute or drive path detected in archive member: '{member.name}'"
                )

            # Block special device nodes (character, block, fifo)
            if member.isdev() or member.ischr() or member.isblk() or member.isfifo():
                raise SecurityError(
                    f"Special device file detected in archive member: '{member.name}'"
                )

            target_path = (dest_resolved / member.name).resolve()
            try:
                target_path.relative_to(dest_resolved)
            except ValueError:
                raise SecurityError(
                    f"Directory traversal attack detected in archive member: '{member.name}' "
                    f"resolves to '{target_path}' which is outside destination '{dest_resolved}'"
                )

            # Validate symlink and hardlink targets stay strictly within destination
            if member.issym() or member.islnk():
                if (
                    member.linkname.startswith(("/", "\\"))
                    or os.path.isabs(member.linkname)
                    or bool(ntpath.splitdrive(member.linkname)[0])
                    or ("\0" in member.linkname)
                ):
                    raise SecurityError(
                        f"Absolute, drive, or malformed link target detected in archive member: '{member.name}' -> '{member.linkname}'"
                    )
                if member.issym():
                    link_target = (target_path.parent / member.linkname).resolve()
                else:
                    link_target = (dest_resolved / member.linkname).resolve()
                try:
                    link_target.relative_to(dest_resolved)
                except ValueError:
                    raise SecurityError(
                        f"Directory traversal attack detected in link target: '{member.name}' -> '{member.linkname}'"
                    )

            # Strip setuid/setgid bits
            member.mode &= 0o777

            # Extract member individually so intermediate symlinks are grounded on disk
            if hasattr(tarfile, "data_filter"):
                tar.extract(member, path=str(dest_resolved), filter="data")
            else:
                tar.extract(member, path=str(dest_resolved))


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
        str(p) for p in sorted(
            list(keyframes_dir.glob(f"{part_prefix}*.jp*g"))
            + list(keyframes_dir.glob(f"{part_prefix}*.JP*G"))
            + list(keyframes_dir.glob(f"{part_prefix}*.png"))
            + list(keyframes_dir.glob(f"{part_prefix}*.PNG"))
        )
    ]

    target_beats = getattr(config, "TARGET_BEATS_PER_PART", 10)

    # 1. Fetch keyframes if deficient
    if len(existing_kfs) < target_beats:
        print(f"[ASSET] Part {part_index:02d} has {len(existing_kfs)}/{target_beats} keyframes. Fetching bundle from CDN...")
        bundle_tar = root_path / "keyframes_bundle.tar.gz"
        try:
            if not bundle_tar.exists() or bundle_tar.stat().st_size == 0:
                tmp_tar = bundle_tar.with_suffix(".tar.tmp")
                req = urllib.request.Request(KEYFRAMES_RELEASE_URL, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=60) as resp, open(tmp_tar, "wb") as f_out:
                    shutil.copyfileobj(resp, f_out)
                tmp_tar.replace(bundle_tar)
            safe_extract_tarball(bundle_tar, keyframes_dir)
        except Exception as e:
            if bundle_tar.exists():
                try:
                    bundle_tar.unlink()
                except OSError:
                    pass
            raise RuntimeError(f"Failed to fetch or extract keyframes bundle: {e}") from e

        existing_kfs = [
            str(p) for p in sorted(
                list(keyframes_dir.glob(f"{part_prefix}*.jp*g"))
                + list(keyframes_dir.glob(f"{part_prefix}*.JP*G"))
                + list(keyframes_dir.glob(f"{part_prefix}*.png"))
                + list(keyframes_dir.glob(f"{part_prefix}*.PNG"))
            )
        ]
        print(f"✓ Extracted {len(existing_kfs)} keyframes for Part {part_index:02d}")

    # 2. Fetch audio if missing
    expected_wav_name = f"Part_{part_index:02d}.wav"
    audio_path = audio_dir / expected_wav_name
    if not audio_path.exists() or audio_path.stat().st_size < 1024 * 1024:
        # Check parent search
        found_wavs = [w for w in root_path.glob(f"**/{expected_wav_name}") if w.resolve() != audio_path.resolve()]
        if found_wavs and found_wavs[0].stat().st_size > 1024 * 1024:
            from pipeline_orchestrator import link_or_copy_artifact
            try:
                link_or_copy_artifact(str(found_wavs[0]), str(audio_dir))
            except Exception:
                shutil.copy2(found_wavs[0], audio_path)
        else:
            print(f"[ASSET] {expected_wav_name} not found. Fetching audio bundle from CDN...")
            audio_tar = root_path / "audio_bundle.tar.gz"
            try:
                if not audio_tar.exists() or audio_tar.stat().st_size == 0:
                    tmp_tar = audio_tar.with_suffix(".tar.tmp")
                    req = urllib.request.Request(AUDIO_RELEASE_URL, headers={"User-Agent": "Mozilla/5.0"})
                    with urllib.request.urlopen(req, timeout=60) as resp, open(tmp_tar, "wb") as f_out:
                        shutil.copyfileobj(resp, f_out)
                    tmp_tar.replace(audio_tar)
                safe_extract_tarball(audio_tar, audio_dir)
            except Exception as e:
                if audio_tar.exists():
                    try:
                        audio_tar.unlink()
                    except OSError:
                        pass
                raise RuntimeError(f"Failed to fetch or extract audio bundle: {e}") from e

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


def render_single_part(project_root: str, part_index: int, max_workers: int = 4, force_cpu: bool = False) -> str:
    """
    Renders one Part chunk.
    """
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

    target_beats = getattr(config, "TARGET_BEATS_PER_PART", 10)
    if len(beat_images) < target_beats:
        raise ValueError(f"Insufficient keyframes for Part {part_index:02d}: found {len(beat_images)}, expected >= {target_beats}")

    # GK6 Parity: Cover Image Verification (HITL) on Part 01
    if part_index == 1:
        has_cover = any(
            bool(re.search(r"beat_P0?1_B0?1(?:\.|$|_)", img))
            for img in beat_images
        )
        if not has_cover:
            print("=" * 60)
            print("⏸️ [HUMAN-IN-THE-LOOP CHECKPOINT: COVER MISSING]")
            print("👉 Part 01 Beat 01 Cover image ('beat_P01_B01.*') is missing from keyframes!")
            print("👉 Please upload your custom Cover image into '02. Media Generation/keyframes/'")
            print("   and change Status on Google Sheet to 'Image' before rendering.")
            print("=" * 60)
            raise FileNotFoundError("Manual Cover image 'beat_P01_B01' is required before rendering Part 01.")

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
        output_dir=chunks_dir,
        temp_dir=temp_dir,
        cues_json_path=cues_json,
        force_cpu=force_cpu,
        max_workers=max_workers
    )

    if not is_chunk_valid(rendered_chunk):
        raise RuntimeError(f"Rendered chunk {rendered_chunk} failed validation!")

    # Link canonical chunk to output/
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
