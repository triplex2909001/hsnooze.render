"""
HistorySnooze Director - Orchestrator Stage Manager
Handles image stage transitions and Cover Image (HITL) gates (Rule <= 150 lines).
"""

import glob
import os


def check_cover_image_present(project_root: str) -> bool:
    """Checks whether the manual Cover image (beat_P01_B01.*) exists in keyframes."""
    keyframes_candidates = [
        os.path.join(project_root, "02. Media Generation", "keyframes"),
        os.path.join(project_root, "keyframes"),
        os.path.join(project_root, "hsnooze.render", "keyframes"),
    ]
    for kf_dir in keyframes_candidates:
        if os.path.isdir(kf_dir):
            for ext in ("*.jpg", "*.jpeg", "*.png", "*.JPG", "*.JPEG", "*.PNG"):
                matches = glob.glob(os.path.join(kf_dir, f"beat_P01_B01{ext[1:]}")) + glob.glob(os.path.join(kf_dir, f"beat_P01_B1{ext[1:]}"))
                if matches:
                    return True
    return False


def handle_image_generation_stage(
    project_root: str,
    image_mode: str = "Automatic",
    current_status: str = "Voiceover"
) -> str:
    """Handles Image generation branching and Human-in-the-Loop (HITL) gates."""
    has_cover = check_cover_image_present(project_root)
    status_clean = current_status.strip().capitalize()

    if status_clean == "Voiceover":
        if image_mode.lower() == "automatic":
            print("[ORCHESTRATOR] Status is 'Voiceover'. Initiating automated image generation (excluding Cover)...")
            print("[ORCHESTRATOR] Transitioning Status -> 'JPEG' awaiting human Cover insertion.")
            return "JPEG"
        print("[ORCHESTRATOR] Image_Mode is 'Manual'. Awaiting human image upload.")
        return "Voiceover"

    elif status_clean == "Jpeg":
        if not has_cover:
            print("=" * 60)
            print("⏸️ [HUMAN-IN-THE-LOOP CHECKPOINT: STATUS = JPEG]")
            print("👉 Automated keyframes are ready (Beats P01_B02 .. P15_B10).")
            print("👉 Step blocked: Please design and add your Cover image ('beat_P01_B01.jpg/png') into keyframes/.")
            print("👉 After placing Cover image, change Status from 'JPEG' to 'Image' on Dashboard to activate render.")
            print("=" * 60)
            return "JPEG"
        print("✅ Found manual Cover image 'beat_P01_B01'. Awaiting human to switch Status to 'Image'.")
        return "JPEG"

    elif status_clean == "Image":
        if not has_cover:
            raise ValueError(
                "Cannot render: Status is 'Image' but manual Cover image 'beat_P01_B01' is missing from keyframes! "
                "Please add Cover image before rendering."
            )
        print("✅ Status is 'Image' and manual Cover image verified. Authorizing 4K Video Render Pipeline.")
        return "Image"

    return status_clean
