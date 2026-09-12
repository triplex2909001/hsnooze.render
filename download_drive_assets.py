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
        req = urllib.request.Request(KEYFRAMES_RELEASE_URL, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req) as resp, open(bundle_tar, "wb") as f_out:
            shutil.copyfileobj(resp, f_out)
        print(f"[DOWNLOAD] Keyframe bundle downloaded ({bundle_tar.stat().st_size / 1024 / 1024:.1f} MB). Extracting...")
        with tarfile.open(bundle_tar, "r:gz") as tar:
            tar.extractall(path=str(keyframes_dir))
        downloaded_bundle = True
        print(f"✓ Successfully unpacked keyframes into {keyframes_dir}")
    except Exception as e:
        print(f"⚠️ CDN bundle download fallback: {e}")

    # Fallback to gdown if bundle extraction failed
    existing_kfs = list(keyframes_dir.glob("beat_*.jp*g")) + list(keyframes_dir.glob("beat_*.png"))
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
    for w in target_path.glob("**/Part_*.wav"):
        dest = audio_dir / w.name
        if dest.resolve() != w.resolve():
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
    final_kfs = sorted(list(keyframes_dir.glob("beat_*.jp*g")) + list(keyframes_dir.glob("beat_*.png")))
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
