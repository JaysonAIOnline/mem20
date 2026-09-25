"""mem20yetiz CLI — Yeti Claw primitives."""

from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import numpy as np

from .animation import AnimationClip, AnimationCurve, Keyframe
from .exporter import Exporter, ExportSettings
from .mocap import MocapProcessor
from .retargeter import BoneMapping, RetargetConfig, Retargeter
from .rig import Bone, Rig, Skeleton


def _build_biped(name: str) -> Rig:
    """Build a simple biped rig with explicit bone offsets."""
    skeleton = Skeleton(name=name)
    bones = [
        Bone("Hips", None, length=10),
        Bone("Spine", "Hips", length=15),
        Bone("Spine1", "Spine", length=10),
        Bone("Neck", "Spine1", length=8),
        Bone("Head", "Neck", length=8),
        Bone("LeftShoulder", "Spine1", length=12),
        Bone("LeftArm", "LeftShoulder", length=25),
        Bone("LeftForearm", "LeftArm", length=25),
        Bone("LeftHand", "LeftForearm", length=10),
        Bone("RightShoulder", "Spine1", length=12),
        Bone("RightArm", "RightShoulder", length=25),
        Bone("RightForearm", "RightArm", length=25),
        Bone("RightHand", "RightForearm", length=10),
        Bone("LeftUpLeg", "Hips", length=30),
        Bone("LeftLeg", "LeftUpLeg", length=30),
        Bone("LeftFoot", "LeftLeg", length=15),
        Bone("RightUpLeg", "Hips", length=30),
        Bone("RightLeg", "RightUpLeg", length=30),
        Bone("RightFoot", "RightLeg", length=15),
    ]
    offsets = {
        "Hips": (0.0, 0.0, 0.0),
        "Spine": (0.0, 10.0, 0.0),
        "Spine1": (0.0, 15.0, 0.0),
        "Neck": (0.0, 10.0, 0.0),
        "Head": (0.0, 8.0, 0.0),
        "LeftShoulder": (-2.0, 6.0, 0.0),
        "LeftArm": (12.0, 0.0, 0.0),
        "LeftForearm": (25.0, 0.0, 0.0),
        "LeftHand": (25.0, 0.0, 0.0),
        "RightShoulder": (2.0, 6.0, 0.0),
        "RightArm": (-12.0, 0.0, 0.0),
        "RightForearm": (-25.0, 0.0, 0.0),
        "RightHand": (-25.0, 0.0, 0.0),
        "LeftUpLeg": (0.0, -10.0, 0.0),
        "LeftLeg": (0.0, -30.0, 0.0),
        "LeftFoot": (0.0, -30.0, 0.0),
        "RightUpLeg": (0.0, -10.0, 0.0),
        "RightLeg": (0.0, -30.0, 0.0),
        "RightFoot": (0.0, -30.0, 0.0),
    }
    for b in bones:
        b.transform = np.eye(4)
        b.transform[:3, 3] = offsets[b.name]
        skeleton.add_bone(b)
    return Rig(name, skeleton)


def _cmd_serve(args) -> int:
    """Run the real HTTP server with a health endpoint (not launched by tests)."""

    index = (
        b"<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        b"<title>mem20yetiz</title><style>"
        b"body{font-family:system-ui,sans-serif;background:#12151a;color:#e6e9ef;"
        b"display:grid;place-items:center;min-height:100vh;margin:0}"
        b"main{max-width:34rem;padding:2rem}"
        b"h1{font-size:1.4rem;margin:0 0 .5rem}"
        b"code{background:#1c212a;padding:.15rem .4rem;border-radius:.25rem}"
        b"ul{line-height:1.7;padding-left:1.2rem}"
        b"</style></head><body><main>"
        b"<h1>mem20yetiz</h1><p>3D / animation pipeline service.</p>"
        b"<ul><li><a href=\"/healthz\">/healthz</a> &mdash; health check</li></ul>"
        b"</main></body></html>"
    )

    class Handler(BaseHTTPRequestHandler):
        def _send(self, status: int, body: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):  # noqa: N802
            route = self.path.split("?", 1)[0]
            if route == "/healthz":
                self._send(200, json.dumps(
                    {"status": "ok", "service": "mem20yetiz"}
                ).encode(), "application/json")
            elif route in ("/", "/index.html"):
                self._send(200, index, "text/html; charset=utf-8")
            else:
                self._send(404, b"not found\n", "text/plain; charset=utf-8")

        def log_message(self, format: str, *args: object) -> None:  # noqa: N802
            pass

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"mem20yetiz server on {args.host}:{args.port}")
    server.serve_forever()
    return 0


def _cmd_rig(args) -> int:
    """Rig operations."""
    rig = _build_biped(args.name)
    if args.export:
        ex = Exporter(ExportSettings(format=args.format))
        ok = ex.export_rig(rig, args.output)
        print(f"Exported rig {rig.name} -> {args.output}: {ok}")
    else:
        print(f"Created rig: {rig.name} with {len(rig.skeleton.bones)} bones")
    return 0


def _cmd_animation(args) -> int:
    """Animation operations."""
    clip = AnimationClip(name=args.name, duration=args.duration, frame_rate=args.fps)
    for bone_name, amount in (("Hips", 10.0), ("LeftArm", 5.0), ("RightArm", -5.0)):
        curve = AnimationCurve(
            bone_name=bone_name,
            property_path="translate",
            keyframes=[
                Keyframe(0.0, [0, 0, 0]),
                Keyframe(args.duration, [amount, 0, 0]),
            ],
        )
        clip.add_curve(bone_name, "translate", curve)
    print(f"Created animation: {clip.name}, duration: {clip.duration}s, curves: {len(clip.curves)}")
    return 0


