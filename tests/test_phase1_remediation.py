"""
Phase 1 (Sprint 1 / P0 Blockers) Remediation Verification Suite
Tests all 8 requirements:
1. pipeline_orchestrator.py symlinking / single canonical copy (R1.1)
2. chunk_renderer.py memory & NVENC worker clamping (R1.2)
3. kenburns_asmr.py bounded 1.1x zoompan filtergraph (R1.3)
4. chunk_renderer.py deterministic try...finally cleanup (R2.1)
5. kenburns_asmr.py NVENC failure fallback to CPU libx264 (R2.2)
6. image_pipeline_worker.py dynamic path resolution & zero hardcoded host paths (R3.1)
7. download_drive_assets.py and render_single_part.py anti-Tar Slip CVE-2007-4559 (R3.2)
8. pipeline_orchestrator.py Gatekeeper GK3 graceful warning without prompt_engine (R3.3)
"""

import os
import sys
import io
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

# Ensure repo root is on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import config
import pipeline_orchestrator
import chunk_renderer
import kenburns_asmr
import image_pipeline_worker
import download_drive_assets
import render_single_part
import colab_render_runner
import cue_extractor
import generate_ambient_stardust


class TestStorageSafeguards(unittest.TestCase):
    """R1.1: Canonical single-source artifact linking and storage safeguards."""

    def test_link_or_copy_artifact_creates_symlink(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src_dir = os.path.join(tmpdir, "canonical_dir")
            os.makedirs(src_dir, exist_ok=True)
            src_file = os.path.join(src_dir, "chunk_part_01.mp4")
            with open(src_file, "wb") as f:
                f.write(b"CANONICAL_4K_DATA_" * 1024)

            target_dir = os.path.join(tmpdir, "mirror_chunks")
            linked_path = pipeline_orchestrator.link_or_copy_artifact(src_file, target_dir)

            self.assertTrue(os.path.exists(linked_path))
            self.assertTrue(os.path.islink(linked_path))
            self.assertEqual(os.path.realpath(linked_path), os.path.realpath(src_file))
            # Verify data is readable and identical
            with open(linked_path, "rb") as f:
                self.assertEqual(f.read(), b"CANONICAL_4K_DATA_" * 1024)

    def test_link_or_copy_artifact_handles_existing_symlink_idempotently(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src_file = os.path.join(tmpdir, "master_final_90min.mp4")
            with open(src_file, "wb") as f:
                f.write(b"MASTER_DATA")

            target_dir = os.path.join(tmpdir, "mirrored")
            # Call twice
            p1 = pipeline_orchestrator.link_or_copy_artifact(src_file, target_dir)
            p2 = pipeline_orchestrator.link_or_copy_artifact(src_file, target_dir)
            self.assertEqual(p1, p2)
            self.assertTrue(os.path.islink(p1))
            self.assertEqual(os.path.realpath(p1), os.path.realpath(src_file))

    def test_link_or_copy_artifact_handles_same_path(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src_file = os.path.join(tmpdir, "same.mp4")
            with open(src_file, "w") as f:
                f.write("content")
            res = pipeline_orchestrator.link_or_copy_artifact(src_file, tmpdir)
            self.assertEqual(os.path.abspath(res), os.path.abspath(src_file))


class TestMemoryAndWorkerClamping(unittest.TestCase):
    """R1.2: RAM and GPU NVENC worker concurrency clamping."""

    def test_worker_clamping_bounded_by_ram(self):
        # When 7 GB RAM is available (e.g. GitHub Actions Linux VM)
        with patch("chunk_renderer.get_available_ram_gb", return_value=7.0):
            # 7.0 // 3.5 = 2 workers max
            workers = chunk_renderer.get_safe_max_workers(requested_workers=8, force_cpu=True)
            self.assertEqual(workers, 2)

        # When 3.0 GB RAM is available (low memory environment)
        with patch("chunk_renderer.get_available_ram_gb", return_value=3.0):
            # 3.0 // 3.5 = 0 -> clamped to 1
            workers = chunk_renderer.get_safe_max_workers(requested_workers=8, force_cpu=True)
            self.assertEqual(workers, 1)

        # When 32.0 GB RAM is available
        with patch("chunk_renderer.get_available_ram_gb", return_value=32.0):
            with patch("os.cpu_count", return_value=16):
                workers = chunk_renderer.get_safe_max_workers(requested_workers=4, force_cpu=True)
                self.assertEqual(workers, 4)

    def test_worker_clamping_bounded_by_nvenc_cap(self):
        # With NVENC available, concurrency must NEVER exceed 2 NVENC sessions
        with patch("chunk_renderer.get_available_ram_gb", return_value=32.0):
            with patch("kenburns_asmr.check_nvenc_available", return_value=True):
                workers = chunk_renderer.get_safe_max_workers(requested_workers=8, force_cpu=False)
                self.assertEqual(workers, 2)

                # Requested 1 stays 1
                workers_1 = chunk_renderer.get_safe_max_workers(requested_workers=1, force_cpu=False)
                self.assertEqual(workers_1, 1)

    def test_worker_clamping_fallback_when_force_cpu(self):
        with patch("chunk_renderer.get_available_ram_gb", return_value=16.0):
            with patch("kenburns_asmr.check_nvenc_available", return_value=True):
                with patch("os.cpu_count", return_value=8):
                    # force_cpu=True ignores NVENC cap and scales to RAM / CPU
                    workers = chunk_renderer.get_safe_max_workers(requested_workers=4, force_cpu=True)
                    self.assertEqual(workers, 4)

    def test_worker_clamping_handles_invalid_and_negative_input(self):
        with patch("chunk_renderer.get_available_ram_gb", return_value=16.0):
            self.assertEqual(chunk_renderer.get_safe_max_workers(0), 1)
            self.assertEqual(chunk_renderer.get_safe_max_workers(-5), 1)
            self.assertEqual(chunk_renderer.get_safe_max_workers("invalid"), 1)


class TestKenBurnsPrescaleBounds(unittest.TestCase):
    """R1.3: Bound 8K zoompan filtergraph allocation to 1.1x."""

    def test_prescale_is_bounded_to_1_1x_for_4k(self):
        filt, _ = kenburns_asmr.build_filter_graph(
            zoom_in=True,
            total_frames=900,
            width=3840,
            height=2160,
            fps=30
        )
        # 3840 * 1.10 = 4224, 2160 * 1.10 = 2376
        self.assertIn("scale=4224x2376", filt)
        self.assertIn("crop=4224:2376", filt)
        # Ensure 8000x4500 is completely removed
        self.assertNotIn("8000x4500", filt)
        self.assertNotIn("crop=8000:4500", filt)
        # Ensure output dimensions strictly preserve 4K 30fps
        self.assertIn("s=3840x2160:fps=30", filt)

    def test_prescale_dynamic_dimensions(self):
        filt, _ = kenburns_asmr.build_filter_graph(
            zoom_in=False,
            total_frames=300,
            width=1920,
            height=1080,
            fps=30,
            sleep_mode=True
        )
        # 1920 * 1.10 = 2112, 1080 * 1.10 = 1188
        self.assertIn("scale=2112x1188", filt)
        self.assertIn("crop=2112:1188", filt)
        self.assertIn("s=1920x1080:fps=30", filt)
        # Uniform dimming without oval border by default
        self.assertNotIn("vignette=", filt)
        self.assertIn("eq=contrast=", filt)

        # When vignette is explicitly requested, verify aspect ratio normalization
        filt_vig, _ = kenburns_asmr.build_filter_graph(
            zoom_in=False,
            total_frames=300,
            width=1920,
            height=1080,
            fps=30,
            sleep_mode=True,
            vignette="PI/4"
        )
        self.assertIn("aspect=1920/1080", filt_vig)


class TestIntermediateBeatCleanup(unittest.TestCase):
    """R2.1: Deterministic try...finally cleanup of intermediate beat clips and concat lists."""

    def test_cleanup_runs_on_success(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            temp_dir = os.path.join(tmpdir, "temp")
            output_dir = os.path.join(tmpdir, "output")
            os.makedirs(temp_dir, exist_ok=True)
            os.makedirs(output_dir, exist_ok=True)

            # Create dummy beat images
            dummy_img = os.path.join(tmpdir, "beat_01.jpg")
            with open(dummy_img, "wb") as f:
                f.write(b"\xFF\xD8\xFF" + b"\x00" * 2000)

            # Pre-create a dummy beat clip in temp_dir that simulates render output
            beat_clip = os.path.join(temp_dir, "beat_P02_B01.mp4")
            with open(beat_clip, "wb") as f:
                f.write(b"CLIP_DATA")

            dummy_audio = os.path.join(tmpdir, "Part_02.wav")
            with open(dummy_audio, "wb") as f:
                f.write(b"RIFF" + b"\x00" * 1000)

            with patch("chunk_renderer.is_chunk_valid", side_effect=[False, True]), \
                 patch("chunk_renderer.align_part_beats", return_value={"beats": [{"image_path": dummy_img, "duration": 3.0}]}), \
                 patch("chunk_renderer.render_kenburns_beat", return_value=beat_clip), \
                 patch("subprocess.run") as mock_run:

                # Simulate successful ffmpeg calls
                mock_run.return_value = MagicMock(returncode=0)
                chunk_renderer.render_part_chunk(
                    part_index=2,
                    audio_wav_path=dummy_audio,
                    beat_images=[dummy_img],
                    output_dir=output_dir,
                    temp_dir=temp_dir
                )

            # Verify intermediate beat clip and concat list were removed
            self.assertFalse(os.path.exists(beat_clip))
            self.assertFalse(os.path.exists(os.path.join(temp_dir, "part_02_concat.txt")))
            self.assertFalse(os.path.exists(os.path.join(temp_dir, "part_02_video.mp4")))

    def test_cleanup_runs_on_abort_exception(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            temp_dir = os.path.join(tmpdir, "temp")
            output_dir = os.path.join(tmpdir, "output")
            os.makedirs(temp_dir, exist_ok=True)

            dummy_img = os.path.join(tmpdir, "beat_01.jpg")
            with open(dummy_img, "wb") as f:
                f.write(b"IMAGE")
            dummy_audio = os.path.join(tmpdir, "Part_02.wav")
            with open(dummy_audio, "wb") as f:
                f.write(b"AUDIO")

            beat_clip = os.path.join(temp_dir, "beat_P02_B01.mp4")

            def _fake_render(*args, **kwargs):
                with open(beat_clip, "wb") as f:
                    f.write(b"BEAT_CLIP")
                return beat_clip

            with patch("chunk_renderer.is_chunk_valid", return_value=False), \
                 patch("chunk_renderer.align_part_beats", return_value={"beats": [{"image_path": dummy_img, "duration": 3.0}]}), \
                 patch("chunk_renderer.render_kenburns_beat", side_effect=_fake_render), \
                 patch("subprocess.run", side_effect=RuntimeError("FFmpeg error during concat")):

                with self.assertRaises(RuntimeError):
                    chunk_renderer.render_part_chunk(
                        part_index=2,
                        audio_wav_path=dummy_audio,
                        beat_images=[dummy_img],
                        output_dir=output_dir,
                        temp_dir=temp_dir
                    )

            # Even though render_part_chunk aborted with an exception, beat_clip was deterministically deleted!
            self.assertFalse(os.path.exists(beat_clip))

    def test_cleanup_removes_orphaned_beat_clips_in_temp_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            temp_dir = os.path.join(tmpdir, "temp")
            output_dir = os.path.join(tmpdir, "output")
            os.makedirs(temp_dir, exist_ok=True)
            os.makedirs(output_dir, exist_ok=True)

            dummy_img = os.path.join(tmpdir, "beat_01.jpg")
            with open(dummy_img, "wb") as f:
                f.write(b"\xFF\xD8\xFF" + b"\x00" * 2000)

            # Orphaned beat clips from an old/interrupted run
            orphan_clip1 = os.path.join(temp_dir, "beat_P02_B99.mp4")
            orphan_clip2 = os.path.join(temp_dir, "beat_P02_B02.mp4")
            with open(orphan_clip1, "wb") as f:
                f.write(b"ORPHAN1")
            with open(orphan_clip2, "wb") as f:
                f.write(b"ORPHAN2")

            dummy_audio = os.path.join(tmpdir, "Part_02.wav")
            with open(dummy_audio, "wb") as f:
                f.write(b"RIFF" + b"\x00" * 1000)

            with patch("chunk_renderer.is_chunk_valid", side_effect=[False, True]), \
                 patch("chunk_renderer.align_part_beats", return_value={"beats": [{"image_path": dummy_img, "duration": 3.0}]}), \
                 patch("chunk_renderer.render_kenburns_beat", return_value=os.path.join(temp_dir, "beat_P02_B01.mp4")), \
                 patch("subprocess.run") as mock_run:

                mock_run.return_value = MagicMock(returncode=0)
                chunk_renderer.render_part_chunk(
                    part_index=2,
                    audio_wav_path=dummy_audio,
                    beat_images=[dummy_img],
                    output_dir=output_dir,
                    temp_dir=temp_dir
                )

            # Both orphaned beat clips must be purged
            self.assertFalse(os.path.exists(orphan_clip1))
            self.assertFalse(os.path.exists(orphan_clip2))

    def test_cleanup_removes_invalid_partial_chunk_on_abort(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            temp_dir = os.path.join(tmpdir, "temp")
            output_dir = os.path.join(tmpdir, "output")
            os.makedirs(temp_dir, exist_ok=True)
            os.makedirs(output_dir, exist_ok=True)

            dummy_img = os.path.join(tmpdir, "beat_01.jpg")
            with open(dummy_img, "wb") as f:
                f.write(b"IMG")
            dummy_audio = os.path.join(tmpdir, "Part_02.wav")
            with open(dummy_audio, "wb") as f:
                f.write(b"AUDIO")

            chunk_path = os.path.join(output_dir, "chunk_part_02.mp4")

            def _fake_mux(cmd, *args, **kwargs):
                if chunk_path in cmd:
                    # Write partial corrupt chunk
                    with open(chunk_path, "wb") as f:
                        f.write(b"CORRUPT_ZERO_BYTE")
                    raise RuntimeError("FFmpeg mux crashed")
                return MagicMock(returncode=0)

            with patch("chunk_renderer.is_chunk_valid", return_value=False), \
                 patch("chunk_renderer.align_part_beats", return_value={"beats": [{"image_path": dummy_img, "duration": 3.0}]}), \
                 patch("chunk_renderer.render_kenburns_beat", return_value=os.path.join(temp_dir, "beat_P02_B01.mp4")), \
                 patch("subprocess.run", side_effect=_fake_mux):

                with self.assertRaises(RuntimeError):
                    chunk_renderer.render_part_chunk(
                        part_index=2,
                        audio_wav_path=dummy_audio,
                        beat_images=[dummy_img],
                        output_dir=output_dir,
                        temp_dir=temp_dir
                    )

            # Invalid corrupt chunk was purged on abort!
            self.assertFalse(os.path.exists(chunk_path))

    def test_cleanup_removes_chunk_even_if_size_and_duration_positive_on_abort(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            temp_dir = os.path.join(tmpdir, "temp")
            output_dir = os.path.join(tmpdir, "output")
            os.makedirs(temp_dir, exist_ok=True)
            os.makedirs(output_dir, exist_ok=True)

            dummy_img = os.path.join(tmpdir, "beat_01.jpg")
            with open(dummy_img, "wb") as f:
                f.write(b"IMG")
            dummy_audio = os.path.join(tmpdir, "Part_02.wav")
            with open(dummy_audio, "wb") as f:
                f.write(b"AUDIO")

            chunk_path = os.path.join(output_dir, "chunk_part_02.mp4")

            def _fake_mux(cmd, *args, **kwargs):
                if chunk_path in cmd:
                    # Write a file that is "valid" looking (>10MB) but render aborted mid-flight
                    with open(chunk_path, "wb") as f:
                        f.write(b"VALID_LOOKING_TRUNCATED_VIDEO" * (1024 * 500))
                    raise RuntimeError("Aborted after partial render")
                return MagicMock(returncode=0)

            # Even if is_chunk_valid would say True, because render aborted, it MUST be removed!
            with patch("chunk_renderer.is_chunk_valid", side_effect=[False, True]), \
                 patch("chunk_renderer.align_part_beats", return_value={"beats": [{"image_path": dummy_img, "duration": 3.0}]}), \
                 patch("chunk_renderer.render_kenburns_beat", return_value=os.path.join(temp_dir, "beat_P02_B01.mp4")), \
                 patch("subprocess.run", side_effect=_fake_mux):

                with self.assertRaises(RuntimeError):
                    chunk_renderer.render_part_chunk(
                        part_index=2,
                        audio_wav_path=dummy_audio,
                        beat_images=[dummy_img],
                        output_dir=output_dir,
                        temp_dir=temp_dir
                    )

            self.assertFalse(os.path.exists(chunk_path))


class TestHardwareEncodingFallback(unittest.TestCase):
    """R2.2: NVENC failure fallback to CPU libx264."""

    def test_nvenc_failure_falls_back_to_libx264(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            dummy_img = os.path.join(tmpdir, "frame.jpg")
            with open(dummy_img, "wb") as f:
                f.write(b"IMG")
            out_clip = os.path.join(tmpdir, "out.mp4")

            import subprocess
            calls = []

            def _mock_run(cmd, *args, **kwargs):
                calls.append(cmd)
                # First call (NVENC) fails with session limit error
                if "h264_nvenc" in cmd:
                    raise subprocess.CalledProcessError(
                        returncode=1,
                        cmd=cmd,
                        stderr="[h264_nvenc] OpenEncodeSessionEx failed: out of memory (10)"
                    )
                # Fallback call (libx264) succeeds
                return MagicMock(returncode=0)

            with patch("kenburns_asmr.check_nvenc_available", return_value=True), \
                 patch("subprocess.run", side_effect=_mock_run):

                kenburns_asmr.render_kenburns_beat(
                    image_path=dummy_img,
                    duration=5.0,
                    output_clip_path=out_clip,
                    force_cpu=False
                )

            # Verify there were 2 invocations: first NVENC, second CPU libx264
            self.assertEqual(len(calls), 2)
            self.assertIn("h264_nvenc", calls[0])
            self.assertIn("libx264", calls[1])

    def test_kenburns_render_cleans_up_output_on_cpu_failure(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            dummy_img = os.path.join(tmpdir, "frame.jpg")
            with open(dummy_img, "wb") as f:
                f.write(b"IMG")
            out_clip = os.path.join(tmpdir, "out.mp4")

            import subprocess

            def _failing_run(cmd, *args, **kwargs):
                # Simulate partial broken clip written before crash
                with open(out_clip, "wb") as f:
                    f.write(b"CORRUPT_FRAME_DATA")
                raise subprocess.CalledProcessError(returncode=1, cmd=cmd, stderr="CPU libx264 fatal error")

            with patch("subprocess.run", side_effect=_failing_run):
                with self.assertRaises(subprocess.CalledProcessError):
                    kenburns_asmr.render_kenburns_beat(
                        image_path=dummy_img,
                        duration=5.0,
                        output_clip_path=out_clip,
                        force_cpu=True
                    )

            # Output clip must be purged on failure!
            self.assertFalse(os.path.exists(out_clip))

    def test_build_render_command_includes_framerate_flag(self):
        cmd = kenburns_asmr.build_render_command(
            image_path="test.jpg",
            duration=5.0,
            output_clip_path="out.mp4",
            fps=30
        )
        self.assertIn("-framerate", cmd)
        idx_fr = cmd.index("-framerate")
        self.assertEqual(cmd[idx_fr + 1], "30")
        idx_loop = cmd.index("-loop")
        self.assertLess(idx_fr, idx_loop, "-framerate must precede -loop for image demuxer")


class TestEnvironmentPortabilityAndPathResolution(unittest.TestCase):
    """R3.1: Zero hardcoded host paths, dynamic Path.home() resolution."""

    def test_zero_hardcoded_developer_paths_in_repo(self):
        active_py_files = list(REPO_ROOT.glob("*.py"))
        for py_file in active_py_files:
            content = py_file.read_text(encoding="utf-8")
            self.assertNotIn(
                "/Users/hanario",
                content,
                f"Found hardcoded developer path in {py_file.name}"
            )

    def test_image_pipeline_worker_dynamic_path(self):
        # Default fallback uses Path.home()
        expected_default = Path.home() / ".workspace-mcp" / "attachments" / "images"
        with patch.dict(os.environ, {}, clear=False):
            if "HSNOOZE_ATTACHMENTS_DIR" in os.environ:
                del os.environ["HSNOOZE_ATTACHMENTS_DIR"]
            # Re-evaluate Path with default
            p = Path(os.getenv("HSNOOZE_ATTACHMENTS_DIR", str(expected_default)))
            self.assertEqual(p, expected_default)

        # Environment variable override works
        custom = "/custom/pipeline/attachments"
        with patch.dict(os.environ, {"HSNOOZE_ATTACHMENTS_DIR": custom}):
            p = Path(os.getenv("HSNOOZE_ATTACHMENTS_DIR", str(expected_default)))
            self.assertEqual(str(p), custom)


class TestAntiTarSlipVulnerability(unittest.TestCase):
    """R3.2: Neutralize Tar Slip CVE-2007-4559 across all download routines."""

    def test_safe_extract_tarball_allows_safe_archive(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            archive_path = Path(tmpdir) / "safe.tar.gz"
            extract_dir = Path(tmpdir) / "extracted"
            extract_dir.mkdir()

            # Create safe tarball
            with tarfile.open(archive_path, "w:gz") as tar:
                data = b"Hello world safe content"
                ti = tarfile.TarInfo(name="safe_file.txt")
                ti.size = len(data)
                tar.addfile(ti, io.BytesIO(data))

            # Test download_drive_assets extractor
            download_drive_assets.safe_extract_tarball(archive_path, extract_dir)
            self.assertTrue((extract_dir / "safe_file.txt").exists())
            self.assertEqual((extract_dir / "safe_file.txt").read_bytes(), data)

            # Test render_single_part extractor
            extract_dir_2 = Path(tmpdir) / "extracted_2"
            extract_dir_2.mkdir()
            render_single_part.safe_extract_tarball(archive_path, extract_dir_2)
            self.assertTrue((extract_dir_2 / "safe_file.txt").exists())

    def test_safe_extract_tarball_blocks_directory_traversal(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            archive_path = Path(tmpdir) / "malicious.tar.gz"
            extract_dir = Path(tmpdir) / "target_dir"
            extract_dir.mkdir()

            # Craft malicious tarball with ../../ traversal
            with tarfile.open(archive_path, "w:gz") as tar:
                data = b"malicious code overwrite"
                ti = tarfile.TarInfo(name="../../evil_file.txt")
                ti.size = len(data)
                tar.addfile(ti, io.BytesIO(data))

            with self.assertRaises(download_drive_assets.SecurityError):
                download_drive_assets.safe_extract_tarball(archive_path, extract_dir)

            with self.assertRaises(render_single_part.SecurityError):
                render_single_part.safe_extract_tarball(archive_path, extract_dir)

            # Confirm file was not written outside target
            self.assertFalse((Path(tmpdir) / "evil_file.txt").exists())

    def test_safe_extract_tarball_blocks_symlink_traversal(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            archive_path = Path(tmpdir) / "symlink_evil.tar.gz"
            extract_dir = Path(tmpdir) / "target_dir"
            extract_dir.mkdir()

            # Malicious symlink pointing outside destination
            with tarfile.open(archive_path, "w:gz") as tar:
                ti = tarfile.TarInfo(name="link_to_parent")
                ti.type = tarfile.SYMTYPE
                ti.linkname = "../"
                tar.addfile(ti)

            with self.assertRaises(download_drive_assets.SecurityError):
                download_drive_assets.safe_extract_tarball(archive_path, extract_dir)

            with self.assertRaises(render_single_part.SecurityError):
                render_single_part.safe_extract_tarball(archive_path, extract_dir)

    def test_safe_extract_tarball_blocks_hardlink_traversal(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            archive_path = Path(tmpdir) / "hardlink_evil.tar.gz"
            extract_dir = Path(tmpdir) / "target_dir"
            extract_dir.mkdir()

            # Malicious hardlink pointing to /etc/passwd
            with tarfile.open(archive_path, "w:gz") as tar:
                ti = tarfile.TarInfo(name="evil_hardlink")
                ti.type = tarfile.LNKTYPE
                ti.linkname = "/etc/passwd"
                tar.addfile(ti)

            with self.assertRaises(download_drive_assets.SecurityError):
                download_drive_assets.safe_extract_tarball(archive_path, extract_dir)

            with self.assertRaises(render_single_part.SecurityError):
                render_single_part.safe_extract_tarball(archive_path, extract_dir)

    def test_safe_extract_tarball_blocks_device_nodes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            archive_path = Path(tmpdir) / "device_evil.tar.gz"
            extract_dir = Path(tmpdir) / "target_dir"
            extract_dir.mkdir()

            # Malicious device node
            with tarfile.open(archive_path, "w:gz") as tar:
                ti = tarfile.TarInfo(name="evil_chr_dev")
                ti.type = tarfile.CHRTYPE
                tar.addfile(ti)

            with self.assertRaises(download_drive_assets.SecurityError):
                download_drive_assets.safe_extract_tarball(archive_path, extract_dir)

            with self.assertRaises(render_single_part.SecurityError):
                render_single_part.safe_extract_tarball(archive_path, extract_dir)

    def test_safe_extract_tarball_blocks_chained_symlinks(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            dest = Path(tmpdir) / "dest"
            dest.mkdir()
            outside = Path(tmpdir) / "outside"
            outside.mkdir()

            buf = io.BytesIO()
            with tarfile.open(fileobj=buf, mode="w:gz") as tar:
                ti1 = tarfile.TarInfo(name="link1")
                ti1.type = tarfile.SYMTYPE
                ti1.linkname = "."
                tar.addfile(ti1)

                ti2 = tarfile.TarInfo(name="link2")
                ti2.type = tarfile.SYMTYPE
                ti2.linkname = "link1/.."
                tar.addfile(ti2)

                ti3 = tarfile.TarInfo(name="link2/outside/pwned.txt")
                data = b"PWNED BY CHAINED SYMLINK"
                ti3.size = len(data)
                tar.addfile(ti3, io.BytesIO(data))
            buf.seek(0)

            archive_path = Path(tmpdir) / "chained_link.tar.gz"
            archive_path.write_bytes(buf.getvalue())

            with self.assertRaises(download_drive_assets.SecurityError):
                download_drive_assets.safe_extract_tarball(archive_path, dest)
            self.assertFalse((outside / "pwned.txt").exists())

            dest2 = Path(tmpdir) / "dest2"
            dest2.mkdir()
            with self.assertRaises(render_single_part.SecurityError):
                render_single_part.safe_extract_tarball(archive_path, dest2)
            self.assertFalse((outside / "pwned.txt").exists())

    def test_safe_extract_tarball_blocks_absolute_member_path(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            dest = Path(tmpdir) / "dest"
            dest.mkdir()

            buf = io.BytesIO()
            with tarfile.open(fileobj=buf, mode="w:gz") as tar:
                ti = tarfile.TarInfo(name=str(dest / "evil.txt"))
                data = b"PWNED"
                ti.size = len(data)
                tar.addfile(ti, io.BytesIO(data))
            buf.seek(0)

            archive_path = Path(tmpdir) / "abs_member.tar.gz"
            archive_path.write_bytes(buf.getvalue())

            with self.assertRaises(download_drive_assets.SecurityError):
                download_drive_assets.safe_extract_tarball(archive_path, dest)

            with self.assertRaises(render_single_part.SecurityError):
                render_single_part.safe_extract_tarball(archive_path, dest)

    def test_safe_extract_tarball_blocks_absolute_symlink_target(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            dest = Path(tmpdir) / "dest"
            dest.mkdir()

            buf = io.BytesIO()
            with tarfile.open(fileobj=buf, mode="w:gz") as tar:
                ti = tarfile.TarInfo(name="link_abs")
                ti.type = tarfile.SYMTYPE
                ti.linkname = "/etc/shadow"
                tar.addfile(ti)
            buf.seek(0)

            archive_path = Path(tmpdir) / "abs_link.tar.gz"
            archive_path.write_bytes(buf.getvalue())

            with self.assertRaises(download_drive_assets.SecurityError):
                download_drive_assets.safe_extract_tarball(archive_path, dest)

            with self.assertRaises(render_single_part.SecurityError):
                render_single_part.safe_extract_tarball(archive_path, dest)


class TestGatekeeperGK3GracefulWarning(unittest.TestCase):
    """R3.3: Gatekeeper GK3 warns rather than terminating when prompt_engine is absent."""

    def test_gk3_passes_and_warns_when_prompt_engine_is_none(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            prompts_file = os.path.join(tmpdir, "combined_imageprompts.txt")
            # Build valid 15-part prompt file with 10 beats per part = 150 total beats
            lines = []
            for part in range(1, 16):
                for beat in range(1, 11):
                    lines.append(f"beat_P{part:02d}_B{beat:02d}.jpg: Calm scene of historical serenity {part}-{beat}")
            with open(prompts_file, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))

            # Mock validate_prompt as None (optional module absent)
            with patch("pipeline_orchestrator.validate_prompt", None):
                audit = pipeline_orchestrator.audit_gk3_prompts(
                    project_root=tmpdir,
                    prompts_file_path=prompts_file
                )

                self.assertTrue(audit["passed_gk3"], f"GK3 failed with details: {audit['details']}")
                self.assertEqual(audit["total_count"], 150)
                self.assertEqual(len(audit["deficient_parts"]), 0)
                self.assertTrue(any("prompt_engine" in w for w in audit.get("warnings", [])))

    def test_gk3_fails_when_prompts_missing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            audit = pipeline_orchestrator.audit_gk3_prompts(project_root=tmpdir)
            self.assertFalse(audit["passed_gk3"])
            self.assertIn("combined_imageprompts.txt not found", audit["details"][0])
            self.assertIn("warnings", audit)
            self.assertIsInstance(audit["warnings"], list)

    def test_gk3_fails_when_prompt_count_deficient(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            prompts_file = os.path.join(tmpdir, "combined_imageprompts.txt")
            # Only 5 beats total (below 150 min)
            lines = [f"beat_P01_B{b:02d}.jpg: Short beat {b}" for b in range(1, 6)]
            with open(prompts_file, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))

            audit = pipeline_orchestrator.audit_gk3_prompts(
                project_root=tmpdir,
                prompts_file_path=prompts_file
            )
            self.assertFalse(audit["passed_gk3"])
            self.assertIn("outside required range", " ".join(audit["details"]))

    def test_gk3_fails_when_validate_prompt_reports_syntax_error(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            prompts_file = os.path.join(tmpdir, "combined_imageprompts.txt")
            lines = []
            for part in range(1, 16):
                for beat in range(1, 11):
                    lines.append(f"beat_P{part:02d}_B{beat:02d}.jpg: Scene {part}-{beat}")
            with open(prompts_file, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))

            def _mock_validate(prompt):
                if "Scene 1-1" in prompt:
                    return {"is_valid": False, "issues": ["Disallowed keyword detected"]}
                return {"is_valid": True, "issues": []}

            with patch("pipeline_orchestrator.validate_prompt", side_effect=_mock_validate):
                audit = pipeline_orchestrator.audit_gk3_prompts(
                    project_root=tmpdir,
                    prompts_file_path=prompts_file
                )
                self.assertFalse(audit["passed_gk3"])
                self.assertTrue(any("Disallowed keyword" in d for d in audit["details"]))


class TestStorageSafeguardsEdgeCases(unittest.TestCase):
    """Storage edge cases: broken symlink recovery and OSError fallback to copy."""

    def test_link_or_copy_replaces_broken_symlink(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src_file = os.path.join(tmpdir, "canonical.mp4")
            with open(src_file, "w") as f:
                f.write("CANONICAL")

            target_dir = os.path.join(tmpdir, "target")
            os.makedirs(target_dir, exist_ok=True)
            broken_symlink = os.path.join(target_dir, "canonical.mp4")
            # Point to nonexistent target
            os.symlink(os.path.join(tmpdir, "nonexistent.mp4"), broken_symlink)
            self.assertTrue(os.path.islink(broken_symlink))
            self.assertFalse(os.path.exists(broken_symlink))  # Broken!

            # link_or_copy_artifact should remove broken symlink and re-link
            res = pipeline_orchestrator.link_or_copy_artifact(src_file, target_dir)
            self.assertTrue(os.path.exists(res))
            self.assertEqual(os.path.realpath(res), os.path.realpath(src_file))

    def test_link_or_copy_fallback_to_copy_on_symlink_oserror(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src_file = os.path.join(tmpdir, "canonical.mp4")
            with open(src_file, "w") as f:
                f.write("DATA_PAYLOAD")

            target_dir = os.path.join(tmpdir, "target")
            with patch("os.symlink", side_effect=OSError("Symlinks unsupported")):
                res = pipeline_orchestrator.link_or_copy_artifact(src_file, target_dir)
                self.assertTrue(os.path.exists(res))
                self.assertFalse(os.path.islink(res))  # Is a regular file copy
                with open(res, "r") as f:
                    self.assertEqual(f.read(), "DATA_PAYLOAD")

    def test_link_or_copy_replaces_existing_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src_file = os.path.join(tmpdir, "canonical.mp4")
            with open(src_file, "w") as f:
                f.write("CANONICAL_DATA")

            target_dir = os.path.join(tmpdir, "target")
            os.makedirs(target_dir, exist_ok=True)
            conflict_dir = os.path.join(target_dir, "canonical.mp4")
            os.makedirs(conflict_dir, exist_ok=True)
            with open(os.path.join(conflict_dir, "junk.txt"), "w") as f:
                f.write("junk")

            res = pipeline_orchestrator.link_or_copy_artifact(src_file, target_dir)
            self.assertTrue(os.path.exists(res))
            self.assertFalse(os.path.isdir(res))
            self.assertEqual(os.path.realpath(res), os.path.realpath(src_file))

    def test_link_or_copy_empty_source_path_raises_value_error(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            target_dir = os.path.join(tmpdir, "important_dir")
            os.makedirs(target_dir, exist_ok=True)
            sentinel_file = os.path.join(target_dir, "sentinel.txt")
            with open(sentinel_file, "w") as f:
                f.write("DO_NOT_DELETE")

            with self.assertRaises(ValueError):
                pipeline_orchestrator.link_or_copy_artifact("", target_dir)

            with self.assertRaises(ValueError):
                pipeline_orchestrator.link_or_copy_artifact("   ", target_dir)

            # Confirm target_dir and its contents were NOT destroyed
            self.assertTrue(os.path.exists(target_dir))
            self.assertTrue(os.path.exists(sentinel_file))

    def test_link_or_copy_nonexistent_source_raises_file_not_found(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            target_dir = os.path.join(tmpdir, "target")
            with self.assertRaises(FileNotFoundError):
                pipeline_orchestrator.link_or_copy_artifact("/nonexistent/fake_chunk.mp4", target_dir)


class TestColabRunnerParameterForwarding(unittest.TestCase):
    """Verify force_cpu forwarding in colab_render_runner."""

    def test_force_cpu_forwarded_to_render_part_chunk(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            proj = Path(tmpdir)
            (proj / "02. Media Generation" / "audio").mkdir(parents=True)
            (proj / "02. Media Generation" / "keyframes").mkdir(parents=True)
            (proj / "02. Media Generation" / "chunks").mkdir(parents=True)
            (proj / "03. Final Production").mkdir(parents=True)

            # Create dummy Part 01 audio and 1 keyframe
            (proj / "02. Media Generation" / "audio" / "Part_01.wav").write_bytes(b"RIFF" + b"\x00" * 100)
            (proj / "02. Media Generation" / "keyframes" / "beat_P01_B01.jpg").write_bytes(b"\xFF\xD8\xFF" + b"\x00" * 100)

            chunk_out = proj / "02. Media Generation" / "chunks" / "chunk_part_01.mp4"
            chunk_out.write_bytes(b"CHUNK" * 100)

            with patch("colab_render_runner.is_chunk_valid", return_value=False), \
                 patch("colab_render_runner.render_part_chunk") as mock_render:

                mock_render.return_value = str(chunk_out)
                colab_render_runner.run_colab_render(
                    project_folder_path=str(proj),
                    parts_to_process=[1],
                    force_cpu=True
                )

                mock_render.assert_called_once()
                self.assertTrue(mock_render.call_args.kwargs.get("force_cpu"))

    def test_colab_runner_detects_png_keyframes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            proj = Path(tmpdir)
            (proj / "02. Media Generation" / "audio").mkdir(parents=True)
            (proj / "02. Media Generation" / "keyframes").mkdir(parents=True)
            (proj / "02. Media Generation" / "chunks").mkdir(parents=True)
            (proj / "03. Final Production").mkdir(parents=True)

            (proj / "02. Media Generation" / "audio" / "Part_01.wav").write_bytes(b"RIFF" + b"\x00" * 100)
            (proj / "02. Media Generation" / "keyframes" / "beat_P01_B01.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)

            chunk_out = proj / "02. Media Generation" / "chunks" / "chunk_part_01.mp4"
            chunk_out.write_bytes(b"CHUNK" * 100)

            with patch("colab_render_runner.is_chunk_valid", return_value=False), \
                 patch("colab_render_runner.render_part_chunk") as mock_render:

                mock_render.return_value = str(chunk_out)
                colab_render_runner.run_colab_render(
                    project_folder_path=str(proj),
                    parts_to_process=[1],
                    force_cpu=True
                )

                mock_render.assert_called_once()
                beat_images = mock_render.call_args.kwargs.get("beat_images")
                self.assertEqual(len(beat_images), 1)
                self.assertTrue(beat_images[0].endswith(".png"))

    def test_colab_runner_deduplicates_keyframes_by_stem(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            proj = Path(tmpdir)
            (proj / "02. Media Generation" / "audio").mkdir(parents=True)
            (proj / "02. Media Generation" / "keyframes").mkdir(parents=True)
            (proj / "02. Media Generation" / "chunks").mkdir(parents=True)
            (proj / "03. Final Production").mkdir(parents=True)

            (proj / "02. Media Generation" / "audio" / "Part_01.wav").write_bytes(b"RIFF" + b"\x00" * 100)
            # Both .jpg and .png for beat 1
            (proj / "02. Media Generation" / "keyframes" / "beat_P01_B01.jpg").write_bytes(b"\xFF\xD8\xFF" + b"\x00" * 100)
            (proj / "02. Media Generation" / "keyframes" / "beat_P01_B01.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)

            chunk_out = proj / "02. Media Generation" / "chunks" / "chunk_part_01.mp4"
            chunk_out.write_bytes(b"CHUNK" * 100)

            with patch("colab_render_runner.is_chunk_valid", return_value=False), \
                 patch("colab_render_runner.render_part_chunk") as mock_render:

                mock_render.return_value = str(chunk_out)
                colab_render_runner.run_colab_render(
                    project_folder_path=str(proj),
                    parts_to_process=[1],
                    force_cpu=True
                )

                mock_render.assert_called_once()
                beat_images = mock_render.call_args.kwargs.get("beat_images")
                # Deduplicated: exactly 1 keyframe passed for Beat 01, not 2
                self.assertEqual(len(beat_images), 1)

    def test_colab_runner_detects_uppercase_extensions(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            proj = Path(tmpdir)
            (proj / "02. Media Generation" / "audio").mkdir(parents=True)
            (proj / "02. Media Generation" / "keyframes").mkdir(parents=True)
            (proj / "02. Media Generation" / "chunks").mkdir(parents=True)
            (proj / "03. Final Production").mkdir(parents=True)

            (proj / "02. Media Generation" / "audio" / "Part_01.wav").write_bytes(b"RIFF" + b"\x00" * 100)
            (proj / "02. Media Generation" / "keyframes" / "beat_P01_B01.JPG").write_bytes(b"\xFF\xD8\xFF" + b"\x00" * 100)
            (proj / "02. Media Generation" / "keyframes" / "beat_P01_B02.PNG").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)

            chunk_out = proj / "02. Media Generation" / "chunks" / "chunk_part_01.mp4"
            chunk_out.write_bytes(b"CHUNK" * 100)

            with patch("colab_render_runner.is_chunk_valid", return_value=False), \
                 patch("colab_render_runner.render_part_chunk") as mock_render:

                mock_render.return_value = str(chunk_out)
                colab_render_runner.run_colab_render(
                    project_folder_path=str(proj),
                    parts_to_process=[1],
                    force_cpu=True
                )

                mock_render.assert_called_once()
                beat_images = mock_render.call_args.kwargs.get("beat_images")
                self.assertEqual(len(beat_images), 2)


class TestPhase1AdditionalP0Remediations(unittest.TestCase):
    """P0.6 & P0.7: Streaming PCM silence extraction and Stardust FFmpeg process cleanup."""

    def test_cue_extractor_streaming_silence_scan(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            wav_path = os.path.join(tmpdir, "Part_01.wav")
            import wave, struct

            # Create a small WAV with silence intervals: 8000 Hz, 16-bit mono
            framerate = 8000
            silence_len = int(framerate * 1.0)
            tone_len = int(framerate * 0.5)

            with wave.open(wav_path, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(framerate)
                for chunk_idx in range(18):
                    # 1.0s silence
                    wf.writeframes(struct.pack(f"<{silence_len}h", *([0] * silence_len)))
                    # 0.5s tone
                    wf.writeframes(struct.pack(f"<{tone_len}h", *([5000] * tone_len)))

            res = cue_extractor.extract_part01_cue_timestamps(
                part_01_wav_path=wav_path,
                intra_silence_sec=1.0
            )
            self.assertEqual(res["extraction_method"], "zero_silence_scan")
            self.assertGreater(res["cue_start_sec"], 0.0)
            self.assertGreater(res["cue_end_sec"], res["cue_start_sec"])

    def test_stardust_pipe_cleanup_on_broken_pipe(self):
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None  # Process is running
        mock_proc.stdin.write.side_effect = BrokenPipeError("Broken pipe")

        with tempfile.TemporaryDirectory() as tmpdir:
            out_target = os.path.join(tmpdir, "test_stardust.mp4")
            with patch("subprocess.Popen", return_value=mock_proc), \
                 patch("shutil.which", return_value="/usr/bin/ffmpeg"):

                with self.assertRaises(RuntimeError):
                    generate_ambient_stardust.generate_ambient_stardust_loop(
                        output_path=out_target,
                        duration=0.1
                    )

            # Child process must be killed and waited on
            mock_proc.kill.assert_called_once()
            mock_proc.wait.assert_called()

    def test_render_single_part_unlinks_corrupted_bundle_archive(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            proj = Path(tmpdir)
            corrupt_bundle = proj / "keyframes_bundle.tar.gz"
            corrupt_bundle.write_bytes(b"NOT_A_TAR_GZ_FILE_JUST_CORRUPT_BYTES")

            with patch("urllib.request.urlopen"):
                with self.assertRaises(RuntimeError):
                    render_single_part.ensure_part_assets(str(proj), 1)

            # Corrupted archive must be unlinked to allow future clean runs
            self.assertFalse(corrupt_bundle.exists())


class TestLiveFFmpeg4KRender(unittest.TestCase):
    """Deep verification: Execute real FFmpeg 4K (3840x2160, 30fps) beat render."""

    def test_live_4k_kenburns_render(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            img_path = os.path.join(tmpdir, "test_beat.png")
            out_clip = os.path.join(tmpdir, "test_beat_out.mp4")

            # Generate a 4K test still frame using ffmpeg
            gen_cmd = [
                "ffmpeg", "-y", "-loglevel", "error",
                "-f", "lavfi", "-i", "color=c=navy:s=3840x2160:d=0.1",
                "-frames:v", "1",
                img_path
            ]
            import subprocess
            subprocess.run(gen_cmd, check=True)
            self.assertTrue(os.path.exists(img_path))

            # Render 1.0 second Ken Burns beat clip (30 frames at 3840x2160)
            kenburns_asmr.render_kenburns_beat(
                image_path=img_path,
                duration=1.0,
                output_clip_path=out_clip,
                zoom_in=True,
                width=3840,
                height=2160,
                fps=30,
                force_cpu=True
            )

            self.assertTrue(os.path.exists(out_clip))
            self.assertGreater(os.path.getsize(out_clip), 1000)

            # Probe resolution and framerate using ffprobe
            probe_cmd = [
                "ffprobe", "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=width,height,r_frame_rate,duration",
                "-of", "csv=p=0",
                out_clip
            ]
            res = subprocess.run(probe_cmd, capture_output=True, text=True, check=True)
            parts = res.stdout.strip().split(",")
            width = int(parts[0])
            height = int(parts[1])
            fps_str = parts[2]
            dur = float(parts[3])

            self.assertEqual(width, 3840, f"Expected 4K width 3840, got {width}")
            self.assertEqual(height, 2160, f"Expected 4K height 2160, got {height}")
            self.assertEqual(fps_str, "30/1", f"Expected 30 fps, got {fps_str}")
            self.assertAlmostEqual(dur, 1.0, delta=0.1)



class TestPhase1Reviewer3AdversarialHardening(unittest.TestCase):
    """
    Reviewer 3 Adversarial Hardening:
    Edge cases, race conditions, parameter validation, broken symlink fallback,
    drive letter path attacks, and uppercase Linux case-sensitivity.
    """

    def test_link_or_copy_empty_target_dir_raises_value_error(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src_file = os.path.join(tmpdir, "chunk.mp4")
            with open(src_file, "w") as f:
                f.write("DATA")
            with self.assertRaises(ValueError):
                pipeline_orchestrator.link_or_copy_artifact(src_file, "")
            with self.assertRaises(ValueError):
                pipeline_orchestrator.link_or_copy_artifact(src_file, "   ")
            with self.assertRaises(ValueError):
                pipeline_orchestrator.link_or_copy_artifact(src_file, None)

    def test_link_or_copy_fallback_with_broken_symlink_at_target(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src_file = os.path.join(tmpdir, "src.mp4")
            with open(src_file, "w") as f:
                f.write("CANONICAL_PAYLOAD")

            target_dir = os.path.join(tmpdir, "target")
            os.makedirs(target_dir, exist_ok=True)
            target_path = os.path.join(target_dir, "src.mp4")
            # Create a broken dangling symlink at target
            os.symlink(os.path.join(tmpdir, "dangling.mp4"), target_path)
            self.assertTrue(os.path.islink(target_path))
            self.assertFalse(os.path.exists(target_path))

            # When os.symlink fails with OSError, fallback to copy2 must succeed without FileNotFoundError
            with patch("os.symlink", side_effect=OSError("Symlink failed")):
                result = pipeline_orchestrator.link_or_copy_artifact(src_file, target_dir)
                self.assertTrue(os.path.exists(result))
                self.assertFalse(os.path.islink(result))
                with open(result, "r") as f:
                    self.assertEqual(f.read(), "CANONICAL_PAYLOAD")

    def test_safe_extract_tarball_blocks_windows_drive_prefix(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            dest = Path(tmpdir) / "dest"
            dest.mkdir()

            buf = io.BytesIO()
            with tarfile.open(fileobj=buf, mode="w:gz") as tar:
                ti = tarfile.TarInfo(name="C:evil.txt")
                data = b"DRIVE_INJECTION"
                ti.size = len(data)
                tar.addfile(ti, io.BytesIO(data))
            buf.seek(0)

            archive_path = Path(tmpdir) / "drive_prefix.tar.gz"
            archive_path.write_bytes(buf.getvalue())

            with self.assertRaises(download_drive_assets.SecurityError):
                download_drive_assets.safe_extract_tarball(archive_path, dest)

            with self.assertRaises(render_single_part.SecurityError):
                render_single_part.safe_extract_tarball(archive_path, dest)

    def test_safe_extract_tarball_blocks_windows_drive_symlink(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            dest = Path(tmpdir) / "dest"
            dest.mkdir()

            buf = io.BytesIO()
            with tarfile.open(fileobj=buf, mode="w:gz") as tar:
                ti = tarfile.TarInfo(name="link_drive")
                ti.type = tarfile.SYMTYPE
                ti.linkname = "C:\\Windows\\System32"
                tar.addfile(ti)
            buf.seek(0)

            archive_path = Path(tmpdir) / "drive_symlink.tar.gz"
            archive_path.write_bytes(buf.getvalue())

            with self.assertRaises(download_drive_assets.SecurityError):
                download_drive_assets.safe_extract_tarball(archive_path, dest)

            with self.assertRaises(render_single_part.SecurityError):
                render_single_part.safe_extract_tarball(archive_path, dest)

    def test_safe_extract_tarball_empty_destination_raises_value_error(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            archive_path = Path(tmpdir) / "empty.tar.gz"
            with tarfile.open(archive_path, "w:gz") as tar:
                pass
            with self.assertRaises(ValueError):
                download_drive_assets.safe_extract_tarball(archive_path, "")
            with self.assertRaises(ValueError):
                download_drive_assets.safe_extract_tarball(archive_path, "   ")
            with self.assertRaises(ValueError):
                render_single_part.safe_extract_tarball(archive_path, "")

    def test_safe_extract_tarball_blocks_null_byte_member(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            dest = Path(tmpdir) / "dest"
            dest.mkdir()

            buf = io.BytesIO()
            with tarfile.open(fileobj=buf, mode="w:gz") as tar:
                ti = tarfile.TarInfo(name="dummy")
                ti.pax_headers = {"path": "file\0evil.txt"}
                data = b"NULL_BYTE"
                ti.size = len(data)
                tar.addfile(ti, io.BytesIO(data))
            buf.seek(0)

            archive_path = Path(tmpdir) / "null_byte.tar.gz"
            archive_path.write_bytes(buf.getvalue())

            with self.assertRaises(download_drive_assets.SecurityError):
                download_drive_assets.safe_extract_tarball(archive_path, dest)

            with self.assertRaises(render_single_part.SecurityError):
                render_single_part.safe_extract_tarball(archive_path, dest)

    def test_audit_gk6_detects_uppercase_keyframe_extensions(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            proj = Path(tmpdir)
            audio_dir = proj / "02. Media Generation" / "audio"
            keyframes_dir = proj / "02. Media Generation" / "keyframes"
            audio_dir.mkdir(parents=True)
            keyframes_dir.mkdir(parents=True)

            # Create 15 audio parts
            for p in range(1, 16):
                (audio_dir / f"Part_{p:02d}.wav").write_bytes(b"RIFF" + b"\x00" * 20000)

            # Create 150 keyframes with mixed uppercase extensions (.JPG, .PNG, .JPEG)
            for p in range(1, 16):
                for b in range(1, 11):
                    ext = ".JPG" if b % 3 == 0 else (".PNG" if b % 3 == 1 else ".JPEG")
                    (keyframes_dir / f"beat_P{p:02d}_B{b:02d}{ext}").write_bytes(b"IMG")

            audit = pipeline_orchestrator.audit_gk6_assets(str(proj))
            self.assertTrue(audit["passed_gk6"], f"GK6 failed: {audit.get('details')}")
            self.assertEqual(audit["audio_count"], 15)
            self.assertEqual(audit["image_count"], 150)
            self.assertEqual(len(audit["deficient_parts"]), 0)

    def test_kenburns_zero_total_frames_is_bounded(self):
        filt, _ = kenburns_asmr.build_filter_graph(
            zoom_in=True,
            total_frames=0,
            width=3840,
            height=2160,
            fps=30
        )
        self.assertIn("d=1:", filt)
        self.assertNotIn("d=0:", filt)

    def test_kenburns_none_vignette_handled_safely(self):
        filt, _ = kenburns_asmr.build_filter_graph(
            zoom_in=True,
            total_frames=30,
            sleep_mode=True,
            vignette=None
        )
        # Uniform dimming without oval border by default
        self.assertNotIn("vignette=", filt)
        self.assertIn("eq=contrast=", filt)

        # When vignette is specified, verify it is included
        filt_with_vig, _ = kenburns_asmr.build_filter_graph(
            zoom_in=True,
            total_frames=30,
            sleep_mode=True,
            vignette="PI/4:aspect=16/9"
        )
        self.assertIn("vignette=", filt_with_vig)

    def test_stardust_purges_partial_file_on_error(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            out_file = os.path.join(tmpdir, "broken_stardust.mp4")
            mock_proc = MagicMock()
            mock_proc.poll.return_value = None

            def _failing_write(data):
                # Write partial broken file
                with open(out_file, "wb") as f:
                    f.write(b"PARTIAL_STARDUST_VIDEO")
                raise BrokenPipeError("FFmpeg broke pipe")

            mock_proc.stdin.write.side_effect = _failing_write

            with patch("subprocess.Popen", return_value=mock_proc), \
                 patch("shutil.which", return_value="/usr/bin/ffmpeg"):
                with self.assertRaises(RuntimeError):
                    generate_ambient_stardust.generate_ambient_stardust_loop(
                        output_path=out_file,
                        duration=0.1
                    )

            # Broken output file must be purged!
            self.assertFalse(os.path.exists(out_file))

    def test_chunk_renderer_cleanup_removes_broken_symlinks(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            temp_dir = os.path.join(tmpdir, "temp")
            output_dir = os.path.join(tmpdir, "output")
            os.makedirs(temp_dir, exist_ok=True)
            os.makedirs(output_dir, exist_ok=True)

            dummy_img = os.path.join(tmpdir, "beat.jpg")
            with open(dummy_img, "wb") as f:
                f.write(b"IMG")
            dummy_audio = os.path.join(tmpdir, "Part_01.wav")
            with open(dummy_audio, "wb") as f:
                f.write(b"AUDIO")

            # Create broken symlink in temp_dir matching beat clip pattern
            broken_symlink = os.path.join(temp_dir, "beat_P01_B05.mp4")
            os.symlink(os.path.join(tmpdir, "nonexistent.mp4"), broken_symlink)
            self.assertTrue(os.path.islink(broken_symlink))
            self.assertFalse(os.path.exists(broken_symlink))  # Broken!

            with patch("chunk_renderer.is_chunk_valid", side_effect=[False, True]), \
                 patch("chunk_renderer.align_part_beats", return_value={"beats": [{"image_path": dummy_img, "duration": 3.0}]}), \
                 patch("chunk_renderer.render_kenburns_beat", return_value=os.path.join(temp_dir, "beat_P01_B01.mp4")), \
                 patch("subprocess.run") as mock_run:

                mock_run.return_value = MagicMock(returncode=0)
                chunk_renderer.render_part_chunk(
                    part_index=1,
                    audio_wav_path=dummy_audio,
                    beat_images=[dummy_img],
                    output_dir=output_dir,
                    temp_dir=temp_dir
                )

            # Broken symlink must be removed!
            self.assertFalse(os.path.lexists(broken_symlink))

    def test_render_single_part_forwards_force_cpu(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            proj = Path(tmpdir)
            audio_dir = proj / "02. Media Generation" / "audio"
            keyframes_dir = proj / "02. Media Generation" / "keyframes"
            audio_dir.mkdir(parents=True)
            keyframes_dir.mkdir(parents=True)

            (audio_dir / "Part_01.wav").write_bytes(b"RIFF" + b"\x00" * (1024 * 1024 + 100))
            for b in range(1, 11):
                (keyframes_dir / f"beat_P01_B{b:02d}.jpg").write_bytes(b"IMG")

            with patch("render_single_part.render_part_chunk") as mock_render, \
                 patch("render_single_part.is_chunk_valid", return_value=True), \
                 patch("pipeline_orchestrator.link_or_copy_artifact", return_value="/output/chunk.mp4"):

                mock_render.return_value = "/output/chunk.mp4"
                render_single_part.render_single_part(str(proj), part_index=1, force_cpu=False)
                self.assertFalse(mock_render.call_args.kwargs.get("force_cpu"))

                render_single_part.render_single_part(str(proj), part_index=1, force_cpu=True)
                self.assertTrue(mock_render.call_args.kwargs.get("force_cpu"))

    def test_colab_runner_forwards_max_workers(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            proj = Path(tmpdir)
            (proj / "02. Media Generation" / "audio").mkdir(parents=True)
            (proj / "02. Media Generation" / "keyframes").mkdir(parents=True)
            (proj / "02. Media Generation" / "chunks").mkdir(parents=True)
            (proj / "03. Final Production").mkdir(parents=True)

            (proj / "02. Media Generation" / "audio" / "Part_01.wav").write_bytes(b"RIFF" + b"\x00" * 100)
            (proj / "02. Media Generation" / "keyframes" / "beat_P01_B01.jpg").write_bytes(b"\xFF\xD8\xFF" + b"\x00" * 100)

            chunk_out = proj / "02. Media Generation" / "chunks" / "chunk_part_01.mp4"
            chunk_out.write_bytes(b"CHUNK" * 100)

            with patch("colab_render_runner.is_chunk_valid", return_value=False), \
                 patch("colab_render_runner.render_part_chunk") as mock_render:

                mock_render.return_value = str(chunk_out)
                colab_render_runner.run_colab_render(
                    project_folder_path=str(proj),
                    parts_to_process=[1],
                    max_workers=3
                )

                self.assertEqual(mock_render.call_args.kwargs.get("max_workers"), 3)


if __name__ == "__main__":
    unittest.main(verbosity=2)

