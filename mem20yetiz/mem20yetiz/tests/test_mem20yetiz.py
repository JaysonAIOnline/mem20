"""Hermetic tests for mem20yetiz."""

from __future__ import annotations

import math
import os
import tempfile
import unittest

import numpy as np

from mem20yetiz import gltf, obj
from mem20yetiz.animation import AnimationClip, AnimationCurve, Keyframe
from mem20yetiz.config import YetiConfig
from mem20yetiz.exporter import Exporter, ExportSettings
from mem20yetiz.mocap import (
    MarkerSet,
    MocapData,
    MocapFrame,
    MocapProcessor,
    butterworth_filter,
    compute_fk,
    fill_gap,
    load_c3d,
    mocap_to_animation,
    moving_average,
    parse_bvh_file,
    track_markers,
    write_bvh,
    write_c3d,
)
from mem20yetiz.retargeter import BoneMapping, RetargetConfig, Retargeter
from mem20yetiz.rig import Bone, Rig, Skeleton

FIXTURE_BVH = os.path.join(os.path.dirname(__file__), "fixtures", "biped_test.bvh")


class TestConfig(unittest.TestCase):
    """Config tests."""

    def test_defaults(self):
        cfg = YetiConfig()
        self.assertEqual(cfg.port, 8005)
        self.assertEqual(cfg.gateway_url, "http://127.0.0.1:4000")
        self.assertIn("gltf", cfg.export_formats)
        self.assertNotIn("fbx", cfg.export_formats)

    def test_load_from_yaml(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write('port: 9000\ngateway_url: "http://localhost:4100"\n')
            f.flush()
            cfg = YetiConfig.load(f.name)
        os.unlink(f.name)
        self.assertEqual(cfg.port, 9000)
        self.assertEqual(cfg.gateway_url, "http://localhost:4100")


class TestRig(unittest.TestCase):
    """Rig tests."""

    def test_skeleton_creation(self):
        skeleton = Skeleton(name="test")
        bone1 = Bone("Hips", None, length=10)
        bone2 = Bone("Spine", "Hips", length=15)
        skeleton.add_bone(bone1)
        skeleton.add_bone(bone2)

        self.assertEqual(skeleton.root_bone, "Hips")
        self.assertEqual(skeleton.bones["Hips"].children, ["Spine"])

    def test_bone_chain(self):
        skeleton = Skeleton(name="test")
        bones = [
            Bone("Hips", None),
            Bone("Spine", "Hips"),
            Bone("Neck", "Spine"),
            Bone("Head", "Neck"),
        ]
        for b in bones:
            skeleton.add_bone(b)

        chain = skeleton.get_bone_chain("Hips", "Head")
        self.assertEqual(chain, ["Hips", "Spine", "Neck", "Head"])

    def test_global_transform(self):
        skeleton = Skeleton(name="test")
        bone1 = Bone("Hips", None)
        bone1.transform = np.eye(4)
        bone1.transform[0, 3] = 1.0  # translate x
        bone2 = Bone("Spine", "Hips")
        skeleton.add_bone(bone1)
        skeleton.add_bone(bone2)

        transform = skeleton.get_bone_global_transform("Spine")
        self.assertEqual(transform[0, 3], 1.0)

    def test_rig_creation(self):
        skeleton = Skeleton(name="test")
        bone = Bone("Hips", None)
        skeleton.add_bone(bone)
        rig = Rig("test_rig", skeleton)

        rig.add_control("Hips_Ctrl", "Hips", "transform", "sphere", (1, 0, 0))
        self.assertIn("Hips_Ctrl", rig.controls)

    def test_rig_constraint(self):
        skeleton = Skeleton(name="test")
        b1 = Bone("Hips", None)
        b2 = Bone("Spine", "Hips")
        skeleton.add_bone(b1)
        skeleton.add_bone(b2)
        rig = Rig("test", skeleton)

        rig.add_constraint("parent", "Spine", "Hips")
        self.assertEqual(len(rig.constraints), 1)

    def test_export_fbx_raises(self):
        skeleton = Skeleton(name="test")
        skeleton.add_bone(Bone("Hips", None))
        rig = Rig("test_rig", skeleton)
        with self.assertRaises(NotImplementedError):
            rig.export_fbx("out.fbx")


class TestAnimation(unittest.TestCase):
    """Animation tests."""

    def test_keyframe(self):
        kf = Keyframe(time=0.0, value=np.array([1, 2, 3]))
        self.assertEqual(kf.time, 0.0)

    def test_animation_curve(self):
        curve = AnimationCurve(
            bone_name="Hips",
            property_path="translate",
            keyframes=[
                Keyframe(0.0, np.array([0, 0, 0])),
                Keyframe(1.0, np.array([10, 0, 0])),
            ],
        )
        val = curve.evaluate(0.5)
        self.assertAlmostEqual(val[0], 5.0)

    def test_animation_clip(self):
        clip = AnimationClip(name="walk", duration=1.0, frame_rate=30.0)
        curve = AnimationCurve(
            bone_name="Hips",
            property_path="translate",
            keyframes=[Keyframe(0.0, np.array([0, 0, 0])), Keyframe(1.0, np.array([10, 0, 0]))],
        )
        clip.add_curve("Hips", "translate", curve)

        self.assertEqual(clip.duration, 1.0)
        self.assertIn("Hips.translate", clip.curves)

    def test_clip_evaluate(self):
        clip = AnimationClip(name="walk", duration=1.0, frame_rate=30.0)
        curve = AnimationCurve(
            bone_name="Hips",
            property_path="translate",
            keyframes=[Keyframe(0.0, np.array([0, 0, 0])), Keyframe(1.0, np.array([10, 0, 0]))],
        )
        clip.add_curve("Hips", "translate", curve)

        result = clip.evaluate(0.5)
        self.assertIn("Hips.translate", result)
        self.assertAlmostEqual(result["Hips.translate"][0], 5.0)

    def test_clip_trim(self):
        clip = AnimationClip(name="walk", duration=2.0, frame_rate=30.0)
        curve = AnimationCurve(
            bone_name="Hips",
            property_path="translate",
            keyframes=[
                Keyframe(0.0, np.array([0, 0, 0])),
                Keyframe(1.0, np.array([10, 0, 0])),
                Keyframe(2.0, np.array([20, 0, 0])),
            ],
        )
        clip.add_curve("Hips", "translate", curve)

        trimmed = clip.trim(0.5, 1.5)
        self.assertEqual(trimmed.duration, 1.0)


class TestRetargeter(unittest.TestCase):
    """Retargeter tests."""

    def setUp(self):
        src_skeleton = Skeleton(name="source")
        src_bones = [
            Bone("Hips", None, length=10),
            Bone("Spine", "Hips", length=15),
            Bone("LeftArm", "Spine", length=25),
        ]
        for b in src_bones:
            src_skeleton.add_bone(b)
        self.src_rig = Rig("source", src_skeleton)

        tgt_skeleton = Skeleton(name="target")
        tgt_bones = [
            Bone("Hips", None, length=12),
            Bone("Spine", "Hips", length=18),
            Bone("LeftArm", "Spine", length=30),
        ]
        for b in tgt_bones:
            tgt_skeleton.add_bone(b)
        self.tgt_rig = Rig("target", tgt_skeleton)

    def test_bone_mapping(self):
        mapping = BoneMapping("Hips", "Hips")
        self.assertEqual(mapping.source_bone, "Hips")

    def test_retarget_config(self):
        config = RetargetConfig(
            bone_mappings=[
                BoneMapping("Hips", "Hips"),
                BoneMapping("Spine", "Spine"),
            ],
            root_bone_source="Hips",
            root_bone_target="Hips",
        )
        self.assertEqual(len(config.bone_mappings), 2)

    def test_retargeter_creation(self):
        config = RetargetConfig(
            bone_mappings=[
                BoneMapping("Hips", "Hips"),
                BoneMapping("Spine", "Spine"),
                BoneMapping("LeftArm", "LeftArm"),
            ],
        )
        retargeter = Retargeter(self.src_rig, self.tgt_rig, config)
        self.assertEqual(retargeter.bone_map["Hips"], "Hips")

    def test_retarget_animation(self):
        config = RetargetConfig(
            bone_mappings=[
                BoneMapping("Hips", "Hips"),
                BoneMapping("Spine", "Spine"),
            ],
        )
        retargeter = Retargeter(self.src_rig, self.tgt_rig, config)

        src_clip = AnimationClip(name="walk", duration=1.0)
        curve = AnimationCurve(
            bone_name="Hips",
            property_path="translate",
            keyframes=[Keyframe(0.0, np.array([0, 0, 0])), Keyframe(1.0, np.array([10, 0, 0]))],
        )
        src_clip.add_curve("Hips", "translate", curve)

        tgt_clip = retargeter.retarget_animation(src_clip)
        self.assertIn("Hips.translate", tgt_clip.curves)

    def test_create_mapping_from_names(self):
        retargeter = Retargeter(self.src_rig, self.tgt_rig, RetargetConfig())
        mappings = retargeter.create_mapping_from_names(
            ["Hips", "Spine", "LeftArm"], ["Hips", "Spine", "LeftArm"]
        )
        self.assertEqual(len(mappings), 3)


class TestBVHParse(unittest.TestCase):
    """BVH parsing + FK tests against the hermetic fixture."""

    @classmethod
    def setUpClass(cls):
        cls.data = parse_bvh_file(FIXTURE_BVH)

    def test_hierarchy(self):
        self.assertEqual(self.data.root_joint, "Hips")
        self.assertEqual(self.data.num_frames, 3)
        self.assertAlmostEqual(self.data.frame_rate, 30.0, places=3)
        self.assertEqual(sorted(self.data.joint_positions.keys()), ["Hips", "LeftArm", "LeftArmEnd", "Neck", "NeckEnd", "Spine"])

    def test_fk_frame0(self):
        f0 = self.data.frames[0]
        np.testing.assert_allclose(f0.joint_positions["Hips"], [0, 0, 0], atol=1e-6)
        np.testing.assert_allclose(f0.joint_positions["Spine"], [0, 10, 0], atol=1e-6)

    def test_fk_frame1(self):
        f1 = self.data.frames[1]
        a = math.radians(30)
        c, s = math.cos(a), math.sin(a)
        r = np.array([[c, -s, 0], [s, c, 0], [0, 0, 1.0]])
        np.testing.assert_allclose(f1.joint_positions["Hips"], [5, 0, 0], atol=1e-6)
        spine = np.array([5, 0, 0]) + r @ np.array([0, 10, 0])
        np.testing.assert_allclose(f1.joint_positions["Spine"], spine, atol=1e-6)
        neck = spine + (r @ r) @ np.array([0, 8, 0])
        np.testing.assert_allclose(f1.joint_positions["Neck"], neck, atol=1e-6)

    def test_fk_frame2_linear_rotation(self):
        f2 = self.data.frames[2]
        a = math.radians(60)
        c, s = math.cos(a), math.sin(a)
        r = np.array([[c, -s, 0], [s, c, 0], [0, 0, 1.0]])
        np.testing.assert_allclose(f2.joint_positions["Hips"], [10, 0, 0], atol=1e-6)
        np.testing.assert_allclose(f2.joint_positions["Spine"], [10, 0, 0] + r @ np.array([0, 10, 0]), atol=1e-6)

    def test_to_skeleton(self):
        sk = self.data.to_skeleton()
        self.assertEqual(sk.root_bone, "Hips")
        self.assertIn("Spine", sk.bones)


class TestBVHRoundtrip(unittest.TestCase):
    """BVH write -> parse roundtrip preserves motion data."""

    def test_roundtrip(self):
        data = parse_bvh_file(FIXTURE_BVH)
        compute_fk(data)
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "round.bvh")
            self.assertTrue(write_bvh(data, out))
            again = parse_bvh_file(out)
            self.assertEqual(again.num_frames, 3)
            np.testing.assert_allclose(again.motion, data.motion, atol=1e-4)


