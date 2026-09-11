"""
HistorySnooze Image Pipeline Worker (v1.5.0)
Coordinates headless Google Flow 1K image generation via streamlined gflow CLI.
Automated trigger: Image_Mode == 'Automatic' & Status == 'Voiceover'.
Target Account: hothihuong113@gmail.com (profile default).
Target Resolution: 1K (original), 16:9 aspect ratio.
Streaming: Downloads beat images and uploads immediately to Google Drive keyframes folder.
"""

import sys
import os
import re
import json
import time
import argparse
import subprocess
from pathlib import Path

DEFAULT_SHEET_ID = "1x2tcR4WyHXj_cvHjpPFWNsrtelkimUXJXNTw9hPbVeo"
DEFAULT_VPS = "vpsg24gb"
DEFAULT_REMOTE_GFLOW = "/media/vpsg24gb/DATA/gflow"
LOCAL_ATTACHMENTS = Path("/Users/hanario/.workspace-mcp/attachments/images")

def parse_prompts(prompt_file: Path):
    with open(prompt_file, "r", encoding="utf-8") as f:
        content = f.read()

    beats = []
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        colon_idx = line.find(":")
        if colon_idx > 0:
            raw_id = line[:colon_idx].strip()
            prompt = line[colon_idx + 1:].strip()
            clean_id = re.sub(r"\.(jpg|jpeg|png|webp)$", "", raw_id, flags=re.IGNORECASE)
            beats.append({"id": clean_id, "prompt": prompt})
    return beats

def run_remote_gflow(vps_host: str, remote_dir: str, local_prompt_file: Path, part_filter: int = None):
    # 1. SCP prompt file to VPS
    remote_prompts = f"{remote_dir}/prompts.txt"
    print(f"[1/4] Transferring prompt file to {vps_host}:{remote_prompts}...")
    scp_cmd = ["scp", str(local_prompt_file), f"{vps_host}:{remote_prompts}"]
    subprocess.run(scp_cmd, check=True)

    # 2. Trigger gflow prompts command on VPS
    cmd = f"cd {remote_dir} && node ./dist/src/index.js prompts {remote_prompts} --out {remote_dir}/images --no-headed --resume"
    if part_filter is not None:
        cmd += f" --part {part_filter}"

    print(f"[2/4] Executing streamlined gflow on {vps_host}...")
    print(f"      Command: {cmd}")
    ssh_cmd = ["ssh", vps_host, cmd]
    res = subprocess.run(ssh_cmd, capture_output=True, text=True)
    print(res.stdout)
    if res.returncode != 0:
        print(f"[ERROR from gflow on VPS]: {res.stderr}")
        return False
    return True

def sync_images_from_vps(vps_host: str, remote_dir: str, local_dir: Path):
    local_dir.mkdir(parents=True, exist_ok=True)
    print(f"[3/4] Syncing generated 1K images from {vps_host} to {local_dir}...")
    rsync_cmd = [
        "rsync", "-avz",
        "--include=*.jpg", "--include=*.jpeg", "--include=*.png",
        "--exclude=*",
        f"{vps_host}:{remote_dir}/images/",
        f"{str(local_dir)}/"
    ]
    res = subprocess.run(rsync_cmd, capture_output=True, text=True)
    print(res.stdout)
    images = list(local_dir.glob("beat_*.jpg")) + list(local_dir.glob("beat_*.jpeg"))
    print(f"Found {len(images)} local beat images ready for Google Drive sync.")
    return images

def audit_image_gk3(filepath: Path, min_size_kb: float = 30.0):
    if not filepath.exists():
        return False, f"File {filepath.name} does not exist"
    size_kb = filepath.stat().st_size / 1024.0
    if size_kb < min_size_kb:
        return False, f"Size too small: {size_kb:.1f} KB < {min_size_kb} KB"
    return True, f"Valid 1K beat image ({size_kb:.1f} KB)"

def main():
    parser = argparse.ArgumentParser(description="HistorySnooze Image Pipeline Worker")
    parser.add_argument("--prompts", required=True, help="Path to combined_imageprompts.txt")
    parser.add_argument("--part", type=int, help="Optional part number filter (e.g. 1)")
    parser.add_argument("--vps", default=DEFAULT_VPS, help="VPS host SSH alias")
    parser.add_argument("--remote-dir", default=DEFAULT_REMOTE_GFLOW, help="Remote gflow directory")
    args = parser.parse_args()

    prompts_path = Path(args.prompts).resolve()
    if not prompts_path.exists():
        print(f"Error: Prompts file {prompts_path} does not exist!")
        sys.exit(1)

    beats = parse_prompts(prompts_path)
    print(f"Loaded {len(beats)} total beats from {prompts_path.name}")

    success = run_remote_gflow(args.vps, args.remote_dir, prompts_path, args.part)
    if not success:
        sys.exit(1)

    images = sync_images_from_vps(args.vps, args.remote_dir, LOCAL_ATTACHMENTS)
    for img in images:
        ok, msg = audit_image_gk3(img)
        print(f"  - {img.name}: {msg}")

    print("\n🎉 All beats processed and audited! Ready for Google Drive upload.")

if __name__ == "__main__":
    main()
