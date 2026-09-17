"""
Remote Image Generation and CDP Synchronization Submodule.
Wraps Playwright CDP and remote network operations with @retry_network_op.
Adheres to Documents/Structure/01_ARCHITECTURE_CONSTRAINED_AI.md (Rule <= 150 lines/file).
"""

import sys
import subprocess
import json
from pathlib import Path
from typing import List, Optional, Any, Dict

_CUR_DIR = Path(__file__).resolve().parent
if str(_CUR_DIR) not in sys.path:
    sys.path.insert(0, str(_CUR_DIR))

from network_retry import retry_network_op


@retry_network_op(max_retries=3, initial_delay=2.0, backoff_factor=2.0)
def run_remote_gflow(vps_host: str, remote_dir: str, local_prompt_file: Path, part_filter: Optional[int] = None) -> bool:
    """Transfers prompts via SCP and triggers gflow CLI on remote VPS with retry."""
    remote_prompts = f"{remote_dir}/prompts.txt"
    print(f"[1/4] Transferring prompt file to {vps_host}:{remote_prompts}...")
    scp_cmd = ["scp", str(local_prompt_file), f"{vps_host}:{remote_prompts}"]
    subprocess.run(scp_cmd, check=True)

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
        raise RuntimeError(f"Remote gflow failed with exit code {res.returncode}: {res.stderr}")
    return True


@retry_network_op(max_retries=3, initial_delay=2.0, backoff_factor=2.0)
def sync_images_from_vps(vps_host: str, remote_dir: str, local_dir: Path) -> List[Path]:
    """Syncs generated 1K images from VPS to local staging directory with retry."""
    local_dir.mkdir(parents=True, exist_ok=True)
    print(f"[3/4] Syncing generated 1K images from {vps_host} to {local_dir}...")
    rsync_cmd = [
        "rsync", "-avz",
        "--include=*.jpg", "--include=*.jpeg", "--include=*.png",
        "--exclude=*",
        f"{vps_host}:{remote_dir}/images/",
        f"{str(local_dir)}/"
    ]
    subprocess.run(rsync_cmd, check=True)
    images = [
        img for ext in ("jpg", "jpeg", "png", "JPG", "JPEG", "PNG")
        for img in local_dir.glob(f"beat_*.{ext}")
    ]
    print(f"Found {len(images)} local beat images ready for Google Drive sync.")
    return images


@retry_network_op(max_retries=3, initial_delay=1.0, backoff_factor=2.0)
def connect_playwright_cdp(cdp_url: str = "http://127.0.0.1:49657") -> Any:
    """Connects to Chrome DevTools Protocol session via Playwright with retry."""
    try:
        from playwright.sync_api import sync_playwright
        p = sync_playwright().start()
        browser = p.chromium.connect_over_cdp(cdp_url)
        return p, browser
    except Exception as err:
        raise ConnectionError(f"Failed to connect to Playwright CDP at {cdp_url}: {err}")


@retry_network_op(max_retries=3, initial_delay=1.0, backoff_factor=2.0)
def execute_playwright_cdp_call(endpoint_url: str, method: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Executes a low-level CDP JSON-RPC command with retry."""
    import urllib.request
    req_body = json.dumps({"id": 1, "method": method, "params": params or {}}).encode("utf-8")
    req = urllib.request.Request(
        f"{endpoint_url.rstrip('/')}/json",
        data=req_body,
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))