class TestMocapFilters(unittest.TestCase):
    """Real signal-processing helpers."""

    def test_fill_gap(self):
        arr = np.array([1.0, np.nan, np.nan, 4.0, 5.0])
        values, filled_count, remaining_count = fill_gap(arr, max_gap=5)
        self.assertEqual(filled_count, 2)
        self.assertEqual(remaining_count, 0)
        self.assertEqual(values[1], 2.0)
        self.assertEqual(values[2], 3.0)

    def test_fill_gap_long_gap_kept(self):
        arr = np.array([1.0, np.nan, np.nan, np.nan, np.nan, 6.0])
        values, filled_count, remaining_count = fill_gap(arr, max_gap=2)
        self.assertEqual(filled_count, 0)
        self.assertEqual(remaining_count, 4)
        self.assertTrue(np.isnan(values[1]))

    def test_moving_average(self):
        x = np.array([0.0, 1.0, 2.0, 3.0])
        avg = moving_average(x, window=3)
        self.assertEqual(len(avg), 4)
        self.assertAlmostEqual(avg[2], 2.0)

    def test_butterworth(self):
        t = np.arange(100) / 100.0
        signal = np.sin(2 * np.pi * 3 * t) + np.sin(2 * np.pi * 30 * t)
        filtered = butterworth_filter(signal, cutoff_hz=10, order=4, fs=100)
        self.assertEqual(filtered.shape, signal.shape)
        self.assertTrue(np.all(np.isfinite(filtered)))


