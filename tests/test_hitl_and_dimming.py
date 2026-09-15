"""
Unit and Integration Tests for:
1. Human-in-the-Loop (HITL) Image Stage Gate (Status 'JPEG' & Cover Exemption)
2. 'Dim the Lights' Stardust Cosine Fade-in, Steady-State Pacing, and Uniform Dimming (No Oval Border)
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

# Ensure project root is on sys.path for standalone execution
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
import kenburns_asmr
import chunk_renderer
import pipeline_orchestrator
import image_pipeline_worker


class TestHumanInTheLoopImageStage(unittest.TestCase):
    """Tests the Human-in-the-Loop (HITL) state machine and Cover image gating."""

    def test_status_flow_includes_jpeg(self):
        """Ensures 'JPEG' is a recognized status between 'Voiceover' and 'Image'."""
        self.assertIn("JPEG", config.STATUS_FLOW)
        idx_vo = config.STATUS_FLOW.index("Voiceover")
        idx_jpeg = config.STATUS_FLOW.index("JPEG")
        idx_img = config.STATUS_FLOW.index("Image")
        self.assertEqual(idx_jpeg, idx_vo + 1)
        self.assertEqual(idx_img, idx_jpeg + 1)

    def test_image_worker_skips_cover_by_default(self):
        """Verifies that parse_prompts skips beat_P01_B01 (Cover) when skip_cover=True."""
        with tempfile.NamedTemporaryFile("w", delete=False, suffix=".txt") as f:
            f.write("beat_P01_B01.jpg: Ancient Japanese gate at dusk, 4K\n")
            f.write("beat_P01_B02.jpg: River valley in autumn, 4K\n")
            f.write("beat_P01_B03.jpg: Wooden temple in the mist, 4K\n")
            f_path = Path(f.name)

        try:
            beats, skipped_id = image_pipeline_worker.parse_prompts(f_path, skip_cover=True)
            self.assertEqual(skipped_id, "beat_P01_B01")
            self.assertEqual(len(beats), 2)
            self.assertEqual(beats[0]["id"], "beat_P01_B02")
            self.assertEqual(beats[1]["id"], "beat_P01_B03")

            # With skip_cover=False, Cover should be included
            all_beats, skipped_none = image_pipeline_worker.parse_prompts(f_path, skip_cover=False)
            self.assertIsNone(skipped_none)
            self.assertEqual(len(all_beats), 3)
            self.assertEqual(all_beats[0]["id"], "beat_P01_B01")
        finally:
            if f_path.exists():
                f_path.unlink()

    def test_orchestrator_blocks_when_status_is_jpeg_or_cover_missing(self):
        """Verifies handle_image_generation_stage pauses on 'JPEG' and blocks render without Cover."""
        with tempfile.TemporaryDirectory() as tmpdir:
            kf_dir = os.path.join(tmpdir, "02. Media Generation", "keyframes")
            os.makedirs(kf_dir, exist_ok=True)

            # Step 1: Voiceover -> JPEG transition (Automatic mode initiates and sets JPEG)
            st = pipeline_orchestrator.handle_image_generation_stage(tmpdir, image_mode="Automatic", current_status="Voiceover")
            self.assertEqual(st, "JPEG")

            # Step 2: At Status 'JPEG', without Cover image, it remains paused at 'JPEG'
            st_jpeg = pipeline_orchestrator.handle_image_generation_stage(tmpdir, current_status="JPEG")
            self.assertEqual(st_jpeg, "JPEG")

            # Step 3: If user tries to force 'Image' without adding Cover, it raises ValueError
            with self.assertRaises(ValueError) as ctx:
                pipeline_orchestrator.handle_image_generation_stage(tmpdir, current_status="Image")
            self.assertIn("Cover image 'beat_P01_B01' is missing", str(ctx.exception))

            # Step 4: Add manual Cover image
            cover_path = os.path.join(kf_dir, "beat_P01_B01.jpg")
            with open(cover_path, "wb") as f:
                f.write(b"mock_cover_image_bytes")

            # Now Status 'Image' is authorized
            st_ready = pipeline_orchestrator.handle_image_generation_stage(tmpdir, current_status="Image")
            self.assertEqual(st_ready, "Image")


class TestDimTheLightsStardustAndUniformDimming(unittest.TestCase):
    """Tests the 'dim the lights' lighting transition, stardust fade-in, and uniform dimming."""

    def test_default_vignette_is_none(self):
        """Verifies DEFAULT_VIGNETTE defaults to 'none' for uniform dimming with zero oval border."""
        self.assertEqual(kenburns_asmr.DEFAULT_VIGNETTE, "none")

    def test_uniform_dimming_produces_no_oval_vignette(self):
        """Verifies that the generated filter complex has eq=contrast=... and zero vignette filter."""
        filt, _ = kenburns_asmr.build_filter_graph(
            zoom_in=True,
            total_frames=90,
            sleep_mode=True,
            vignette=None
        )
        self.assertNotIn("vignette=", filt)
        self.assertIn("eq=contrast=", filt)
        self.assertIn("brightness=", filt)
        self.assertIn("gamma=", filt)

    def test_stardust_fadein_on_transition_beat(self):
        """
        Verifies that on is_transition_beat (Part 01 Beat 01 / Cover):
        1. Both lighting dimming and stardust particles start simultaneously at t0 (dim_start_sec).
        2. Stardust opacity ramps from 0.0 to 1.0 via cosine ease-in curve.
        3. Stardust reaches 1.0 steady-state at t1 (dim_end_sec).
        4. Overlay stream is scaled to target resolution.
        """
        t0 = 38.0
        t1 = 45.0
        delta = 7.0
        filt, out_label = kenburns_asmr.build_filter_graph(
            zoom_in=True,
            total_frames=1800, # 60 seconds @ 30 fps
            width=3840,
            height=2160,
            fps=30,
            is_transition_beat=True,
            dim_start_sec=t0,
            dim_end_sec=t1,
            has_overlay=True
        )

        self.assertEqual(out_label, "[out]")
        # Check overlay scaling
        self.assertIn("scale=3840:2160", filt)
        self.assertIn("colorchannelmixer=aa=0.35", filt)
        # Check cosine dimming blend
        self.assertIn("blend=all_expr=", filt)
        # Check stardust opacity blend expression starting at t0, reaching 1.0 at t1
        expected_opacity_sub = f"if(lte(T,{t0:.3f}),0.0,if(gte(T,{t1:.3f}),1.0,0.5*(1-cos(PI*(T-{t0:.3f})/{delta:.3f}))))"
        self.assertIn(expected_opacity_sub, filt)
        # Check that no oval vignette is present
        self.assertNotIn("vignette=", filt)


if __name__ == "__main__":
    unittest.main()
