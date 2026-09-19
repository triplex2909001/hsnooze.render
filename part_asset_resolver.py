"""
HistorySnooze Director - Part Asset Resolver
Resolves and downloads audio, keyframe bundles, and cue manifests for a Part (Rule <= 150 lines).
"""

import os
import shutil
import sys
import urllib.request
from pathlib import Path
from typing import List, Optional, Tuple

_DIR = str(Path(__file__).resolve().parent)
if _DIR not in sys.path:
    sys.path.insert(0, _DIR)

from tar_archive_guard import safe_extract_tarball

try:
    import config
except ImportError:
    config = None

def get_release_urls() -> Tuple[str, str]:
    tag = os.environ.get("RELEASE_TAG", "v-assets-basho").strip()
    repo = os.environ.get("GITHUB_REPOSITORY", "triplex2909001/hsnooze.render").strip()
    kf_url = f"https://github.com/{repo}/releases/download/{tag}/keyframes_bundle.tar.gz"
    audio_url = f"https://github.com/{repo}/releases/download/{tag}/audio_bundle.tar.gz"
    return kf_url, audio_url



def _scan_keyframes(keyframes_dir: Path, part_prefix: str) -> List[str]:
    return [
        str(p) for p in sorted(
            list(keyframes_dir.glob(f"{part_prefix}*.jp*g"))
            + list(keyframes_dir.glob(f"{part_prefix}*.JP*G"))
            + list(keyframes_dir.glob(f"{part_prefix}*.png"))
            + list(keyframes_dir.glob(f"{part_prefix}*.PNG"))
        )
    ]


def ensure_part_assets(project_root: str, part_index: int) -> Tuple[str, List[str], Optional[str]]:
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
    existing_kfs = _scan_keyframes(keyframes_dir, part_prefix)
    target_beats = getattr(config, "TARGET_BEATS_PER_PART", 10) if config else 10

    kf_release_url, audio_release_url = get_release_urls()

    # 1. Fetch keyframes if deficient
    if len(existing_kfs) < target_beats:
        print(f"[ASSET] Part {part_index:02d} has {len(existing_kfs)}/{target_beats} keyframes. Fetching from CDN ({kf_release_url})...")
        bundle_tar = root_path / "keyframes_bundle.tar.gz"
        try:
            if not bundle_tar.exists() or bundle_tar.stat().st_size == 0:
                tmp_tar = bundle_tar.with_suffix(".tar.tmp")
                req = urllib.request.Request(kf_release_url, headers={"User-Agent": "Mozilla/5.0"})
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

        existing_kfs = _scan_keyframes(keyframes_dir, part_prefix)
        print(f"✓ Extracted {len(existing_kfs)} keyframes for Part {part_index:02d}")

    # 2. Fetch audio if missing
    expected_wav_name = f"Part_{part_index:02d}.wav"
    audio_path = audio_dir / expected_wav_name
    if not audio_path.exists() or audio_path.stat().st_size < 1024 * 1024:
        found_wavs = [w for w in root_path.glob(f"**/{expected_wav_name}") if w.resolve() != audio_path.resolve()]
        if found_wavs and found_wavs[0].stat().st_size > 1024 * 1024:
            from pipeline_orchestrator import link_or_copy_artifact
            try:
                link_or_copy_artifact(str(found_wavs[0]), str(audio_dir))
            except Exception:
                shutil.copy2(found_wavs[0], audio_path)
        else:
            print(f"[ASSET] {expected_wav_name} not found. Fetching audio bundle from CDN ({audio_release_url})...")
            audio_tar = root_path / "audio_bundle.tar.gz"
            try:
                if not audio_tar.exists() or audio_tar.stat().st_size == 0:
                    tmp_tar = audio_tar.with_suffix(".tar.tmp")
                    req = urllib.request.Request(audio_release_url, headers={"User-Agent": "Mozilla/5.0"})
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
        cand_cues = audio_dir / "Part_01_cues.json"
        if cand_cues.exists():
            cues_path = str(cand_cues)
        else:
            found_cues = list(root_path.glob("**/Part_01_cues.json"))
            if found_cues:
                cues_path = str(found_cues[0])

    return str(audio_path), existing_kfs, cues_path
