# Audio Pipeline — Batch Renderer for The Unreliable Prophecy
# Renders all audio assets from FAUST sources and Surge patches
# Matches prod.md §10 audio asset list

import subprocess
import os
import json
from pathlib import Path

# Paths — resolve relative to the mem20owebz repo (no foreign machine paths).
# File: tools/audio/render/render_audio.py -> parents[3] = mem20owebz root.
REPO_ROOT = Path(__file__).resolve().parents[3]
AUDIO_ROOT = REPO_ROOT / "tools" / "audio"
FAUST_DIR = AUDIO_ROOT / "faust"
SURGE_PATCHES = AUDIO_ROOT / "surge_patches"
PROJECT_ROOT = os.environ.get(
    "MEM20OWEBZ_PROJECT_ROOT",
    str(REPO_ROOT / "projects"),
)
OUTPUT_DIR = Path(PROJECT_ROOT) / "unreliable_prophecy" / "engine_project" / "Assets" / "Audio"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# SFX from FAUST (matches prod.md §10.3). Each spec points at the real
# per-function .dsp file that exists under tools/audio/faust/.
SFX_SPECS = {
    "SFX_Stamp": {
        "source": "faust/StampImpact.dsp",
        "function": "stamp_impact",
        "duration": 2.0,
        "sample_rate": 48000,
    },
    "SFX_BureaucratPop": {
        "source": "faust/BureaucratPop.dsp",
        "function": "bureaucrat_pop",
        "duration": 1.0,
        "sample_rate": 48000,
    },
    "SFX_Paper": {
        "source": "faust/PaperRustle.dsp",
        "function": "paper_rustle",
        "duration": 1.5,
        "sample_rate": 48000,
    },
    "SFX_AttackSwingHit": {
        "source": "faust/AttackSwingHit.dsp",
        "function": "attack_swing_hit",
        "duration": 1.5,
        "sample_rate": 48000,
    },
    "SFX_EnemyHitDeath": {
        "source": "faust/EnemyHitDeath.dsp",
        "function": "enemy_hit_death",
        "duration": 1.0,
        "sample_rate": 48000,
    },
    "SFX_AmendmentStamp": {
        "source": "faust/AmendmentStamp.dsp",
        "function": "amendment_stamp",
        "duration": 2.0,
        "sample_rate": 48000,
    },
    "SFX_Footsteps": {
        "source": "faust/Footsteps.dsp",
        "function": "footstep_loop",
        "duration": 0.5,
        "sample_rate": 48000,
    },
    "SFX_AmbientQuietvale": {
        "source": "surge_patches/UP_Music.fxp",  # Surge patch
        "patch_name": "Quietvale_Morning",
        "duration": 60.0,  # 1 minute loop
        "sample_rate": 48000,
    },
    "SFX_AmbientHills": {
        "source": "surge_patches/UP_Music.fxp",
        "patch_name": "Hills_Office_Drone",
        "duration": 120.0,  # 2 minute loop
        "sample_rate": 48000,
    },
}

# Music tracks (from Surge patches + Spitfire LABS)
MUSIC_SPECS = {
    "MUS_Quietvale": {
        "source": "surge_patches/UP_Music.fxp",
        "patch_name": "Quietvale_Morning",
        "duration": 120.0,
        "sample_rate": 48000,
        "layers": ["piano", "drone"],
    },
    "MUS_Hills": {
        "source": "surge_patches/UP_Music.fxp",
        "patch_name": "Hills_Office_Drone",
        "duration": 180.0,
        "sample_rate": 48000,
        "layers": ["drone", "stamp_percussion"],
    },
    "MUS_Combat": {
        "source": "surge_patches/UP_Music.fxp",
        "patch_name": "Combat_Restrained",
        "duration": 90.0,
        "sample_rate": 48000,
        "layers": ["tension", "strings"],
    },
    "MUS_Boss": {
        "source": "surge_patches/UP_Music.fxp",
        "patch_name": "Boss_Seal_Motifs",
        "duration": 180.0,
        "sample_rate": 48000,
        "layers": ["seal", "tension", "choir"],
    },
    "MUS_Menu": {
        "source": "surge_patches/UP_Music.fxp",
        "patch_name": "Menu_Institutional",
        "duration": 60.0,
        "sample_rate": 48000,
        "layers": ["institutional"],
    },
}

