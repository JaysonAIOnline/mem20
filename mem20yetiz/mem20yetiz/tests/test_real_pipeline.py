from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from mem20yetiz import gltf, obj
from mem20yetiz.mocap import (
    MarkerSet,
    MocapData,
    MocapFrame,
    MocapProcessor,
    load_c3d,
    mocap_to_animation,
    parse_bvh_file,
    track_markers,
    write_c3d,
)

FIXTURE = Path(__file__).parent / "fixtures" / "biped_test.bvh"


def test_bvh_exposes_real_kinematics() -> None:
    data = parse_bvh_file(str(FIXTURE))
    assert data.metadata["hierarchy_depth"] == 3
    assert data.metadata["n_frames"] == 3
    assert data.metadata["frame_time"] == pytest.approx(0.033333333)
    assert data.joint_positions["Spine"].shape == (3, 3)
    assert data.joint_world_rotations["Spine"].shape == (3, 3, 3)
    assert data.local_joint_rotations["Spine"].shape == (3, 3, 3)
    assert data.hierarchy["Spine"].channels == ["Zrotation", "Xrotation", "Yrotation"]
    np.testing.assert_allclose(data.joint_positions["Spine"][1], [0.0, 8.660254037844386, 0.0], atol=1e-6)


def test_mocap_to_animation_uses_local_transforms() -> None:
    data = parse_bvh_file(str(FIXTURE))
    clip = mocap_to_animation(data, data.to_rig())
    root = clip.get_curve("Hips", "translate")
    spine = clip.get_curve("Spine", "translate")
    assert root is not None
    assert spine is not None
    np.testing.assert_allclose(root.evaluate(0.0), [0.0, 0.0, 0.0], atol=1e-6)
    np.testing.assert_allclose(spine.evaluate(0.0), [0.0, 10.0, 0.0], atol=1e-6)
    np.testing.assert_allclose(spine.evaluate(1 / 30.0), [0.0, 10.0, 0.0], atol=1e-6)


def test_cleanup_filter_processes_bvh_joint_trajectories() -> None:
    data = parse_bvh_file(str(FIXTURE))
    processor = MocapProcessor()
    processor.add_pipeline_step("filter", "filter", {"cutoff": 4.0, "order": 2})
    filtered = processor.apply_pipeline(data)
    assert filtered.joint_positions["Spine"].shape == (3, 3)
    assert np.all(np.isfinite(filtered.joint_positions["Spine"]))
    assert filtered.metadata["butterworth"]["fs"] == pytest.approx(30.0000003)


def test_marker_tracking_infers_observation_names_and_reidentifies() -> None:
    data = MocapData(name="markers", frame_rate=30.0)
    data.frames = [
        MocapFrame(
            frame_number=0,
            timestamp=0.0,
            marker_positions={"sensor_0": np.array([0.0, 1.0, 0.0]), "sensor_1": np.array([0.0, -1.0, 0.0])},
        ),
        MocapFrame(
            frame_number=1,
            timestamp=1 / 30.0,
            marker_positions={"sensor_0": np.array([0.0, -1.0, 0.0]), "sensor_1": np.array([0.0, 1.0, 0.0])},
        ),
    ]
    marker_set = MarkerSet(
        name="body",
        markers=["left", "right"],
        template={"left": np.array([0.0, 1.0, 0.0]), "right": np.array([0.0, -1.0, 0.0])},
    )
    tracked = track_markers(data, marker_set)
    assert tracked.marker_names == ["left", "right"]
    np.testing.assert_allclose(tracked.frames[0].marker_positions["left"], [0.0, 1.0, 0.0], atol=1e-6)
    np.testing.assert_allclose(tracked.frames[1].marker_positions["left"], [0.0, 1.0, 0.0], atol=1e-6)


def test_gltf_roundtrip_reparses_binary_animation_and_hierarchy(tmp_path: Path) -> None:
    data = parse_bvh_file(str(FIXTURE))
    rig = data.to_rig()
    clip = mocap_to_animation(data, rig)
    path = tmp_path / "capture.gltf"
    assert gltf.export_gltf(rig, clip, str(path))
    document = json.loads(path.read_text(encoding="utf-8"))
    assert document["asset"]["version"] == "2.0"
    assert document["buffers"][0]["uri"] == "capture.bin"
    assert (tmp_path / "capture.bin").stat().st_size == document["buffers"][0]["byteLength"]
    loaded = gltf.load_gltf(str(path))
    assert loaded["valid"] is True
    assert loaded["node_parents"]["Spine"] == "Hips"
    assert loaded["animation_data"][0]["channels"]
    assert loaded["animation_samples"]["Hips.translation"][1][1][0] == pytest.approx(5.0)
    assert loaded["animation_samples"]["Spine.translation"][1][1][0] == pytest.approx(0.0)


def test_obj_roundtrip_preserves_first_frame_and_bone_edges(tmp_path: Path) -> None:
    data = parse_bvh_file(str(FIXTURE))
    path = tmp_path / "capture.obj"
    assert obj.write_obj_from_positions(data.name, data.joint_positions, str(path), data.hierarchy)
    loaded = obj.load_obj(str(path))
    assert loaded["n_vertices"] == len(data.joint_positions)
    for name, trajectory in data.joint_positions.items():
        index = loaded["vertex_names"].index(name)
        np.testing.assert_allclose(loaded["vertices"][index], trajectory[0], atol=1e-5)
    parent_index = loaded["vertex_names"].index("Hips")
    spine_index = loaded["vertex_names"].index("Spine")
    assert [parent_index + 1, spine_index + 1] in loaded["lines"]
    assert loaded["n_lines"] == sum(1 for joint in data.hierarchy.values() if joint.parent and not joint.is_end_site)


