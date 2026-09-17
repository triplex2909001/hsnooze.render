"""
HistorySnooze Asset Downloader for GitHub Actions / Cloud Runners.
Downloads voiceover audio, keyframes, and prompt manifests.
Combines ultra-fast GitHub Release CDN for 150 keyframe bundle with Google Drive sync.
Adheres to Documents/Structure/01_ARCHITECTURE_CONSTRAINED_AI.md (Rule <= 150 lines/file).
"""

import os
import sys
import shutil
import urllib.request
from pathlib import Path

# Submodule imports
_CUR_DIR = Path(__file__).resolve().parent
if str(_CUR_DIR) not in sys.path:
    sys.path.insert(0, str(_CUR_DIR))

from drive_extractor import SecurityError, safe_extract_tarball
from network_retry import retry_network_op

KEYFRAMES_RELEASE_URL = (
    "https://github.com/triplex2909001/hsnooze.render/releases/download/"
    "v-assets-basho/keyframes_bundle.tar.gz"
)

KNOWN_SUBFOLDERS = {
    "1TILhfJstpKX3stnzIzBk6A8ZZKqc7wtc": {
        "audio": "1LernpBWI1DlePFLQiVqTTSGYA9435NjK",
        "keyframes": "19krkuGIJ8l1eyASLIhKyi1oQS9f5cjmm",
        "combined": "1LQQtIcqoMPHqo7Pmpr_zirgCg723SnnY",
    }
}


@retry_network_op(max_retries=3, initial_delay=1.0, backoff_factor=2.0)
def fetch_keyframe_bundle_cdn(bundle_tar: Path, keyframes_dir: Path) -> bool:
    """Downloads keyframe bundle tarball from GitHub CDN with automatic retry."""
    if not bundle_tar.exists() or bundle_tar.stat().st_size == 0:
        tmp_tar = bundle_tar.with_suffix(".tar.tmp")
        req = urllib.request.Request(KEYFRAMES_RELEASE_URL, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=60) as resp, open(tmp_tar, "wb") as f_out:
            shutil.copyfileobj(resp, f_out)
        tmp_tar.replace(bundle_tar)
    print(f"[DOWNLOAD] Keyframe bundle downloaded ({bundle_tar.stat().st_size / (1024*1024):.1f} MB). Extracting...")
    safe_extract_tarball(bundle_tar, keyframes_dir)
    return True


@retry_network_op(max_retries=3, initial_delay=2.0, backoff_factor=2.0)
def download_drive_folder(folder_id: str, output_dir: str, quiet: bool = True) -> None:
    """Downloads Google Drive folder using gdown with automatic exponential retry."""
    import gdown
    gdown.download_folder(id=folder_id, output=output_dir, quiet=quiet, use_cookies=False)


def _sync_prompts(target_path: Path, media_gen_dir: Path, combined_dir: Path, folder_id: str) -> None:
    """Syncs combined_imageprompts.txt from repo or Google Drive."""
    repo_prompts = Path("combined_imageprompts.txt")
    if repo_prompts.exists():
        for dest_dir in (target_path, media_gen_dir, combined_dir):
            shutil.copy2(repo_prompts, dest_dir / "combined_imageprompts.txt")
        print("✓ Loaded combined_imageprompts.txt from repository")
    else:
        comb_id = KNOWN_SUBFOLDERS.get(folder_id, {}).get("combined")
        if comb_id:
            try:
                download_drive_folder(comb_id, str(combined_dir), quiet=True)
            except Exception as e:
                print(f"Warning downloading combined folder: {e}")


def download_project_assets(folder_id: str, target_dir: str):
    """Downloads project assets (keyframes, audio, prompts) with self-healing retries."""
    target_path = Path(target_dir).resolve()
    media_gen_dir = target_path / "02. Media Generation"
    audio_dir = media_gen_dir / "audio"
    keyframes_dir = media_gen_dir / "keyframes"
    combined_dir = media_gen_dir / "combined"

    for d in (target_path, audio_dir, keyframes_dir, combined_dir):
        d.mkdir(parents=True, exist_ok=True)

    print(f"[DOWNLOAD] Initiating asset sync for Project: {folder_id} -> {target_path}")

    # 1. CDN Keyframes bundle
    bundle_tar = target_path / "keyframes_bundle.tar.gz"
    try:
        fetch_keyframe_bundle_cdn(bundle_tar, keyframes_dir)
        print(f"✓ Successfully unpacked keyframes into {keyframes_dir}")
    except Exception as e:
        print(f"⚠️ CDN bundle download fallback: {e}")
        if bundle_tar.exists():
            try:
                bundle_tar.unlink()
            except OSError:
                pass

    # Fallback to gdown for keyframes if needed
    existing_kfs = [f for ext in ("jpg", "jpeg", "png") for f in keyframes_dir.glob(f"beat_*.{ext}")]
    if len(existing_kfs) < 150:
        kf_id = KNOWN_SUBFOLDERS.get(folder_id, {}).get("keyframes")
        if kf_id:
            print(f"[DOWNLOAD] Falling back to direct Drive keyframes sync ({kf_id})...")
            try:
                download_drive_folder(kf_id, str(keyframes_dir), quiet=True)
            except Exception as e:
                print(f"Drive keyframe sync warning: {e}")

    # 2. Audio Parts
    audio_id = KNOWN_SUBFOLDERS.get(folder_id, {}).get("audio", "1LernpBWI1DlePFLQiVqTTSGYA9435NjK")
    print(f"[DOWNLOAD] Syncing 15 audio WAV parts from Drive folder ({audio_id})...")
    try:
        download_drive_folder(audio_id, str(audio_dir), quiet=False)
    except Exception as e:
        print(f"⚠️ Warning during audio sync: {e}")

    from pipeline_orchestrator import link_or_copy_artifact
    for w in target_path.glob("**/Part_*.wav"):
        dest = audio_dir / w.name
        if dest.resolve() != w.resolve():
            try:
                link_or_copy_artifact(str(w), str(audio_dir))
            except Exception:
                shutil.copy2(w, dest)

    # 3. Prompts & Audit
    _sync_prompts(target_path, media_gen_dir, combined_dir, folder_id)
    final_wavs = sorted(audio_dir.glob("Part_*.wav"))
    unique_kfs = {f.stem for ext in ("jpg", "jpeg", "png", "JPG", "JPEG", "PNG") for f in keyframes_dir.glob(f"beat_*.{ext}")}

    print("=" * 50)
    print(f"✅ ASSET DOWNLOAD COMPLETE: Audio={len(final_wavs)}/15, Beats={len(unique_kfs)}/150")
    print("=" * 50)
    if len(final_wavs) < 15 or len(unique_kfs) < 150:
        print(f"❌ Asset verification failed: WAVs={len(final_wavs)}/15, Beats={len(unique_kfs)}/150")
        sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 download_drive_assets.py <folder_id> [target_dir]")
        sys.exit(1)
    download_project_assets(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "./project_assets")