# VO lines (from Piper TTS)
VO_SPECS = {
    "VO_Bureaucrat": {
        "lines": [
            "Prophecy forty-seven-B, revised.",
            "Sign here. And here. And here.",
            "Amendment one: the chosen one must file form 33-C.",
            "Amendment two: the prophecy is non-transferable.",
            "Compliance is not optional. It is documented.",
        ],
        "voice": "bureaucrat",
        "sample_rate": 22050,
    },
    "VO_Wizard": {
        "lines": [
            "Another prophecy. Joy.",
            "I have seen twelve chosen ones. You are adequate.",
            "The paperwork never ends. Neither do I, unfortunately.",
            "Try not to die. The forms for a replacement are tedious.",
        ],
        "voice": "wizard",
        "sample_rate": 22050,
    },
    "VO_Guidebook": {
        "lines": [
            "Welcome to your destiny. Please initial page one.",
            "Warning: chosen ones have a 94% mortality rate.",
            "The prophecy binder updates automatically. Do not resist.",
            "Secret ending unlocked. Prophecy forty-seven-C drafted.",
        ],
        "voice": "guidebook",
        "sample_rate": 22050,
    },
}

def run_cmd(cmd, cwd=None, timeout=60):
    try:
        result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        return {
            "success": result.returncode == 0,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "timeout"}
    except Exception as e:
        return {"success": False, "error": str(e)}

def render_faust_sfx(spec, output_path):
    """Render a single SFX from a per-function FAUST source file.

    Real pipeline: faust -lang cpp emits a dsp implementation, a tiny driver
    instantiates it (dsp API), renders `duration` seconds at `sample_rate`
    into a 16-bit PCM WAV. No placeholder/pretend output.
    """
    dsp_source = Path(AUDIO_ROOT) / spec["source"]

    if not dsp_source.is_file():
        return {"success": False, "error": f"DSP source missing: {dsp_source}"}

    content = dsp_source.read_text()
    if f"process = {spec['function']}" not in content:
        return {"success": False, "error": f"function {spec['function']} not found in {dsp_source.name}"}

    duration = float(spec.get("duration", 1.0))
    sample_rate = int(spec.get("sample_rate", 48000))
    num_frames = int(duration * sample_rate)

    workdir = OUTPUT_DIR / "sfx"
    workdir.mkdir(parents=True, exist_ok=True)
    gen_cpp = workdir / f"_render_{spec['function']}.cpp"
    driver_cpp = workdir / f"_driver_{spec['function']}.cpp"
    binary = workdir / f"_render_{spec['function']}.bin"

    # 1) faust -> C++ implementation with the standard dsp API.
    compile_check = run_cmd(
        ["faust", "-lang", "cpp", "-cn", spec["function"], "-o", str(gen_cpp), str(dsp_source)],
        timeout=60,
    )
    if not compile_check.get("success"):
        return {"success": False, "error": compile_check.get("stderr", compile_check.get("error", "faust compile failed"))}
    if not gen_cpp.is_file():
        return {"success": False, "error": f"faust did not produce {gen_cpp}"}

    # 2) Driver: instantiate the DSP, render N frames, write 16-bit PCM WAV.
    # The generated class name is `spec["function"]` (from -cn). dsp.h + gui
    # headers complete the Meta/UI base types the generated code inherits.
    driver_cpp.write_text(f'''
#include <fstream>
#include <cmath>
#include <memory>
#include "faust/gui/meta.h"
#include "faust/gui/UI.h"
#include "faust/dsp/dsp.h"
#include "{gen_cpp.name}"

int main() {{
    std::unique_ptr<dsp> dsp(new FAUSTCLASS());
    int sr = {sample_rate};
    dsp->init(sr);
    long n = {num_frames};
    float* buf = new float[n];
    // One output channel feeds buf; inputs/residual channel are placeholders.
    float* in[1];
    float* out[1] = {{ buf }};
    for (long i = 0; i < n; i ++) {{
        dsp->compute(1, in, out);
    }}
    std::ofstream wav("{output_path}", std::ios::binary);
    if (!wav) return 2;
    const int channels = 1;
    const int bits = 16;
    wav.write("RIFF", 4);
    uint32_t data_size = (uint32_t)(n * channels * bits / 8);
    uint32_t riff_size = 36 + data_size;
    wav.write(reinterpret_cast<const char*>(&riff_size), 4);
    wav.write("WAVEfmt ", 8);
    uint32_t fmt_size = 16;
    wav.write(reinterpret_cast<const char*>(&fmt_size), 4);
    uint16_t fmt = 1;
    wav.write(reinterpret_cast<const char*>(&fmt), 2);
    uint16_t ch = (uint16_t)channels;
    wav.write(reinterpret_cast<const char*>(&ch), 2);
    wav.write(reinterpret_cast<const char*>(&sr), 4);
    uint32_t byte_rate = (uint32_t)(sr * channels * bits / 8);
    wav.write(reinterpret_cast<const char*>(&byte_rate), 4);
    uint16_t block_align = (uint16_t)(channels * bits / 8);
    wav.write(reinterpret_cast<const char*>(&block_align), 2);
    uint16_t bps = bits;
    wav.write(reinterpret_cast<const char*>(&bps), 2);
    wav.write("data", 4);
    wav.write(reinterpret_cast<const char*>(&data_size), 4);
    for (long i = 0; i < n; i ++) {{
        float v = buf[i];
        if (v > 1.0f) v = 1.0f;
        if (v < -1.0f) v = -1.0f;
        short s = (short)(v * 32767.0f);
        wav.write(reinterpret_cast<const char*>(&s), 2);
    }}
    wav.close();
    delete[] buf;
    return 0;
}}
''')

    build = run_cmd(
        ["g++", "-O2", "-std=c++14", "-I" + str(gen_cpp.parent), str(driver_cpp), "-o", str(binary), "-lm"],
        timeout=120,
    )
    if not build.get("success"):
        return {"success": False, "error": build.get("stderr", build.get("error", "g++ build failed"))}

    run = run_cmd([str(binary)], timeout=int(duration * 2) + 30)
    for f in (gen_cpp, driver_cpp, binary):
        try:
            f.unlink()
        except OSError:
            pass

    if not run.get("success"):
        return {"success": False, "error": run.get("stderr", run.get("error", f"render binary failed with rc={run.get('returncode')}"))}
    if not Path(output_path).is_file() or Path(output_path).stat().st_size == 0:
        return {"success": False, "error": f"render produced no WAV at {output_path}"}
    return {"success": True, "output": str(output_path), "frames": num_frames, "sample_rate": sample_rate}