def test_bvh_roundtrip_preserves_hierarchy_channels_and_fk(tmp_path: Path) -> None:
    data = parse_bvh_file(str(FIXTURE))
    path = tmp_path / "roundtrip.bvh"
    from mem20yetiz.mocap import write_bvh

    assert write_bvh(data, str(path))
    reparsed = parse_bvh_file(str(path))
    assert reparsed.root_joint == data.root_joint
    assert reparsed.channel_names == data.channel_names
    assert reparsed.metadata["hierarchy_depth"] == data.metadata["hierarchy_depth"]
    for name in data.joint_positions:
        np.testing.assert_allclose(reparsed.joint_positions[name], data.joint_positions[name], atol=1e-4)


def test_c3d_point_roundtrip_preserves_marker_positions(tmp_path: Path) -> None:
    data = parse_bvh_file(str(FIXTURE))
    path = tmp_path / "capture.c3d"
    assert write_c3d(data, str(path))
    loaded = load_c3d(str(path))
    assert loaded.metadata["c3d_float_type"] == "ieee-float"
    assert loaded.marker_names
    for name in loaded.marker_names:
        np.testing.assert_allclose(
            np.asarray([frame.marker_positions[name] for frame in loaded.frames]),
            data.joint_positions[name],
            atol=1e-4,
        )


def test_glb_conversion_is_not_fake_zero_geometry(tmp_path: Path) -> None:
    from mem20yetiz.exporter import Exporter

    exporter = Exporter()
    gltf_path = tmp_path / "rig.gltf"
    obj_path = tmp_path / "rig.obj"
    data = parse_bvh_file(str(FIXTURE))
    assert exporter.export_mocap(data, str(gltf_path))
    assert exporter.convert_format(str(gltf_path), str(obj_path))
    loaded = obj.load_obj(str(obj_path))
    assert loaded["n_vertices"] == sum(1 for joint in data.hierarchy.values() if not joint.is_end_site)
    assert any(np.linalg.norm(np.asarray(loaded["vertices"][i])) > 0 for i in range(loaded["n_vertices"]))


def test_retarget_pipeline_reconstructs_world_positions() -> None:
    data = parse_bvh_file(str(FIXTURE))
    target = data.to_rig()
    processor = MocapProcessor()
    processor.add_pipeline_step("retarget", "retarget", {"target_rig": target})
    retargeted = processor.apply_pipeline(data)
    assert retargeted.num_frames == data.num_frames
    for name in ("Hips", "Spine", "Neck"):
        np.testing.assert_allclose(retargeted.joint_positions[name], data.joint_positions[name], atol=2e-5)


def test_optional_trimesh_reimports_both_export_formats(tmp_path: Path) -> None:
    trimesh = pytest.importorskip("trimesh")
    from mem20yetiz.exporter import Exporter, ExportSettings

    data = parse_bvh_file(str(FIXTURE))
    for extension in ("gltf", "obj"):
        path = tmp_path / f"capture.{extension}"
        assert Exporter(ExportSettings(format=extension)).export_mocap(data, str(path))
        scene = trimesh.load(str(path), force="scene")
        assert isinstance(scene, trimesh.Scene)


def test_animation_export_uses_real_clip_data(tmp_path: Path) -> None:
    from mem20yetiz.exporter import Exporter, ExportSettings

    data = parse_bvh_file(str(FIXTURE))
    clip = mocap_to_animation(data, data.to_rig())
    path = tmp_path / "clip.gltf"
    assert Exporter(ExportSettings(format="gltf")).export_animation(clip, str(path))
    loaded = gltf.load_gltf(str(path))
    assert loaded["valid"] is True
    assert "Hips" in loaded["names"]
    assert loaded["animation_samples"]["Hips.translation"][1][1][0] == pytest.approx(5.0)


def test_gltf_roundtrip_reconstructs_all_sampled_world_positions(tmp_path: Path) -> None:
    data = parse_bvh_file(str(FIXTURE))
    rig = data.to_rig()
    clip = mocap_to_animation(data, rig)
    path = tmp_path / "full.gltf"
    assert gltf.export_gltf(rig, clip, str(path))
    loaded = gltf.load_gltf(str(path))
    samples = loaded["animation_samples"]
    frames = len(samples["Hips.translation"][0])
    world: dict[tuple[str, int], np.ndarray] = {}

    def resolve(name: str, frame: int) -> np.ndarray:
        key = (name, frame)
        if key in world:
            return world[key]
        matrix = np.eye(4)
        matrix[:3, 3] = samples[f"{name}.translation"][1][frame]
        matrix[:3, :3] = gltf.quaternion_to_matrix(samples[f"{name}.rotation"][1][frame].tolist())
        parent = loaded["node_parents"][name]
        if parent is not None:
            matrix = resolve(parent, frame) @ matrix
        world[key] = matrix
        return matrix

    for frame in range(frames):
        for name in data.hierarchy:
            if not data.hierarchy[name].is_end_site:
                np.testing.assert_allclose(resolve(name, frame)[:3, 3], data.joint_positions[name][frame], atol=2e-5)
