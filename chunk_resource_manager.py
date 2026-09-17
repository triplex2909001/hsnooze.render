"""
HistorySnooze Director - Chunk Resource Manager
Monitors available RAM and clamps concurrency to prevent OOM / GPU errors (Rule <= 150 lines).
"""

import os
import subprocess
import sys
from typing import Optional


def get_available_ram_gb() -> float:
    """Returns available system RAM in gigabytes across Linux, macOS, and fallback."""
    try:
        import psutil
        return psutil.virtual_memory().available / (1024 ** 3)
    except ImportError:
        pass

    if os.path.exists("/proc/meminfo"):
        try:
            mem_info = {}
            with open("/proc/meminfo", "r") as f:
                for line in f:
                    parts = line.split(":")
                    if len(parts) == 2:
                        mem_info[parts[0].strip()] = int(parts[1].split()[0])
            if "MemAvailable" in mem_info:
                return mem_info["MemAvailable"] / (1024 * 1024)
            if "MemFree" in mem_info:
                return (mem_info["MemFree"] + mem_info.get("Buffers", 0) + mem_info.get("Cached", 0)) / (1024 * 1024)
            if "MemTotal" in mem_info:
                return (mem_info["MemTotal"] / (1024 * 1024)) * 0.7
        except Exception:
            pass

    if sys.platform == "darwin":
        try:
            res = subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True, check=True)
            total_bytes = int(res.stdout.strip())
            return (total_bytes / (1024 ** 3)) * 0.6
        except Exception:
            pass

    return 8.0


def get_safe_max_workers(
    requested_workers: int = 1,
    force_cpu: bool = False,
    ram_gb: Optional[float] = None
) -> int:
    """Clamps worker concurrency based on system RAM (min 3.5GB/worker) and NVENC limit (max 2)."""
    try:
        requested_workers = int(requested_workers)
    except (ValueError, TypeError):
        requested_workers = 1

    if requested_workers < 1:
        requested_workers = 1

    mod_chunk = sys.modules.get("chunk_renderer")
    ram_fn = getattr(mod_chunk, "get_available_ram_gb", get_available_ram_gb) if mod_chunk else get_available_ram_gb
    avail_ram_gb = ram_gb if ram_gb is not None else ram_fn()
    ram_workers = max(1, int(avail_ram_gb // 3.5))

    mod_kb = sys.modules.get("kenburns_asmr")
    from kenburns_asmr import check_nvenc_available
    nvenc_fn = getattr(mod_kb, "check_nvenc_available", check_nvenc_available) if mod_kb else check_nvenc_available

    has_nvenc = (not force_cpu) and nvenc_fn()
    if has_nvenc:
        max_allowed = min(requested_workers, 2, ram_workers)
    else:
        cpu_count = os.cpu_count() or 2
        cpu_workers = max(1, cpu_count - 1 if cpu_count > 2 else cpu_count)
        max_allowed = min(requested_workers, ram_workers, cpu_workers)

    return max(1, max_allowed)