def render_piper_vo(lines, voice, output_dir):
    """Render VO lines using Piper TTS."""
    results = []
    for i, line in enumerate(lines):
        output_path = output_dir / f"vo_{i:03d}.wav"
        cmd = [
            "/root/.venv/bin/python3", "-c",
            f"import piper; v = piper.PiperVoice.load('en_US-lessac-medium'); v.synthesize('{line}', '{output_path}')"
        ]
        result = run_cmd(cmd, timeout=30)
        results.append({"line": line, "result": result, "output": output_path})
    return results

def render_surge_patch(patch_file, patch_name, duration, output_path):
    """Render a Surge patch for given duration."""
    # Use surge-xt CLI
    # surge-xt --render --patch patch.fxp --patch-name "PatchName" --output out.wav --duration 60
    cmd = [
        "surge-xt",
        "--render",
        "--patch", patch_file,
        "--patch-name", patch_name,
        "--output", str(output_path),
        "--duration", str(int(duration))
    ]
    return run_cmd(cmd, timeout=120)

def main():
    import subprocess
    
    print("=== AUDIO PIPELINE RENDERER ===")
    print(f"Output: {OUTPUT_DIR}")
    
    # Create output directories
    (OUTPUT_DIR / "sfx").mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "music").mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "vo").mkdir(parents=True, exist_ok=True)
    
    # Render SFX from FAUST
    print("\n--- Rendering SFX from FAUST ---")
    for name, spec in SFX_SPECS.items():
        print(f"Rendering {name}...")
        result = render_faust_sfx(spec, OUTPUT_DIR / "sfx" / f"{name}.wav")
        if result.get("success"):
            print(f"  ✓ {name}")
        else:
            print(f"  ✗ {name}: {result.get('stderr', result.get('error'))}")
    
    # Render VO from Piper
    print("\n--- Rendering VO from Piper TTS ---")
    for name, spec in VO_SPECS.items():
        print(f"Rendering {name}...")
        results = render_piper_vo(spec["lines"], spec["voice"], OUTPUT_DIR / "vo" / name.lower())
        for r in results:
            if r["result"].get("success"):
                print(f"  ✓ {r['line'][:40]}...")
            else:
                print(f"  ✗ {r['line'][:40]}...: {r['result'].get('stderr', r['result'].get('error'))}")
    
    # Render Music from Surge (if patches exist)
    print("\n--- Rendering Music from Surge ---")
    if (AUDIO_ROOT / "surge_patches" / "UP_Music.fxp").exists():
        for name, spec in MUSIC_SPECS.items():
            print(f"Rendering {name}...")
            output_path = OUTPUT_DIR / "music" / f"{name}.wav"
            result = render_surge_patch(
                AUDIO_ROOT / "surge_patches" / "UP_Music.fxp",
                spec["patch_name"],
                spec["duration"],
                output_path
            )
            if result.get("success"):
                print(f"  ✓ {name}")
            else:
                print(f"  ✗ {name}: {result.get('stderr', result.get('error'))}")
    else:
        print("  Surge patch file not found, skipping music rendering")
    
    print("\n=== RENDER COMPLETE ===")
    print(f"Output directory: {OUTPUT_DIR}")

if __name__ == "__main__":
    main()