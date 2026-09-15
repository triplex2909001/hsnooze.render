#!/usr/bin/env python3
"""
Unit and Integration Tests for Dual-Operation Parity: GitHub Actions ⟷ Google Colab
Authority: GATEKEEPERS.md (Section 3) & AGENTS.md (Section 6)
Mandate: "Mọi sự thay đổi một cách tích cực, đều được cập nhật trên cả 2 operation versions."
"""

import os
import io
import sys
import tarfile
import tempfile
import inspect
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

# Ensure project root is in python path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
import colab_render_runner
import render_single_part
import assemble_master
import master_assembler
import chunk_renderer
import kenburns_asmr
import download_drive_assets
import pipeline_orchestrator


class TestDualOperationParity(unittest.TestCase):
    """Verifies 100% operational parity between GitHub Actions and Google Colab."""

    def setUp(self):
        self.gha_workflow_path = Path(__file__).resolve().parent.parent / ".github" / "workflows" / "render_parallel.yml"

    def test_checkpoint_1_safe_tarball_and_asset_download_parity(self):
        """Checkpoint 1: Both GHA and Colab use CVE-2007-4559 safe extraction & folder_id."""
        self.assertTrue(hasattr(download_drive_assets, "safe_extract_tarball"))
        self.assertTrue(hasattr(render_single_part, "safe_extract_tarball"))
        self.assertIn("folder_id", inspect.signature(download_drive_assets.download_project_assets).parameters)
        self.assertIn("folder_id", inspect.signature(colab_render_runner.run_colab_render).parameters)

        # Active Tar Slip path traversal rejection assertion
        with tempfile.TemporaryDirectory() as tmpdir:
            tar_p = Path(tmpdir) / "evil.tar.gz"
            with tarfile.open(tar_p, "w:gz") as tar:
                ti = tarfile.TarInfo(name="../evil.txt")
                ti.size = 4
                tar.addfile(ti, io.BytesIO(b"evil"))
            with self.assertRaises((download_drive_assets.SecurityError, Exception)):
                download_drive_assets.safe_extract_tarball(tar_p, Path(tmpdir) / "out1")
            with self.assertRaises((render_single_part.SecurityError, Exception)):
                render_single_part.safe_extract_tarball(tar_p, Path(tmpdir) / "out2")

    def test_checkpoint_2_uniform_dimming_and_cosine_stardust_parity(self):
        """Checkpoint 2: Both platforms enforce uniform dimming & cosine fade-in."""
        self.assertEqual(config.DEFAULT_VIGNETTE, "none")
        self.assertEqual(kenburns_asmr.DEFAULT_VIGNETTE, "none")

        t0, t1, delta = 38.0, 45.0, 7.0
        filt, out_label = kenburns_asmr.build_filter_graph(
            zoom_in=True, total_frames=1800, width=3840, height=2160, fps=30,
            is_transition_beat=True, dim_start_sec=t0, dim_end_sec=t1, has_overlay=True
        )
        self.assertEqual(out_label, "[out]")
        exp_opacity = f"if(lte(T,{t0:.3f}),0.0,if(gte(T,{t1:.3f}),1.0,0.5*(1-cos(PI*(T-{t0:.3f})/{delta:.3f}))))"
        self.assertIn(exp_opacity, filt)
        self.assertNotIn("vignette=", filt)

        # Non-transition beats must omit cosine blend ramp
        filt_non, _ = kenburns_asmr.build_filter_graph(
            zoom_in=True, total_frames=1800, width=3840, height=2160, fps=30,
            is_transition_beat=False, has_overlay=True
        )
        self.assertNotIn("cos(PI*(T-", filt_non)

    def test_checkpoint_3_hitl_cover_gate_parity(self):
        """Checkpoint 3: Missing Cover blocks render; present Cover authorizes render."""
        with tempfile.TemporaryDirectory() as tmpdir:
            proj = Path(tmpdir)
            audio_dir, kf_dir = proj / "02. Media Generation" / "audio", proj / "02. Media Generation" / "keyframes"
            audio_dir.mkdir(parents=True), kf_dir.mkdir(parents=True)

            for p in (1, 2):
                (audio_dir / f"Part_{p:02d}.wav").write_bytes(b"RIFF" + b"\x00" * 1050000)
                for i in range(2, 12):
                    (kf_dir / f"beat_P{p:02d}_B{i:02d}.jpg").write_bytes(b"\xFF\xD8\xFF" * 10)
            (kf_dir / "beat_P02_B01.jpg").write_bytes(b"\xFF\xD8\xFF" * 10)

            # Rejection on missing Cover
            with self.assertRaises(FileNotFoundError):
                colab_render_runner.run_colab_render(str(proj), parts_to_process=[1])
            with self.assertRaises(FileNotFoundError):
                render_single_part.render_part(str(proj), part_index=1)

            # Positive passage when Cover exists and Part 2 independence
            (kf_dir / "beat_P01_B01.jpg").write_bytes(b"\xFF\xD8\xFFcover" * 10)
            def mock_chunk(part_index, audio_wav_path, beat_images, output_dir, temp_dir, **kw):
                p = Path(output_dir) / f"chunk_part_{part_index:02d}.mp4"
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(b"mock_mp4")
                return str(p)

            with patch("render_single_part.render_part_chunk", side_effect=mock_chunk), \
                 patch("render_single_part.is_chunk_valid", return_value=True), \
                 patch("colab_render_runner.render_part_chunk", side_effect=mock_chunk), \
                 patch("colab_render_runner.is_chunk_valid", return_value=True), \
                 patch("pipeline_orchestrator.link_or_copy_artifact", return_value=True):
                self.assertTrue(render_single_part.render_part(str(proj), part_index=1))
                colab_render_runner.run_colab_render(str(proj), parts_to_process=[1])
                (kf_dir / "beat_P01_B01.jpg").unlink()
                self.assertTrue(render_single_part.render_part(str(proj), part_index=2))

    def test_checkpoint_4_hardware_and_memory_clamping_parity(self):
        """Checkpoint 4: Concurrency clamping and CPU fallback across both platforms."""
        self.assertLessEqual(chunk_renderer.get_safe_max_workers(8, ram_gb=4.0), 1)

        with tempfile.TemporaryDirectory() as tmpdir:
            dummy_img, out_clip = Path(tmpdir) / "test.jpg", Path(tmpdir) / "out.mp4"
            dummy_img.write_bytes(b"\xFF\xD8\xFFdummy")
            calls = []

            def fake_run(cmd, **kwargs):
                calls.append(list(cmd))
                if "-c:v" in cmd and "h264_nvenc" in cmd[cmd.index("-c:v") + 1]:
                    raise subprocess.CalledProcessError(1, cmd, stderr="NVENC failed")
                out_clip.write_bytes(b"mp4data")
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

            with patch("kenburns_asmr.check_nvenc_available", return_value=True), \
                 patch("subprocess.run", side_effect=fake_run):
                kenburns_asmr.render_kenburns_beat(str(dummy_img), 1.0, str(out_clip), force_cpu=False)

            self.assertEqual(len(calls), 2)
            self.assertIn("h264_nvenc", calls[0])
            self.assertIn("libx264", calls[1])

    def test_checkpoint_5_inter_part_silence_parity(self):
        """Checkpoint 5: Interleave exactly 14 silences for 15 parts in master assembly."""
        self.assertEqual(config.INTER_PART_SILENCE_SEC, 5.0)
        self.assertEqual(assemble_master.SILENCE_GAP_SEC, 5.0)

        with tempfile.TemporaryDirectory() as tmpdir:
            chunks = [str(Path(tmpdir) / f"chunk_{i:02d}.mp4") for i in range(1, 16)]
            with patch("master_assembler.create_5s_silence_clip", return_value="silence.mp4"), \
                 patch("subprocess.run"), \
                 patch("master_assembler.audit_master_video_gk7", return_value={"passed_gk7": True, "duration_minutes": 90.0, "file_size_gb": 1.0}):
                master_assembler.assemble_master_video(chunks, str(Path(tmpdir) / "m.mp4"), tmpdir)

            lines = (Path(tmpdir) / "master_concat_list.txt").read_text().strip().split("\n")
            self.assertEqual(len(lines), 29)
            self.assertEqual(len([l for l in lines if "silence_5s.mp4" in l]), 14)
            self.assertIn("chunk_15.mp4", lines[-1])

    def test_checkpoint_6_gk7_master_audit_parity(self):
        """Checkpoint 6: Enforce GK7 bounds (80.0-95.0 mins, >500MB) across both assemblers."""
        self.assertEqual(config.GK7_MIN_VIDEO_DURATION_MIN, 80)
        self.assertEqual(config.GK7_MAX_VIDEO_DURATION_MIN, 95)

        cases = [(5100, 10**9, True), (4800, 10**9, True), (5700, 10**9, True),
                 (4500, 10**9, False), (6000, 10**9, False), (5100, 4 * 10**8, False)]
        with tempfile.NamedTemporaryFile() as tf:
            for dur, sz, exp in cases:
                with patch("subprocess.run", return_value=MagicMock(stdout=f"{dur}\n{sz}\n")):
                    self.assertEqual(master_assembler.audit_master_video_gk7(tf.name)["passed_gk7"], exp)
                    self.assertEqual(pipeline_orchestrator.audit_gk7_master(".", master_path=tf.name)["passed_gk7"], exp)

    def test_checkpoint_7_output_artifact_hierarchy_parity(self):
        """Checkpoint 7: Both GHA and Colab mirror chunks and master to output/ directory."""
        gha = self.gha_workflow_path.read_text(encoding="utf-8")
        self.assertIn("output/chunk_part_*.mp4", gha)
        self.assertIn("output/master_final_90min.mp4", gha)

        colab = Path(colab_render_runner.__file__).read_text(encoding="utf-8")
        self.assertIn('output_dir = proj_dir / "output"', colab)
        self.assertIn("link_or_copy_artifact(chunk_mp4, str(output_dir))", colab)
        self.assertIn("link_or_copy_artifact(str(master_mp4), str(output_dir))", colab)


if __name__ == "__main__":
    unittest.main()
