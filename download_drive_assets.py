"""
HistorySnooze Asset Downloader for GitHub Actions / Cloud Runners
Downloads voiceover audio, keyframes, and prompt manifests from Google Drive.
Supports public Drive folders via gdown with fallback direct subfolder sync.
"""

import os
import sys
import glob
import shutil
from pathlib import Path

# Known subfolder IDs for Matsuo Bashō (and fallback mapping)
KNOWN_SUBFOLDERS = {
    "1TILhfJstpKX3stnzIzBk6A8ZZKqc7wtc": {
        "audio": "1LernpBWI1DlePFLQiVqTTSGYA9435NjK",
        "keyframes": "19krkuGIJ8l1eyASLIhKyi1oQS9f5cjmm",
        "combined": "1LQQtIcqoMPHqo7Pmpr_zirgCg723SnnY",
        "references": "1gN6zMml-lliz_wMf6o3e3_iSzOD9fx_B",
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

    print(f"[DOWNLOAD] Initiating Google Drive asset sync for folder: {folder_id}")
    print(f"[DOWNLOAD] Destination: {target_path}")

    # 1. Attempt full recursive folder download
    try:
        print("[DOWNLOAD] Downloading complete project folder hierarchy...")
        gdown.download_folder(
            id=folder_id,
            output=str(target_path),
            quiet=False,
            use_cookies=False
        )
    except Exception as e:
        print(f"⚠️ Warning during root folder download: {e}")

    # Check downloaded assets
    wavs = list(audio_dir.glob("Part_*.wav")) + list(target_path.glob("**/Part_*.wav"))
    keyframes = list(keyframes_dir.glob("beat_*.jp*g")) + list(keyframes_dir.glob("beat_*.png")) + list(target_path.glob("**/beat_*.jp*g"))

    # 2. Fallback / Direct subfolder download if needed
    subfolder_map = KNOWN_SUBFOLDERS.get(folder_id, {})

    if len(wavs) < 15 and "audio" in subfolder_map:
        print(f"[DOWNLOAD] Fallback: Direct download audio folder {subfolder_map['audio']}...")
        try:
            gdown.download_folder(
                id=subfolder_map["audio"],
                output=str(audio_dir),
                quiet=False,
                use_cookies=False
            )
        except Exception as e:
            print(f"Error downloading audio: {e}")

    if len(keyframes) < 150 and "keyframes" in subfolder_map:
        print(f"[DOWNLOAD] Fallback: Direct download keyframes folder {subfolder_map['keyframes']}...")
        try:
            gdown.download_folder(
                id=subfolder_map["keyframes"],
                output=str(keyframes_dir),
                quiet=False,
                use_cookies=False
            )
        except Exception as e:
            print(f"Error downloading keyframes: {e}")

    if "combined" in subfolder_map:
        prompts_file = media_gen_dir / "combined_imageprompts.txt"
        if not prompts_file.exists():
            print(f"[DOWNLOAD] Downloading combined prompts folder {subfolder_map['combined']}...")
            try:
                gdown.download_folder(
                    id=subfolder_map["combined"],
                    output=str(combined_dir),
                    quiet=False,
                    use_cookies=False
                )
            except Exception as e:
                print(f"Error downloading combined folder: {e}")

    # 3. Flatten / Reorganize into expected canonical structure
    # Audio
    found_wavs = sorted(target_path.glob("**/Part_*.wav"))
    for w in found_wavs:
        dest = audio_dir / w.name
        if dest.resolve() != w.resolve():
            shutil.copy2(w, dest)

    # Keyframes
    found_kfs = sorted(list(target_path.glob("**/beat_*.jp*g")) + list(target_path.glob("**/beat_*.png")))
    for kf in found_kfs:
        dest = keyframes_dir / kf.name
        if dest.resolve() != kf.resolve():
            shutil.copy2(kf, dest)

    # Prompts
    found_prompts = list(target_path.glob("**/combined_imageprompts.txt"))
    for p in found_prompts:
        dest1 = media_gen_dir / "combined_imageprompts.txt"
        dest2 = target_path / "combined_imageprompts.txt"
        if dest1.resolve() != p.resolve():
            shutil.copy2(p, dest1)
        if dest2.resolve() != p.resolve():
            shutil.copy2(p, dest2)

    # Audit final state
    final_wavs = sorted(audio_dir.glob("Part_*.wav"))
    final_kfs = sorted(list(keyframes_dir.glob("beat_*.jp*g")) + list(keyframes_dir.glob("beat_*.png")))
    print(f"==================================================")
    print(f"✅ ASSET DOWNLOAD COMPLETE:")
    print(f"   Audio Parts:    {len(final_wavs)}/15 WAVs")
    print(f"   Keyframe Beats: {len(final_kfs)}/150 Images")
    print(f"   Target Root:    {target_path}")
    print(f"==================================================")

    if len(final_wavs) < 15 or len(final_kfs) < 150:
        print(f"⚠️ Warning: Assets incomplete! WAVs={len(final_wavs)}, Keyframes={len(final_kfs)}")
        sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 download_drive_assets.py <folder_id> [target_dir]")
        sys.exit(1)

    fid = sys.argv[1]
    tdir = sys.argv[2] if len(sys.argv) > 2 else "./project_assets"
    download_project_assets(fid, tdir)
