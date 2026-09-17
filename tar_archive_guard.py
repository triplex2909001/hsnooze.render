"""
HistorySnooze Director - Tarball Security Extraction Guard
Safe extraction preventing directory traversal attacks (CVE-2007-4559).
Rule <= 150 lines compliant.
"""

import ntpath
import os
import tarfile
from pathlib import Path


class SecurityError(Exception):
    """Raised when an archive member attempts directory traversal (CVE-2007-4559)."""
    pass


def safe_extract_tarball(archive_path: Path, destination_dir: Path) -> None:
    """
    Safely extracts a tar archive ensuring no member path escapes target directory (CVE-2007-4559).
    Validates regular files, directories, symlinks, and hardlinks against directory traversal.
    Blocks special device files (char, block, fifo), absolute paths, and chained link escapes.
    Strips dangerous permission bits and extracts member-by-member.
    """
    if not destination_dir or not str(destination_dir).strip():
        raise ValueError("destination_dir cannot be empty or whitespace")

    dest_resolved = Path(destination_dir).resolve()
    dest_resolved.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive_path, "r:*") as tar:
        for member in tar.getmembers():
            norm_name = os.path.normpath(member.name)
            if not member.name.strip() or norm_name in (".", ""):
                continue

            if "\0" in member.name:
                raise SecurityError(f"Null byte detected in archive member: '{member.name}'")

            if (
                member.name.startswith(("/", "\\"))
                or os.path.isabs(member.name)
                or bool(ntpath.splitdrive(member.name)[0])
            ):
                raise SecurityError(f"Absolute or drive path detected in archive member: '{member.name}'")

            if member.isdev() or member.ischr() or member.isblk() or member.isfifo():
                raise SecurityError(f"Special device file detected in archive member: '{member.name}'")

            target_path = (dest_resolved / member.name).resolve()
            try:
                target_path.relative_to(dest_resolved)
            except ValueError:
                raise SecurityError(
                    f"Directory traversal attack detected in archive member: '{member.name}' "
                    f"resolves to '{target_path}' which is outside destination '{dest_resolved}'"
                )

            if member.issym() or member.islnk():
                if (
                    member.linkname.startswith(("/", "\\"))
                    or os.path.isabs(member.linkname)
                    or bool(ntpath.splitdrive(member.linkname)[0])
                    or ("\0" in member.linkname)
                ):
                    raise SecurityError(
                        f"Absolute, drive, or malformed link target detected: '{member.name}' -> '{member.linkname}'"
                    )
                if member.issym():
                    link_target = (target_path.parent / member.linkname).resolve()
                else:
                    link_target = (dest_resolved / member.linkname).resolve()
                try:
                    link_target.relative_to(dest_resolved)
                except ValueError:
                    raise SecurityError(
                        f"Directory traversal attack in link target: '{member.name}' -> '{member.linkname}'"
                    )

            member.mode &= 0o777

            if hasattr(tarfile, "data_filter"):
                tar.extract(member, path=str(dest_resolved), filter="data")
            else:
                tar.extract(member, path=str(dest_resolved))
