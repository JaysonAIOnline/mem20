"""CLI for mem20factoryz."""

from __future__ import annotations

import argparse
import json

from .assets import AssetSynthesizer, Palette
from .config import FactoryConfig
from .level import LevelBuilder
from .narrative import NarrativeEngine
from .playtest import Playtester


def _cmd_generate(args) -> int:
    cfg = FactoryConfig(seed=args.seed, width=args.width, height=args.height)
    builder = LevelBuilder(cfg)
    level = builder.build()
    if args.json:
        print(level.json())
    else:
        print(f"Level: {level.width}x{level.height} seed={cfg.seed} rooms={level.metadata['rooms']} entities={len(level.entities)} objectives={len(level.objectives)}")
    return 0


def _cmd_texture(args) -> int:
    cfg = FactoryConfig(seed=args.seed, asset_resolution=args.resolution)
    synth = AssetSynthesizer(cfg)
    pixels = synth.synthesise_texture(palette=Palette.from_seed(args.seed))
    path = args.out or f"/tmp/factoryz_texture_{args.seed}.ppm"
    synth.textures.export_ppm(pixels, path)
    print(f"Texture written: {path}")
    return 0


def _cmd_audio(args) -> int:
    cfg = FactoryConfig(seed=args.seed)
    synth = AssetSynthesizer(cfg)
    data = synth.synthesise_sfx()
    path = args.out or f"/tmp/factoryz_sfx_{args.seed}.wav"
    synth.audio.export_wav(data, path)
    print(f"SFX written: {path}")
    return 0


def _cmd_terrain(args) -> int:
    cfg = FactoryConfig(seed=args.seed, width=args.width, height=args.height)
    builder = LevelBuilder(cfg)
    tiles = builder.terrain_preview()
    print(f"Terrain {len(tiles)}x{len(tiles[0])}:")
    for row in tiles[: args.height if args.height <= 12 else 12]:
        print(" ".join(str(t) for t in row))
    return 0


def _cmd_story(args) -> int:
    eng = NarrativeEngine(seed=args.seed)
    beats = eng.generate(segments=args.segments)
    if args.json:
        print(json.dumps(eng.compile(), indent=2))
    else:
        for b in beats:
            print(f"[{b.index:02d}] ({b.kind:<10}) {b.text}")
    return 0


def _cmd_playtest(args) -> int:
    cfg = FactoryConfig(seed=args.seed)
    builder = LevelBuilder(cfg)
    level = builder.build()
    tester = Playtester(cfg)
    results = tester.run(level, runs=args.runs)
    agg = tester.aggregate(results)
    if args.json:
        print(json.dumps({"aggregate": agg, "runs": [r.summary() for r in results]}, indent=2))
    else:
        print(f"Playtest {args.runs} run(s):")
        for r in results:
            print(f"  seed={r.seed} completed={r.completed} steps={r.steps} deaths={r.deaths} loot={r.loot_collected}")
        print(f"  aggregate: {agg}")
    return 0


def _cmd_test(args) -> int:
    cfg = FactoryConfig(seed=args.seed)
    level = LevelBuilder(cfg).build()
    assert level.width == cfg.width and level.height == cfg.height
    eng = NarrativeEngine(cfg.seed)
    assert eng.quest_hooks()
    synth = AssetSynthesizer(cfg)
    pixels = synth.synthesise_texture()
    assert len(pixels) == cfg.asset_resolution
    assert synth.synthesise_sfx()
    tester = Playtester(cfg)
    results = tester.run(level, runs=2)
    assert len(results) == 2
    print("mem20factoryz test: ALL OK")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="mem20factoryz", description="Native mem20 GameFactory-3A")
    p.add_argument("--seed", type=int, default=20260910)
    sub = p.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("generate", help="Generate a level")
    g.add_argument("--width", type=int, default=64)
    g.add_argument("--height", type=int, default=64)
    g.add_argument("--json", action="store_true")
    g.set_defaults(func=_cmd_generate)

    t = sub.add_parser("texture", help="Generate a texture")
    t.add_argument("--resolution", type=int, default=32)
    t.add_argument("--out", default="")
    t.set_defaults(func=_cmd_texture)

    a = sub.add_parser("audio", help="Generate an SFX")
    a.add_argument("--out", default="")
    a.set_defaults(func=_cmd_audio)

    te = sub.add_parser("terrain", help="Preview terrain")
    te.add_argument("--width", type=int, default=64)
    te.add_argument("--height", type=int, default=64)
    te.set_defaults(func=_cmd_terrain)

    s = sub.add_parser("story", help="Generate narrative")
    s.add_argument("--segments", type=int, default=12)
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=_cmd_story)

    r = sub.add_parser("playtest", help="Simulate playthroughs")
    r.add_argument("--runs", type=int, default=5)
    r.add_argument("--json", action="store_true")
    r.set_defaults(func=_cmd_playtest)

    sub.add_parser("test", help="Run smoke test").set_defaults(func=_cmd_test)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())