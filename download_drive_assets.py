"""
HistorySnooze Asset Downloader for GitHub Actions / Cloud Runners
Downloads voiceover audio, keyframes, and prompt manifests.
Combines ultra-fast GitHub Release CDN for 150 keyframe bundle with Google Drive sync.
"""

import os
import sys
import glob
import shutil
import urllib.request
import tarfile
from pathlib import Path

KEYFRAMES_RELEASE_URL = "https://github.com/triplex2909001/hsnooze.render/releases/download/v-assets-basho/keyframes_bundle.tar.gz"

KNOWN_SUBFOLDERS = {
    "1TILhfJstpKX3stnzIzBk6A8ZZKqc7wtc": {
        "audio": "1LernpBWI1DlePFLQiVqTTSGYA9435NjK",
        "keyframes": "19krkuGIJ8l1eyASLIhKyi1oQS9f5cjmm",
        "combined": "1LQQtIcqoMPHqo7Pmpr_zirgCg723SnnY",
    }
}


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


def download_project_assets(folder_id: str, target_dir: str):
    import gdown

    target_path = Path(target_dir).resolve()
    target_path.mkdir(parents=True, exist_ok=True)
    media_gen_dir = target_path / "02. Media Generation"
    audio_dir = media_gen_dir / "audio"
    keyframes_dir = media_gen_dir / "keyframes"
    combined_dir = media_gen_dir / "combined"

    audio_dir.mkdir(parents=True, exist_ok=True)
    keyframes_dir.mkdir(parents=True, exist_ok=True)
    combined_dir.mkdir(parents=True, exist_ok=True)

    print(f"[DOWNLOAD] Initiating asset sync for Project: {folder_id}")
    print(f"[DOWNLOAD] Target Directory: {target_path}")

    # --- 1. KEYFRAME BEATS (Ultra-fast CDN Release Bundle) ---
    print(f"[DOWNLOAD] Fetching 150-beat keyframe bundle from GitHub CDN...")
    bundle_tar = target_path / "keyframes_bundle.tar.gz"
    downloaded_bundle = False
    try:
        if not bundle_tar.exists() or bundle_tar.stat().st_size == 0:
            tmp_tar = bundle_tar.with_suffix(".tar.tmp")
            req = urllib.request.Request(KEYFRAMES_RELEASE_URL, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=60) as resp, open(tmp_tar, "wb") as f_out:
                shutil.copyfileobj(resp, f_out)
            tmp_tar.replace(bundle_tar)
        print(f"[DOWNLOAD] Keyframe bundle downloaded ({bundle_tar.stat().st_size / 1024 / 1024:.1f} MB). Extracting...")
        safe_extract_tarball(bundle_tar, keyframes_dir)
        downloaded_bundle = True
        print(f"✓ Successfully unpacked keyframes into {keyframes_dir}")
    except Exception as e:
        print(f"⚠️ CDN bundle download fallback: {e}")
        # If the downloaded bundle is corrupt, remove it to allow clean re-download on next attempt
        if bundle_tar.exists() and not downloaded_bundle:
            try:
                bundle_tar.unlink()
            except OSError:
                pass

    # Fallback to gdown if bundle extraction failed
    existing_kfs = []
    for ext in ("*.jpg", "*.jpeg", "*.png", "*.JPG", "*.JPEG", "*.PNG"):
        existing_kfs.extend(keyframes_dir.glob(f"beat_{ext}"))
    if len(existing_kfs) < 150:
        subfolder_map = KNOWN_SUBFOLDERS.get(folder_id, {})
        kf_id = subfolder_map.get("keyframes")
        if kf_id:
            print(f"[DOWNLOAD] Falling back to direct Drive keyframes sync ({kf_id})...")
            try:
                gdown.download_folder(id=kf_id, output=str(keyframes_dir), quiet=True, use_cookies=False)
            except Exception as e:
                print(f"Drive keyframe sync warning: {e}")

    # --- 2. AUDIO PARTS (Direct Drive Audio Folder Sync) ---
    subfolder_map = KNOWN_SUBFOLDERS.get(folder_id, {})
    audio_id = subfolder_map.get("audio", "1LernpBWI1DlePFLQiVqTTSGYA9435NjK")
    print(f"[DOWNLOAD] Syncing 15 audio WAV parts from Drive folder ({audio_id})...")
    try:
        gdown.download_folder(id=audio_id, output=str(audio_dir), quiet=False, use_cookies=False)
    except Exception as e:
        print(f"⚠️ Warning during audio sync: {e}")

    # Re-check flattened WAV files
    from pipeline_orchestrator import link_or_copy_artifact
    for w in target_path.glob("**/Part_*.wav"):
        dest = audio_dir / w.name
        if dest.resolve() != w.resolve():
            try:
                link_or_copy_artifact(str(w), str(audio_dir))
            except Exception:
                shutil.copy2(w, dest)

    # --- 3. PROMPTS & MANIFEST ---
    repo_prompts = Path("combined_imageprompts.txt")
    if repo_prompts.exists():
        shutil.copy2(repo_prompts, target_path / "combined_imageprompts.txt")
        shutil.copy2(repo_prompts, media_gen_dir / "combined_imageprompts.txt")
        shutil.copy2(repo_prompts, combined_dir / "combined_imageprompts.txt")
        print("✓ Loaded combined_imageprompts.txt from repository")
    else:
        comb_id = subfolder_map.get("combined")
        if comb_id:
            try:
                gdown.download_folder(id=comb_id, output=str(combined_dir), quiet=True, use_cookies=False)
            except Exception as e:
                print(f"Warning downloading combined folder: {e}")

    # Final Audit
    final_wavs = sorted(audio_dir.glob("Part_*.wav"))
    final_kfs = []
    for ext in ("*.jpg", "*.jpeg", "*.png", "*.JPG", "*.JPEG", "*.PNG"):
        final_kfs.extend(keyframes_dir.glob(f"beat_{ext}"))
    final_kfs.sort()
    # Deduplicate stems
    unique_stems = {os.path.splitext(f.name)[0] for f in final_kfs}

    print(f"==================================================")
    print(f"✅ ASSET DOWNLOAD COMPLETE:")
    print(f"   Audio Parts:    {len(final_wavs)}/15 WAVs")
    print(f"   Keyframe Beats: {len(unique_stems)}/150 Unique Beats")
    print(f"   Target Root:    {target_path}")
    print(f"==================================================")

    if len(final_wavs) < 15 or len(unique_stems) < 150:
        print(f"❌ Asset verification failed: WAVs={len(final_wavs)}/15, Beats={len(unique_stems)}/150")
        sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 download_drive_assets.py <folder_id> [target_dir]")
        sys.exit(1)

    fid = sys.argv[1]
    tdir = sys.argv[2] if len(sys.argv) > 2 else "./project_assets"
    download_project_assets(fid, tdir)