class TestMarkerTracking(unittest.TestCase):
    """MarkerSet + tracking."""

    def test_marker_set_validation(self):
        ms = MarkerSet(name="test", markers=["A", "B"], template={"A": np.zeros(3), "B": np.ones(3)})
        self.assertEqual(len(ms.markers), 2)

    def test_track_markers_assigns(self):
        data = MocapData(name="track", frame_rate=30.0)
        names = ["A", "B"]
        for f in range(3):
            data.frames.append(
                MocapFrame(
                    frame_number=f,
                    timestamp=f / 30.0,
                    marker_positions={n: np.array([f, 0, 0]) for n in names},
                )
            )
        ms = MarkerSet(name="def", markers=names, template={n: np.zeros(3) for n in names})
        out = track_markers(data, ms)
        # Canonical labels are present on every frame after tracking.
        self.assertIn("A", out.frames[0].marker_positions)
        self.assertTrue(np.all(np.isfinite(out.frames[0].marker_positions["A"])))


class TestMocapToAnimation(unittest.TestCase):
    """mocap -> animation conversion."""

    def test_mocap_to_animation(self):
        data = parse_bvh_file(FIXTURE_BVH)
        clip = mocap_to_animation(data)
        self.assertEqual(clip.name, "Hips")
        self.assertEqual(clip.frame_rate, data.frame_rate)
        self.assertGreater(len(clip.curves), 0)

    def test_mocap_processor(self):
        processor = MocapProcessor()
        processor.add_pipeline_step("gap_fill", "gap_fill", {"max_gap": 5})
        processor.add_pipeline_step("smooth", "smooth", {"window": 3})
        self.assertEqual(len(processor.pipelines), 2)

    def test_mocap_processor_loads_fixture(self):
        processor = MocapProcessor()
        data = processor.load_bvh(FIXTURE_BVH)
        self.assertAlmostEqual(data.frame_rate, 30.0, places=3)


