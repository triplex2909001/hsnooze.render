"""
HistorySnooze Director - Central Configuration Module
Version: 1.2.0 (100% Online Serverless & Colab CLI Edition)
Single Source of Truth (SSOT) compliant configuration for 90-minute sleep documentary pipeline.
"""

import os
from dataclasses import dataclass
from typing import Dict, Tuple, List

# Video Rendering Specifications
WIDTH = 3840
HEIGHT = 2160
FPS = 30
ASPECT_RATIO = "16:9"
RESOLUTION = f"{WIDTH}x{HEIGHT}"
CPU_PRESET = "veryfast"  # Fast CPU encoding for Cloud Runners (GitHub Actions)

# Ken Burns ASMR Motion Parameters
ZOOM_START = 1.00
ZOOM_MAX = 1.04          # Maximum 4% zoom over 25-45s (~30-45s per beat)
INTER_PART_SILENCE_SEC = 5.0  # 5-second silence between parts
INTRA_SENTENCE_SILENCE_SEC = 1.0 # 1.0s silence between sentences
INTER_PARAGRAPH_SILENCE_SEC = 2.0 # 2.0s silence between paragraphs

# Story Structure
TOTAL_PARTS = 15
EXPECTED_MIN_BEATS = 150  # Scaled for 150-160 high-density beats (~10 beats/part)
EXPECTED_MAX_BEATS = 160
TARGET_BEATS_PER_PART = 10
BEAT_MIN_DURATION_SEC = 25.0
BEAT_MAX_DURATION_SEC = 45.0
CHUNK_MIN_WORDS = 15
CHUNK_MAX_WORDS = 35

# Google Workspace Integration IDs
PARENT_FOLDER_ID = "1UGkrUFQ62ghj1Lquy1HVsKIYR9nO60zf"  # 'historysnooze posts'
DASHBOARD_SHEET_ID = "1x2tcR4WyHXj_cvHjpPFWNsrtelkimUXJXNTw9hPbVeo"
SSOT_FOLDER_ID = "1aV8nBelLqXclJLScwKx-c4H-GMjtxGX0"
CODE_FOLDER_ID = "1mzeigkeg5vxapdHTQ8wHhYE8Y6gY3se9"

# Sleep Mood Parameters
DEFAULT_VIGNETTE = "none"
SLEEP_VIGNETTE = os.getenv("HSNOOZE_VIGNETTE", DEFAULT_VIGNETTE)  # "none" for uniform dimming with zero oval border

# Pipeline Status Lifecycle Flow
STATUS_FLOW = [
    "Proposed",    # New idea suggested
    "Pending",     # Approved by human, queued for agent execution
    "Script",      # Outline & 15-part script completed
    "Voiceover",   # 15 WAV audio files generated
    "JPEG",        # Automated keyframes generated (excluding Cover); Human-in-the-loop pause
    "Image",       # 150-160 4K keyframe images complete (including manual Cover), ready for render
    "Video",       # 15 chunks rendered & master video assembled
    "Ready",       # Passed all Gatekeepers (GK1-GK7), QA approved, ready for YouTube upload
    "Done"         # Successfully published to YouTube via Buffer API
]

# Image Generation Execution Modes
IMAGE_MODES = [
    "Automatic",   # Mode 1: Bot/VPS automatically sends prompts to ImageFX & downloads 4K images
    "Manual"       # Mode 2: Human manually generates images from combined_imageprompts.txt & uploads to keyframes/
]

# Online Execution Environments (0% VPS)
ONLINE_EXECUTION_MODES = [
    "github_actions", # 15 parallel matrix jobs on CPU (chunk-level immediate upload to GDrive)
    "google_colab"    # Colab CLI (T4/L4 GPU) sequential Part 1->15 with direct GDrive mount
]

# Voice Generation Execution Modes
VOICE_MODES = [
    "GHA",     # GitHub Actions: 15 parallel matrix jobs, chunk-level generation & immediate sync
    "Colab"    # Google Colab via colab-cli: T4/L4 GPU, sequential Part 1->15 with direct GDrive mount
]
DEFAULT_VOICE_MODE = "GHA"
# Voice Reference Configuration (Default Anchor Voice)
MAINVOICE_FOLDER_ID = "1n3CkuRYJlmeWR2V_rn8w3UT14ECQlc2v"
DEFAULT_VOICE_REF_ID = "1VC_eN0rnm9l2d4ilogn9B2GqWzzaV4fS"
DEFAULT_VOICE_NAME = "Milo (Calm, Soothing & Meditative)"
DEFAULT_VOICE_PATH = "mainvoice/voice_preview_milo.mp3"


# Video Generation Execution Modes
VIDEO_MODES = [
    "Colab",   # Google Colab: GPU T4/L4 accelerated FFmpeg with Ken Burns effect
    "GHA"      # GitHub Actions: 15 parallel matrix jobs on CPU
]
DEFAULT_VIDEO_MODE = "Colab"


# Google Sheet Column Schema (A - O)
COLUMNS = {
    "A": "Idea_ID",
    "B": "Historical_Figure",
    "C": "YouTube_Title",
    "D": "Status",
    "E": "GDrive",
    "F": "Outline",
    "G": "Script",
    "H": "Voice_Mode",   # "GHA" vs "Colab" (Default: "GHA")
    "I": "Voiceover",
    "J": "Image_Mode",   # "Automatic" vs "Manual" (Default: "Automatic")
    "K": "Image",
    "L": "Video_Mode",   # "Colab" vs "GHA" (Default: "Colab")
    "M": "Video",
    "N": "YouTube",      # Link YouTube video URL via Buffer API
    "O": "Updated_At"
}

# Gatekeeper Quality Thresholds
GK4_MIN_WAV_SIZE_KB = 10
GK4_RMS_THRESHOLD = 0.003
GK4_PEAK_THRESHOLD = 0.02
GK4_MIN_SEC_PER_WORD = 0.15

GK3_MIN_PROMPTS = EXPECTED_MIN_BEATS
GK3_MAX_PROMPTS = EXPECTED_MAX_BEATS
GK3_MIN_BEATS_PER_PART = TARGET_BEATS_PER_PART
GK6_MIN_KEYFRAMES = EXPECTED_MIN_BEATS
GK6_MIN_BEATS_PER_PART = TARGET_BEATS_PER_PART

GK5_MIN_IMAGE_SIZE_KB = 30
GK7_MIN_VIDEO_DURATION_MIN = 80
GK7_MAX_VIDEO_DURATION_MIN = 95
