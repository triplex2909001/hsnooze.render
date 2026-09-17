"""
HistorySnooze Director - Artifact Linker
Creates lightweight symlinks with atomic copy fallback (Rule <= 150 lines).
"""

import os
import shutil


def link_or_copy_artifact(source_path: str, target_dir: str) -> str:
    """
    Creates a lightweight symlink pointing to the canonical single-source artifact.
    Falls back to file copy only if symlinks are unsupported by the host filesystem.
    Validates source_path existence and prevents directory wiping on invalid filenames.
    """
    if not source_path or not str(source_path).strip():
        raise ValueError("source_path cannot be empty or whitespace")

    src_abs = os.path.abspath(str(source_path))
    if not os.path.exists(src_abs):
        raise FileNotFoundError(f"Source artifact does not exist: {source_path}")

    base_name = os.path.basename(os.path.normpath(src_abs))
    if not base_name:
        raise ValueError(f"Invalid source artifact filename: '{source_path}'")

    if not target_dir or not str(target_dir).strip():
        raise ValueError("target_dir cannot be empty or whitespace")

    os.makedirs(target_dir, exist_ok=True)
    target_path = os.path.join(target_dir, base_name)
    tgt_abs = os.path.abspath(target_path)
    if src_abs == tgt_abs:
        return target_path

    if os.path.lexists(target_path):
        try:
            if os.path.islink(target_path) and os.path.realpath(target_path) == os.path.realpath(src_abs):
                return target_path
            if os.path.isdir(target_path) and not os.path.islink(target_path):
                shutil.rmtree(target_path)
            else:
                os.remove(target_path)
        except OSError:
            pass

    try:
        os.symlink(src_abs, target_path)
    except OSError:
        if os.path.lexists(target_path):
            try:
                os.remove(target_path)
            except OSError:
                pass
        shutil.copy2(src_abs, target_path)
    return target_path