class TestC3DRoundtrip(unittest.TestCase):
    """C3D write -> read roundtrip preserves marker positions."""

    def test_c3d_roundtrip(self):
        data = MocapData(name="markers", frame_rate=30.0)
        names = ["A", "B"]
        for f in range(3):
            data.frames.append(
                MocapFrame(
                    frame_number=f,
                    timestamp=f / 30.0,
                    marker_positions={"A": np.array([float(f), 1, 0]), "B": np.array([0, float(f), 1])},
                )
            )
        data.marker_names = names
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "m.c3d")
            self.assertTrue(write_c3d(data, out))
            back = load_c3d(out)
            self.assertEqual(back.marker_names, names)
            self.assertEqual(back.num_frames, 3)
            np.testing.assert_allclose(back.frames[0].marker_positions["A"], [0, 1, 0], atol=1e-4)


class TestExportGLTF(unittest.TestCase):
    """Real glTF 2.0 export + strict reload validation."""

    def test_export_rig_gltf(self):
        skeleton = Skeleton(name="biped")
        skeleton.add_bone(Bone("Hips", None, length=10))
        skeleton.add_bone(Bone("Spine", "Hips", length=15))
        rig = Rig("biped_rig", skeleton)
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "rig.gltf")
            self.assertTrue(gltf.export_gltf(rig, None, out))
            info = gltf.load_gltf(out)
            self.assertTrue(info["valid"])
            self.assertEqual(set(info["names"]), {"Hips", "Spine"})

    def test_export_mocap_gltf(self):
        data = parse_bvh_file(FIXTURE_BVH)
        clip = mocap_to_animation(data)
        rig = data.to_rig()
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "anim.gltf")
            self.assertTrue(gltf.export_gltf(rig, clip, out))
            info = gltf.load_gltf(out)
            self.assertTrue(info["valid"])
            self.assertEqual(
                info["n_nodes"],
                sum(1 for joint in data.hierarchy.values() if not joint.is_end_site),
            )
            self.assertEqual(info["animations"], 1)