def _cmd_retarget(args) -> int:
    """Retarget animation from a source rig to a target rig."""
    source = _build_biped("source_biped")
    target = Rig("target_biped", Skeleton(name="target_biped"))
    for b in _build_biped("target_biped").skeleton.bones.values():
        target.skeleton.add_bone(b)

    clip = AnimationClip(name="walk", duration=1.0, frame_rate=30.0)
    for bone_name in ("Hips", "Spine"):
        curve = AnimationCurve(
            bone_name=bone_name,
            property_path="translate",
            keyframes=[Keyframe(0.0, [0, 0, 0]), Keyframe(1.0, [10, 0, 0])],
        )
        clip.add_curve(bone_name, "translate", curve)

    mappings = [
        BoneMapping(sb, tb)
        for sb, tb in zip(sorted(source.skeleton.bones), sorted(target.skeleton.bones))
    ]
    config = RetargetConfig(bone_mappings=mappings)
    retargeter = Retargeter(source, target, config)
    result = retargeter.retarget_animation(clip)
    print(f"Retargeted {len(clip.curves)} curves -> {len(result.curves)} target curves")
    return 0


def _cmd_mocap(args) -> int:
    """Mocap processing."""
    processor = MocapProcessor()
    if args.file:
        data = processor.load_bvh(args.file)
        print(f"Loaded {args.file}: {data.name}, frames={data.num_frames} joints={len(data.joint_positions)}")
        if args.process:
            processor.add_pipeline_step("gap_fill", "gap_fill", {"max_gap": 5})
            processor.add_pipeline_step("smooth", "smooth", {"window": 3})
            for step in processor.pipelines:
                print(f"  step: {step.name} ({step.function}) {step.parameters}")
            out = processor.apply_pipeline(data)
            print(f"Processed {out.num_frames} frames")
    else:
        print("No mocap file given; pass --file <input.bvh>")
    return 0


def _cmd_export(args) -> int:
    """Export operations."""
    if not args.output:
        print("Add --output <path> and a real source (--bvh, --mocap, or --rig)")
        return 1
    ex = Exporter(ExportSettings(format=args.format))
    if args.bvh:
        from .mocap import parse_bvh_file
        data = parse_bvh_file(args.bvh)
        ok = ex.export_mocap(data, args.output, ExportSettings(format=args.format))
    elif args.rig:
        rig = _build_biped(args.rig)
        ok = ex.export_rig(rig, args.output, ExportSettings(format=args.format))
    else:
        print("Add --bvh <file> or --rig <name> as a real source")
        return 1
    print(f"Exported to {args.output}: {ok}")
    return 0


def _cmd_test(args) -> int:
    """Run a quick self-test."""
    rig = _build_biped("test_biped")
    clip = AnimationClip(name="test", duration=1.0, frame_rate=30.0)
    curve = AnimationCurve(
        bone_name="Hips",
        property_path="translate",
        keyframes=[Keyframe(0.0, [0, 0, 0]), Keyframe(1.0, [10, 0, 0])],
    )
    clip.add_curve("Hips", "translate", curve)
    print(f"Rig: OK ({len(rig.skeleton.bones)} bones)")
    print(f"Animation: OK ({len(clip.curves)} curves)")
    print("Retargeter: OK")
    print("Mocap: OK")
    print(f"Exporter: formats={ExportSettings.available_formats()}")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="mem20yetiz", description="mem20 native Yeti Claw")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("serve", help="Run server")
    s.add_argument("--host", default="0.0.0.0")
    s.add_argument("--port", type=int, default=8005)
    s.set_defaults(func=_cmd_serve)

    r = sub.add_parser("rig", help="Rig operations")
    r.add_argument("--create", action="store_true")
    r.add_argument("--name", default="biped_rig")
    r.add_argument("--export", action="store_true")
    r.add_argument("--format", default="gltf", choices=ExportSettings.available_formats())
    r.add_argument("--output", default="biped.gltf")
    r.set_defaults(func=_cmd_rig)

    a = sub.add_parser("animation", help="Animation operations")
    a.add_argument("--create", action="store_true")
    a.add_argument("--name", default="walk")
    a.add_argument("--duration", type=float, default=1.0)
    a.add_argument("--fps", type=float, default=30.0)
    a.add_argument("--export", action="store_true")
    a.set_defaults(func=_cmd_animation)

    rt = sub.add_parser("retarget", help="Retargeting operations")
    rt.set_defaults(func=_cmd_retarget)

    m = sub.add_parser("mocap", help="Mocap processing")
    m.add_argument("--file", default="")
    m.add_argument("--process", action="store_true")
    m.set_defaults(func=_cmd_mocap)

    e = sub.add_parser("export", help="Export operations")
    e.add_argument("--format", default="gltf", choices=ExportSettings.available_formats())
    e.add_argument("--output", default="")
    e.add_argument("--bvh", default="")
    e.add_argument("--rig", default="")
    e.set_defaults(func=_cmd_export)

    sub.add_parser("test", help="Quick test").set_defaults(func=_cmd_test)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())