"""
HistorySnooze Image Pipeline Worker (v1.5.0).
Coordinates headless Google Flow 1K image generation via streamlined gflow CLI.
Adheres to Documents/Structure/01_ARCHITECTURE_CONSTRAINED_AI.md (Rule <= 150 lines/file).
"""

import sys
import os
import argparse
from pathlib import Path

# Submodule resolution
_CUR_DIR = Path(__file__).resolve().parent
if str(_CUR_DIR) not in sys.path:
    sys.path.insert(0, str(_CUR_DIR))

from image_prompt_parser import parse_prompts, audit_image_gk3
from image_remote_sync import (
    run_remote_gflow,
    sync_images_from_vps,
    connect_playwright_cdp,
    execute_playwright_cdp_call
)

DEFAULT_SHEET_ID = "1x2tcR4WyHXj_cvHjpPFWNsrtelkimUXJXNTw9hPbVeo"
DEFAULT_VPS = os.getenv("HSNOOZE_VPS_HOST", "vpsg24gb")
DEFAULT_REMOTE_GFLOW = os.getenv("HSNOOZE_GFLOW_DIR", "/media/vpsg24gb/DATA/gflow")
LOCAL_ATTACHMENTS = Path(
    os.getenv(
        "HSNOOZE_ATTACHMENTS_DIR",
        str(Path.home() / ".workspace-mcp" / "attachments" / "images")
    )
)


def _prepare_prompts(prompts_path: Path, beats: list, skipped_cover_id: str):
    """Generates temporary prompts file excluding manual cover beat if necessary."""
    if not skipped_cover_id:
        return prompts_path, None
    import tempfile
    tmp = Path(tempfile.gettempdir()) / f"prompts_no_cover_{os.getpid()}.txt"
    with open(tmp, "w", encoding="utf-8") as f:
        for b in beats:
            f.write(f"{b['id']}.jpg: {b['prompt']}\n\n")
    return tmp, tmp


def main():
    parser = argparse.ArgumentParser(description="HistorySnooze Image Pipeline Worker")
    parser.add_argument("--prompts", required=True, help="Path to combined_imageprompts.txt")
    parser.add_argument("--part", type=int, help="Optional part number filter (e.g. 1)")
    parser.add_argument("--vps", default=DEFAULT_VPS, help="VPS host SSH alias")
    parser.add_argument("--remote-dir", default=DEFAULT_REMOTE_GFLOW, help="Remote gflow directory")
    parser.add_argument("--include-cover", action="store_true", help="Force generating Cover image")
    args = parser.parse_args()

    prompts_path = Path(args.prompts).resolve()
    if not prompts_path.exists():
        print(f"Error: Prompts file {prompts_path} does not exist!")
        sys.exit(1)

    beats, skipped_cover_id = parse_prompts(prompts_path, skip_cover=not args.include_cover)
    print(f"Loaded {len(beats)} automated beats from {prompts_path.name}")
    if skipped_cover_id:
        print(f"⚠️ Cover image '{skipped_cover_id}' is EXCLUDED from automated generation (HITL).")

    actual_prompts, tmp_to_clean = _prepare_prompts(prompts_path, beats, skipped_cover_id)
    try:
        success = run_remote_gflow(args.vps, args.remote_dir, actual_prompts, args.part)
    finally:
        if tmp_to_clean and tmp_to_clean.exists():
            try:
                tmp_to_clean.unlink()
            except OSError:
                pass

    if not success:
        sys.exit(1)

    images = sync_images_from_vps(args.vps, args.remote_dir, LOCAL_ATTACHMENTS)
    for img in images:
        ok, msg = audit_image_gk3(img)
        print(f"  - {img.name}: {msg}")

    print("\n" + "=" * 65)
    print("🎉 Automated Keyframe Generation Complete!")
    print(f"✅ Generated {len(images)} automated keyframe images.")
    print("👉 Human-in-the-loop: place custom Cover image in keyframes/ before 4K render.")
    print("=" * 65 + "\n")


if __name__ == "__main__":
    main()