class TestExportOBJ(unittest.TestCase):
    """Real OBJ export + reload validation."""

    def test_obj_rig(self):
        skeleton = Skeleton(name="biped")
        skeleton.add_bone(Bone("Hips", None, length=10))
        skeleton.add_bone(Bone("Spine", "Hips", length=15))
        rig = Rig("biped_rig", skeleton)
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "rig.obj")
            self.assertTrue(obj.write_obj_rig(rig, None, out))
            info = obj.load_obj(out)
            self.assertEqual(info["n_vertices"], 2)
            self.assertEqual(info["n_lines"], 1)

    def test_obj_from_positions(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "skeleton.obj")
            self.assertTrue(obj.write_obj_from_positions("skeleton", {"A": np.zeros(3), "B": np.array([0, 1, 0])}, out))
            info = obj.load_obj(out)
            self.assertEqual(info["n_vertices"], 2)


class TestExporterReal(unittest.TestCase):
    """Real Exporter dispatch, conversion, validation."""

    def test_export_settings(self):
        settings = ExportSettings(format="gltf", include_animation=False)
        self.assertEqual(settings.format, "gltf")
        self.assertFalse(settings.include_animation)

    def test_available_formats(self):
        self.assertEqual(ExportSettings.available_formats(), ["gltf", "obj", "bvh", "c3d"])

    def test_exporter_creation_real(self):
        exporter = Exporter(ExportSettings(format="gltf"))
        self.assertEqual(exporter.settings.format, "gltf")

    def test_exporter_unsupported_format(self):
        with self.assertRaises(NotImplementedError):
            Exporter(ExportSettings(format="usd"))

    def test_export_mocap_all_formats(self):
        data = parse_bvh_file(FIXTURE_BVH)
        exporter = Exporter(ExportSettings(format="gltf"))
        with tempfile.TemporaryDirectory() as d:
            for ext in ("gltf", "obj", "bvh", "c3d"):
                out = os.path.join(d, f"biped.{ext}")
                self.assertTrue(exporter.export_mocap(data, out, ExportSettings(format=ext)))
                result = exporter.validate_export(out)
                self.assertTrue(result["valid"], f"{ext} validation failed: {result}")
                self.assertGreater(result["file_size"], 0)

    def test_batch_export(self):
        exporter = Exporter(ExportSettings(format="gltf"))
        results = exporter.export_batch([], "/tmp/output")
        self.assertEqual(results, {})

    def test_convert_bvh_to_all(self):
        exporter = Exporter(ExportSettings(format="gltf"))
        with tempfile.TemporaryDirectory() as d:
            for ext in ("gltf", "obj", "c3d"):
                out = os.path.join(d, f"conv.{ext}")
                self.assertTrue(exporter.convert_format(FIXTURE_BVH, out))
                self.assertTrue(exporter.validate_export(out)["valid"])

    def test_convert_c3d_to_obj_gltf(self):
        exporter = Exporter(ExportSettings(format="gltf"))
        with tempfile.TemporaryDirectory() as d:
            c3d = os.path.join(d, "m.c3d")
            self.assertTrue(exporter.convert_format(FIXTURE_BVH, c3d))
            self.assertTrue(exporter.convert_format(c3d, os.path.join(d, "out.obj")))
            self.assertTrue(exporter.convert_format(c3d, os.path.join(d, "out.gltf")))


if __name__ == "__main__":
    unittest.main()