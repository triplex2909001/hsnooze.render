"""
CLI Argument Parser for Colab Render Runner.
Adheres to Documents/Structure/01_ARCHITECTURE_CONSTRAINED_AI.md (Rule <= 150 lines/file).
"""

import argparse


def parse_colab_render_args() -> argparse.Namespace:
    """Parses command-line arguments for Colab video rendering."""
    parser = argparse.ArgumentParser(description="HistorySnooze Colab Video Render Runner")
    parser.add_argument("project_dir", nargs="?", default="", help="Path to project root directory")
    parser.add_argument("--project-dir", dest="project_dir_opt", type=str, default="", help="Alternative project dir option")
    parser.add_argument("--folder-id", type=str, default="", help="Google Drive Project Folder ID (GHA parity)")
    parser.add_argument("--parts", type=str, default="", help="Comma-separated parts to render (e.g. 1,2,3)")
    parser.add_argument("--cpu", action="store_true", help="Force CPU libx264 encoding")
    parser.add_argument("--workers", type=int, default=2, help="Max FFmpeg parallel workers (default: 2)")
    parser.add_argument("--mount-drive", action="store_true", help="Mount Colab Drive before running")
    parser.add_argument("--force", action="store_true", help="Force render even if Cover check warns")
    return parser.parse_args()
