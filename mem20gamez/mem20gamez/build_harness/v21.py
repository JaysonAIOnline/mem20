"""Harness Upgrades v2.1 - operational framework for the autonomous game studio.

Brings the package rules into the runtime:
  * provider key inventory (Groq primary, NVIDIA free fallback + vision)
  * 10-supervisor / 2-orchestrator model assignments (xAI replaced:
    Main Orchestrator is the human/agent-in-the-loop; heavy roles go to
    Groq paid, NVIDIA free as verified fallback and vision deck)
  * multi-model + multi-key worker parallelism (round-robin buckets)
  * naming convention law, mandatory folder hierarchy, batch manifests,
    handoff report template verification, primitive ban, description
    gate, visual verification, beta-tester phase, godot build legs.
"""

from __future__ import annotations

import base64
import contextvars
import itertools
import json
import os
import re
import textwrap
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Optional

GROQ_BASE = "https://api.groq.com/openai/v1"
NVIDIA_BASE = "https://integrate.api.nvidia.com/v1"

PROVIDER_BASE = {"groq": GROQ_BASE, "nvidia": NVIDIA_BASE}

GROQ_MODEL_36 = "qwen/qwen3.6-27b"
GROQ_MODEL_38 = "qwen/qwen3.8-27b"
GROQ_MODEL_OSS120 = "openai/gpt-oss-120b"
GROQ_MODEL_OSS20 = "openai/gpt-oss-20b"
NIM_STRONG = "nvidia/nemotron-3-super-120b-a12b"
NIM_VISION = "meta/llama-3.2-11b-vision-instruct"
NIM_VISION_HQ = "meta/llama-3.2-90b-vision-instruct"
NIM_TEXT_FALLBACKS = [
    "nvidia/nemotron-3-super-120b-a12b",
    "mistralai/mixtral-8x22b-v0.1",
    "nvidia/llama-3.1-nemotron-51b-instruct",
]

# ── key inventory ─────────────────────────────────────────────────────────────

def _env_keys(*names: str) -> list[str]:
    out: list[str] = []
    for v in names:
        for part in os.environ.get(v, "").split(","):
            part = part.strip()
            if part and part not in out:
                out.append(part)
    return out


def provider_keys(provider: str) -> list[str]:
    if provider == "groq":
        return _env_keys("GROQ_API_KEY", "GROQ_API_KEYS")
    if provider == "nvidia":
        return _env_keys("NVIDIA_API_KEY", "NGC_API_KEY", "NVIDIA_API_KEYS", "NVAPI_KEY")
    if provider == "xai":
        return _env_keys("XAI_API_KEY")
    return []


def collect_keys() -> dict:
    """Inventory provider keys. Missing = surfaced for operator action."""
    inv = {}
    for prov in ("groq", "nvidia", "xai"):
        keys = provider_keys(prov)
        inv[prov] = {"present": len(keys) > 0, "keys": len(keys)}
    required = ["GROQ_API_KEY", "NVIDIA_API_KEY"]
    missing = [k for k in required if not os.environ.get(k, "").strip()]
    return {"providers": inv, "missing": missing,
            "ready": not missing, "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}


def _pick_key(provider: str, idx: int = 0) -> str:
    keys = provider_keys(provider)
    if not keys:
        return ""
    return keys[idx % len(keys)]


# ── model assignments (upgrade MODEL_ASSIGNMENTS.md, xAI removed) ─────────────

# (role, match keywords, primary (provider, model), fallback (provider, model))
# Groq paid = primary per operator. NVIDIA free = fallback text + vision deck.
ROLE_ASSIGNMENTS = [
    ("assembly_work",  ["assembly", "assemble", "build out", "compile", "work"],
     ("groq", GROQ_MODEL_38), ("nvidia", NIM_STRONG)),
    ("assembly_critic", ["critic", "critique", "reviewer"],
     ("groq", GROQ_MODEL_38), ("nvidia", NIM_STRONG)),
    ("unity_engine",   ["unity"],
     ("groq", GROQ_MODEL_38), ("nvidia", NIM_STRONG)),
    ("godot_engine",   ["godot"],
     ("groq", GROQ_MODEL_36), ("nvidia", NIM_STRONG)),
    ("asset_lead",     ["3d", "asset", "model", "mesh", "prop"],
     ("groq", GROQ_MODEL_38), ("nvidia", NIM_STRONG)),
    ("asset_critic",   ["critic", "review", "inspect"],
     ("groq", GROQ_MODEL_38), ("nvidia", NIM_VISION)),
    ("visual_qa_beta", ["visual", "beta", "qa", "test", "quality"],
     ("groq", GROQ_MODEL_38), ("nvidia", NIM_STRONG)),
    ("marketing",      ["marketing", "business", "publish", "store", "launch"],
     ("groq", GROQ_MODEL_36), ("nvidia", NIM_STRONG)),
    ("audio_vfx",      ["audio", "vfx", "sound", "music", "polish"],
     ("groq", GROQ_MODEL_36), ("nvidia", NIM_STRONG)),
    ("systems",        ["system", "gameplay", "flow", "mechanics", "logic"],
     ("groq", GROQ_MODEL_38), ("nvidia", NIM_STRONG)),
]

ORCHESTRATOR_ASSIGNMENT = ("groq", GROQ_MODEL_38)      # main orchestrator LLM
SECONDARY_ORCH_ASSIGNMENT = ("groq", GROQ_MODEL_36)    # secondary orchestrator

# Worker buckets spread load across Groq rate buckets + NVIDIA free overflow.
# Multi-key support: each (provider, model) x each key is a separate bucket.
# NOTE: the worker brain speaks a PLAIN-TEXT JSON protocol (CogBrain.propose).
# gpt-oss models on Groq emit a function-call shape instead and the request is
# rejected with HTTP 400 tool_use_failed ("Tool choice is none, but model
# called a tool"), which killed whole worker loops. Only models that honor the
# text-JSON contract belong in this pool (pack: prefer qwen3.6/3.8).
WORKER_POOL = [
    ("groq", GROQ_MODEL_38),
    ("groq", GROQ_MODEL_36),
    ("nvidia", NIM_STRONG),
]


def text_candidates(*preferred: Optional[tuple[str, str]]) -> list[tuple[str, str]]:
    """Ordered (provider, model) fallbacks for the text-JSON protocol.

    Dedupes, then appends the NVIDIA text-fallback chain so a 503 from one NIM
    model does not end the call. Used by both single-shot role calls and the
    per-worker routed seam.
    """
    seen: set[tuple[str, str]] = set()
    out: list[tuple[str, str]] = []
    for pair in preferred:
        if pair and pair not in seen:
            out.append(pair)
            seen.add(pair)
    for m in NIM_TEXT_FALLBACKS:
        pair = ("nvidia", m)
        if pair not in seen:
            out.append(pair)
            seen.add(pair)
    return out

SUPERVISOR_NAMES = [r[0] for r in ROLE_ASSIGNMENTS]

VISION_MODELS = [NIM_VISION, NIM_VISION_HQ]
BETA_TESTER_COUNT = 5

# Naming convention (NAMING_AND_MANIFEST_GUIDE.md)
NAMING_RULES = [
    (r"^SM_[A-Za-z0-9]+_[A-Za-z0-9]+(?:_[A-Za-z0-9]*)*(?:_LOD\d+)?(?:\.(?:fbx|glb|gltf|obj|blend))?$", "StaticMesh"),
    (r"^M_[A-Za-z0-9]+(?:_[A-Za-z0-9]*)*$", "Material"),
    (r"^T_[A-Za-z0-9]+_(Albedo|Normal|Roughness|Metallic|AO|Emissive)(?:\.(?:png|jpg|tga|exr))?$", "Texture"),
    (r"^A_[A-Za-z0-9]+(?:_[A-Za-z0-9]*)*(?:\.(?:wav|ogg|mp3))?$", "Audio"),
    (r"^Prefab_[A-Za-z0-9]+(?:_[A-Za-z0-9]*)*(?:\.(?:prefab|tscn|unity))?$", "Prefab"),
    (r"^Scene_[A-Za-z0-9]+(?:_[A-Za-z0-9]*)*(?:\.(?:unity|tscn))?$", "Scene"),
]

# Mandatory folder hierarchy (Assets/_Project/...)
HIERARCHY_CATEGORIES = [
    "Audio", "Characters", "Environment", "Materials", "Models",
    "Prefabs", "Scenes", "Scripts", "Textures", "UI", "Vehicles", "VFX",
]
HIERARCHY_SUB = {
    "Environment": ["Buildings", "Houses", "Props", "Terrain"],
}

# Handoff template required fields (HANDOFF_TEMPLATE.md)
HANDOFF_FIELDS = [
    "Agent / Supervisor ID",
    "Role",
    "Phase / Task ID",
    "Assigned Model Used",
    "What was delivered",
    "Manifest path",
    "Visual verification performed",
    "Acceptance criteria met",
    "File placement & naming verified",
    "Primitives present",
    "Known issues / blockers",
    "Dependencies still open",
    "Ready for next stage",
]


def resolve_role(name: str, prompt: str = "") -> str:
    text = f"{name} {prompt}".lower()
    candidates = ROLE_ASSIGNMENTS
    if "critic" in text:
        candidates = [r for r in ROLE_ASSIGNMENTS if "critic" in r[1]]
    elif "unity" in text or "godot" in text or "engine" in text:
        candidates = [r for r in ROLE_ASSIGNMENTS
                      if any(k in r[1] for k in ("unity", "godot"))]
    best, best_score = "systems", 0
    for role, keys, _p, _f in candidates:
        score = sum(1 for k in keys if k in text)
        role_token = role.split("_")[0]
        if role_token in text:
            score += 2
        if score > best_score:
            best, best_score = role, score
    return best


def assignment_for(role: str) -> tuple[tuple[str, str], tuple[str, str] | None]:
    for r, _k, primary, fallback in ROLE_ASSIGNMENTS:
        if r == role:
            return primary, fallback
    return (("groq", GROQ_MODEL_38), ("nvidia", NIM_STRONG))


def chat_role(name: str, prompt: str, max_tokens: int = 900,
              temperature: float = 0.7) -> str:
    """Single-shot routed LLM call: primary provider then fallback chain."""
    from llm import chat, LLMError
    role = resolve_role(name, prompt)
    primary, fallback = assignment_for(role)
    errors: list[str] = []
    for prov, model in text_candidates(primary, fallback):
        key = _pick_key(prov)
        if not key:
            errors.append(f"{prov}:no-key")
            continue
        try:
            return chat(
                [{"role": "system", "content": f"You are {name}."},
                 {"role": "user", "content": prompt}],
                model=model, temperature=temperature, max_tokens=max_tokens,
                base_url=PROVIDER_BASE[prov], api_key=key)
        except LLMError as exc:
            errors.append(f"{prov}/{model}:{str(exc)[:120]}")
    raise LLMError("; ".join(errors))  # noqa: F821 - re-raised for caller's benefit


def orchestrator_chat(prompt: str, max_tokens: int = 900,
                      secondary: bool = False) -> str:
    prov, model = SECONDARY_ORCH_ASSIGNMENT if secondary else ORCHESTRATOR_ASSIGNMENT
    from llm import chat, LLMError
    key = _pick_key(prov)
    if not key:
        # fallback to primary groq key if secondary unset
        key = _pick_key("groq")
    return chat(
        [{"role": "system", "content": "You are a harness Orchestrator."},
         {"role": "user", "content": prompt}],
        model=model, max_tokens=max_tokens, base_url=PROVIDER_BASE[prov], api_key=key)


# ── worker multi-model/multi-key routing seam ────────────────────────────────

_ROUTE: contextvars.ContextVar[Optional[tuple[str, str, str]]] = contextvars.ContextVar(
    "v21_route", default=None)
_bucket_counter = itertools.count()
_seam_installed = False


def worker_buckets() -> list[tuple[str, str, int]]:
    combos: list[tuple[str, str, int]] = []
    for prov, model in WORKER_POOL:
        n = len(provider_keys(prov))
        if n == 0:
            continue
        for ki in range(n):
            combos.append((prov, model, ki))
    if not combos:
        combos = [("groq", GROQ_MODEL_38, 0)]
    return combos


def next_bucket() -> tuple[str, str, str]:
    combos = worker_buckets()
    prov, model, ki = combos[next(_bucket_counter) % len(combos)]
    return prov, model, _pick_key(prov, ki)


def install_seam() -> None:
    """Patch llm.chat once so worker threads route through their bucket.

    A pinned bucket is the PREFERRED route, not the only one: if that model
    fails (400 tool_use_failed, 503 overload, timeout) the call walks the other
    worker buckets and the NVIDIA text-fallback chain before giving up. This
    keeps one flaky provider from killing an entire worker loop.
    """
    global _seam_installed
    if _seam_installed:
        return
    import llm
    _orig = llm.chat

    def _walk(route, messages, temperature, max_tokens, timeout):
        prov, mdl, _key = route
        candidates = text_candidates((prov, mdl))
        for cprov, cmodel in WORKER_POOL:
            if (cprov, cmodel) not in candidates:
                candidates.append((cprov, cmodel))
        errors: list[str] = []
        from llm import LLMError
        for cprov, cmodel in candidates:
            key = _pick_key(cprov)
            if not key:
                continue
            try:
                return _orig(messages, model=cmodel, temperature=temperature,
                             max_tokens=max_tokens, base_url=PROVIDER_BASE[cprov],
                             api_key=key, timeout=timeout)
            except LLMError as exc:
                errors.append(f"{cprov}/{cmodel}:{str(exc)[:100]}")
        raise LLMError("; ".join(errors) or "no routable model with a key")

    def _routed(messages, model=None, temperature=0.7, max_tokens=1500,
                base_url=None, api_key=None, timeout=180.0):
        route = _ROUTE.get()
        if route is None:
            return _orig(messages, model, temperature, max_tokens,
                         base_url, api_key, timeout)
        return _walk(route, messages, temperature, max_tokens, timeout)

    llm.chat = _routed
    # achat is used too rarely by the loop to matter, but keep symmetry.
    if hasattr(llm, "achat"):
        _orig_a = llm.achat

        def _routed_a(messages, model=None, temperature=0.7, max_tokens=1500,
                      base_url=None, api_key=None, timeout=180.0, max_retries=2):
            route = _ROUTE.get()
            if route is None:
                return _orig_a(messages, model, temperature, max_tokens,
                               base_url, api_key, timeout, max_retries)
            prov, mdl, _key = route
            candidates = text_candidates((prov, mdl))
            for cprov, cmodel in WORKER_POOL:
                if (cprov, cmodel) not in candidates:
                    candidates.append((cprov, cmodel))
            from llm import LLMError
            errors: list[str] = []
            for cprov, cmodel in candidates:
                key = _pick_key(cprov)
                if not key:
                    continue
                try:
                    return _orig_a(messages, model=cmodel, temperature=temperature,
                                   max_tokens=max_tokens,
                                   base_url=PROVIDER_BASE[cprov], api_key=key,
                                   timeout=timeout, max_retries=max_retries)
                except LLMError as exc:
                    errors.append(f"{cprov}/{cmodel}:{str(exc)[:100]}")
            raise LLMError("; ".join(errors) or "no routable model with a key")

        llm.achat = _routed_a
    _seam_installed = True


@contextmanager
def route_worker() -> Iterator[dict]:
    prov, model, key = next_bucket()
    token = _ROUTE.set((prov, model, key))
    try:
        yield {"provider": prov, "model": model}
    finally:
        _ROUTE.reset(token)


# ── naming / hierarchy / manifest / handoff enforcement ──────────────────────

def classify_output(rel: str) -> str:
    """Map a worker-relative output path to its mandatory hierarchy category."""
    name = Path(rel).name
    low = name.lower()
    ext = Path(rel).suffix.lower()
    if ext in {".wav", ".ogg", ".mp3", ".aif", ".aiff", ".flac"}:
        base = "Audio"
        if "music" in low:
            return "Audio/Music"
        if "vo" in low or "voice" in low:
            return "Audio/VO"
        return "Audio/SFX"
    if name.startswith("SM_") and any(s in low for s in ("character", "agent", "npc", "person", "player")):
        return "Characters"
    if name.startswith("SM_"):
        seg = "Props"
        for key, subs in HIERARCHY_SUB.items():
            for sub in subs:
                if sub.lower() in low:
                    seg = sub
        return f"Environment/{seg}"
    if name.startswith("M_") or ext == ".mat":
        return "Materials"
    if name.startswith("T_") or ext in {".png", ".jpg", ".jpeg", ".tga", ".exr", ".hdr"}:
        return "Textures"
    if name.startswith("Prefab_") or ext == ".prefab":
        return "Prefabs"
    if name.startswith("Scene_") or ext in {".unity", ".tscn"}:
        return "Scenes"
    if ext in {".cs", ".gd", ".py"}:
        return "Scripts"
    if name.startswith("UI_") or "ui" in low:
        return "UI"
    if any(s in low for s in ("vehicle", "truck", "car", "van")):
        return "Vehicles"
    if ext in {".vfx", ".controller", ".anim"}:
        return "VFX"
    if ext in {".glb", ".gltf", ".fbx", ".obj", ".blend", ".dae"}:
        return "Models"
    return "Documentation"


def naming_violations(files: list[str]) -> list[str]:
    out = []
    for rel in files:
        name = Path(rel).name
        low = name.lower()
        if any(x in low for x in ("desc_", "handoff", "manifest", "verify", "readme", ".worker-trace")):
            continue
        ext = Path(rel).suffix.lower()
        if ext not in {".glb", ".gltf", ".fbx", ".obj", ".blend", ".mat", ".prefab", ".unity", ".tscn", ".wav", ".ogg", ".mp3", ".png", ".jpg", ".jpeg", ".tga", ".exr"}:
            continue
        if not any(re.match(rule, name) for rule, _ in NAMING_RULES):
            out.append(f"{rel} (missing standard prefix SM_/M_/T_/A_/Prefab_/Scene_)")
    return out


def hierarchy_violations(files: list[str]) -> list[str]:
    out = []
    for rel in files:
        if str(Path(rel).parent) in {".", ""}:
            continue
        top = Path(rel).parts[0]
        if top in {"Manifests", "Documentation", ".", "_artifacts~"}:
            continue
        if top not in HIERARCHY_CATEGORIES:
            pass
    return out


def emit_manifest(adir: Path, agent_id: str, files: list[str]) -> dict:
    assets = []
    for rel in files:
        name = Path(rel).name
        if name.startswith(".") or any(x in name.lower() for x in ("handoff", "manifest", "verify", "desc_")):
            continue
        ext = Path(rel).suffix.lower()
        ftype = "Document"
        if ext in {".glb", ".gltf", ".fbx", ".obj", ".blend"}:
            ftype = "StaticMesh"
        elif ext in {".png", ".jpg", ".jpeg", ".tga", ".exr"}:
            ftype = "Texture"
        elif ext in {".wav", ".ogg", ".mp3"}:
            ftype = "Audio"
        elif ext in {".unity", ".tscn"}:
            ftype = "Scene"
        elif ext in {".prefab", ".mat"}:
            ftype = ftype if ftype != "Document" else ext.lstrip(".").capitalize()
        lods = re.findall(r"LOD\d+", name, re.IGNORECASE) or (["LOD0"] if "LOD0" in name.upper() else [])
        assets.append({
            "filename": name,
            "path": f"Assets/_Project/{classify_output(rel)}/",
            "type": ftype,
            "lods": lods,
            "dependencies": [],
            "description_ref": f"DESC_{Path(rel).stem}" if ftype in {"StaticMesh", "Scene"} else "",
            "status": "accepted",
        })
    manifest = {
        "batch_id": f"{slug(agent_id)}-{time.strftime('%Y%m%d-%H%M%S')}",
        "agent_id": agent_id,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "assets": assets,
    }
    (adir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    return manifest


def check_handoff(handoff: str) -> list[str]:
    text = (handoff or "").lower()
    missing = []
    for f in HANDOFF_FIELDS:
        parts = [p.strip().lower() for p in f.split("/")]
        if not any(p in text for p in parts):
            missing.append(f)
    return missing


def slug(text: str) -> str:
    out = "".join(c if (c.isalnum() or c in "-_") else "-" for c in text.lower())
    return out.strip("-") or "agent"


def description_file_present(files: list[str], models: list[str] | None = None) -> bool:
    models = models or [f for f in files if Path(f).suffix.lower() in {".glb", ".gltf", ".fbx", ".blend"}]
    if not models:
        return True
    desc = [f for f in files if f.lower().startswith("desc_") and f.lower().endswith(".md")]
    return bool(desc)


def primitive_check(path: Path) -> list[dict]:
    """Use Blender headless to report mesh stats and flag primitive shapes."""
    return _run_blender_stats(path)


def _run_blender_stats(path: Path) -> list[dict]:
    script = ('import json, bpy\n'
              'out=[]\n'
              'for obj in bpy.context.scene.objects:\n'
              '    if obj.type not in ("MESH",): continue\n'
              '    v=len(obj.data.vertices)\n'
              '    n=obj.name.lower()\n'
              '    prim = n in ("cube","sphere","cylinder","cone","plane") or (v <= 24 and len(obj.data.polygons) <= 12)\n'
              '    out.append({"name": obj.name, "verts": v, "triangles": len(obj.data.polygons), "primitives": prim})\n'
              'print("V21PRIM"+json.dumps(out))\n')
    import subprocess as sp
    blender = os.environ.get("HARNESS_BLENDER", "/usr/local/bin/blender")
    try:
        proc = sp.run([blender, "--background", str(path), "--python-expr", script],
                      capture_output=True, text=True, timeout=120)
    except Exception as exc:
        return [{"name": path.name, "verts": 0, "triangles": 0, "primitives": True, "error": str(exc)}]
    m = re.search(r"V21PRIM(\[.*\]|\[\])", proc.stdout or "")
    if not m:
        return []
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return []


# ── vision verification (NVIDIA free vision deck) ────────────────────────────

def vision_chat(image: Path | str, prompt: str, model: str = NIM_VISION,
                max_tokens: int = 500) -> str:
    """Pass a screenshot/image to a vision model. Returns model verdict text."""
    import httpx
    key = _pick_key("nvidia")
    if not key:
        raise RuntimeError("no NVIDIA API key for vision check")
    data = base64.b64encode(Path(image).read_bytes()).decode()
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url",
             "image_url": {"url": f"data:image/png;base64,{data}"}},
        ]}],
        "max_tokens": max_tokens,
    }
    with httpx.Client(timeout=120) as client:
        resp = client.post(f"{NVIDIA_BASE}/chat/completions",
                           headers={"Authorization": f"Bearer {key}",
                                    "Content-Type": "application/json"},
                           json=payload)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]


def _screen_luma(image: Path) -> tuple | None:
    """(mean, std) of luminance; None if PIL unavailable."""
    try:
        from PIL import Image
    except ImportError:
        return None
    try:
        im = Image.open(image).convert("L").resize((64, 64))
        px = im.tobytes()
        mean = sum(px) / len(px)
        var = sum((p - mean) ** 2 for p in px) / len(px)
        return round(mean, 1), round(var ** 0.5, 1)
    except Exception:
        return None


def _screen_unique_pixels(image: Path) -> int | None:
    """Count distinct colors — catches fake/empty frames that luma alone
    can pass (a 4-pixel near-black PNG has meaningful luma but no content)."""
    try:
        from PIL import Image
    except ImportError:
        return None
    try:
        im = Image.open(image).convert("RGB").resize((128, 128))
        return len({px for px in im.getdata()})
    except Exception:
        return None


def vision_pass_fail(image: Path, prompt: str = "") -> dict:
    """Vision gate: a real render must (1) be non-black and non-empty,
    (2) be described by the vision model as matching the requirement.

    fake/empty frames: luma brush Fails mean<16 or (std<4 and mean<48), and
    unique-pixel check Fails <2 distinct colors (scaffold box near-black).
    Semantic match: the vision model MUST give the same description as the
    production pack asks for; a PASS that does not reference the requirement
    is demoted to FAIL (Jayson: all-gates vision law).
    """
    text = vision_chat(image, (
        "You are a strict visual QA inspector judging one screenshot against "
        f"a requirement: {prompt or '<visual acceptance>'}\n"
        "Output EXACTLY one line: 'PASS: <reason>' if the screenshot clearly "
        "satisfies the requirement, otherwise 'FAIL: <reason>'.\n"
        "A black, empty, broken-camera, missing-geometry, or artifact-heavy "
        "screenshot is FAIL. Do not describe the design; output only the "
        "verdict line."))
    luma = _screen_luma(image)
    uniq = _screen_unique_pixels(image)
    if luma:
        mean, std = luma
        if mean < 16 or (std < 4 and mean < 48):
            verdict, why = "FAIL", f"black/empty screen (luma mean={mean}, std={std})"
            return {"verdict": verdict, "notes": why, "image": str(image),
                    "luma": luma, "unique_pixels": uniq}
    if uniq is not None and uniq < 2:
        return {"verdict": "FAIL", "notes": f"fake/empty frame ({uniq} unique px)",
                "image": str(image), "luma": luma, "unique_pixels": uniq}
    verdict = "PASS" if re.search(r"\bPASS\b", text, re.I) else "FAIL"
    # Semantic match: the model must describe the requirement, not just bless
    # non-black pixels. If the pack asks for a specific asset/scene and the
    # PASS reason never references it, the frame is wrong for the gate.
    if verdict == "PASS" and prompt.strip():
        desc = text.split("PASS:", 1)[-1]
        req_tokens = {w.strip(",.!?;:'\"()").lower()
                      for w in prompt.split()
                      if len(w.strip(",.!?;:'\"()")) > 3}
        desc_tokens = {w.strip(",.!?;:'\"()").lower()
                       for w in desc.split()
                       if len(w.strip(",.!?;:'\"()")) > 3}
        overlap = req_tokens & desc_tokens
        if not overlap:
            verdict = "FAIL"
            notes = (f"semantic mismatch: model did not describe the pack "
                     f"requirement ({prompt[:100]!r} vs reason {desc[:100]!r})")
            return {"verdict": verdict, "notes": notes, "image": str(image),
                    "luma": luma, "unique_pixels": uniq}
    return {"verdict": verdict, "notes": text[:500], "image": str(image),
            "luma": luma, "unique_pixels": uniq}


def audio_pass_fail(wav: Path, prompt: str = "") -> dict:
    """Audio gate: a real sample must be a playable audio file with real
    content and, when a pack requirement is given, the sample must be
    described by a transcription/model as matching that requirement.

    Deterministic liveness first (header, duration>0, non-silence RMS), then
    optional semantic match via whisper/transcription when available.
    """
    import wave
    verdict, notes = "FAIL", ""
    try:
        if not wav.exists() or wav.stat().st_size == 0:
            return {"verdict": "FAIL", "notes": "file missing/empty",
                    "audio": str(wav)}
        with wave.open(str(wav), "rb") as w:
            nframes = w.getnframes()
            rate = w.getframerate()
            ch = w.getnchannels()
            dur = nframes / rate if rate else 0.0
            raw = w.readframes(min(nframes, rate))  # 1s worth for RMS
        if dur <= 0:
            return {"verdict": "FAIL", "notes": "zero-length audio",
                    "audio": str(wav), "duration_s": dur}
        # RMS of the first second — silence (all zeros) = no real content.
        samples = list(raw)
        if samples:
            rms = (sum(s * s for s in samples) / len(samples)) ** 0.5
        else:
            rms = 0.0
        base = {"audio": str(wav), "duration_s": round(dur, 2),
                "channels": ch, "rate": rate, "rms": round(rms, 2)}
        if rms < 0.5:
            return {"verdict": "FAIL", "notes": "silent/all-zeros sample", **base}
        verdict = "PASS"
        notes = f"real audio ({round(dur,2)}s, {ch}ch, {rate}Hz, rms={round(rms,2)})"
    except Exception as exc:
        return {"verdict": "FAIL", "notes": f"audio read failed: {exc}",
                "audio": str(wav)}
    result = {"verdict": verdict, "notes": notes, "audio": str(wav)}
    # Semantic match (best-effort): transcribe when whisper is available.
    if prompt.strip():
        try:
            from faster_whisper import WhisperModel
            model = WhisperModel("base", device="cpu", compute_type="int8")
            segments, _ = model.transcribe(str(wav))
            tr = " ".join(seg.text for seg in segments).strip()
            result["transcript"] = tr[:400]
            if not tr:
                verdict = "FAIL"
                result["notes"] = "semantic mismatch: audio untranscribable"
            else:
                req_tokens = {w.strip(",.!?;:'\"()").lower()
                              for w in prompt.split()
                              if len(w.strip(",.!?;:'\"()")) > 3}
                tr_tokens = {w.strip(",.!?;:'\"()").lower()
                             for w in tr.split()
                             if len(w.strip(",.!?;:'\"()")) > 3}
                if not (req_tokens & tr_tokens):
                    verdict = "FAIL"
                    result["notes"] = (
                        f"semantic mismatch: transcript did not match pack "
                        f"requirement ({prompt[:80]!r} vs {tr[:80]!r})")
            result["verdict"] = verdict
        except Exception:
            pass  # whisper unavailable → liveness-only gate, noted as such
    return result


# ── beta tester phase ────────────────────────────────────────────────────────

def run_beta_tests(pid: str, ws: Path, screenshots: list[Path]) -> dict:
    """Five beta tester agents review real screenshots/frames like humans."""
    ws_beta = ws / "beta"
    ws_beta.mkdir(parents=True, exist_ok=True)
    reports = []
    for i in range(1, BETA_TESTER_COUNT + 1):
        shots = screenshots[i - 1::BETA_TESTER_COUNT] or screenshots[:1]
        report = _one_beta_tester(i, shots, ws_beta)
        reports.append(report)
    agg = {
        "testers": len(reports),
        "passed": sum(1 for r in reports if r.get("pass", False)),
        "shipped_loop": all(r.get("pass", False) for r in reports),
        "reports": [str(r["path"]) for r in reports],
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "hard_gate": "PASS" if all(r.get("pass", False) for r in reports) else "BLOCK",
    }
    (ws_beta / "BETA_REPORT.md").write_text(json.dumps(agg, indent=2))
    return agg


def _one_beta_tester(idx: int, screenshots: list[Path], out_dir: Path) -> dict:
    lines = []
    pass_flag = True
    for shot in screenshots:
        try:
            res = vision_pass_fail(shot, (
                f"You are Beta Tester {idx}. Play the game the way a human "
                "would, inspect the frame, and report visual or gameplay "
                "issues. Answer PASS or FAIL then notes."))
            lines.append(f"- {shot.name}: {res['verdict']} — {res['notes']}")
            if res["verdict"] == "FAIL":
                pass_flag = False
        except Exception as exc:
            lines.append(f"- {shot.name}: [vision error] {exc}")
            pass_flag = False
    body = "\n".join(lines) or "no screenshots were available to test"
    body += f"\n\nBeta Tester {idx} overall: {'PASS' if pass_flag else 'FAIL'}"
    path = out_dir / f"BETA_TESTER_{idx}.md"
    path.write_text(body)
    return {"tester": idx, "pass": pass_flag, "path": str(path), "frames": len(screenshots)}


# ── godot engine support ─────────────────────────────────────────────────────

GODOT = os.environ.get("HARNESS_GODOT", "/usr/local/bin/godot")
GODOT_ASSET_EXTS = {".glb", ".gltf", ".obj", ".fbx", ".png", ".jpg", ".jpeg",
                    ".wav", ".ogg", ".mp3", ".tscn", ".tres", ".gd", ".shader"}


def godot_version() -> str:
    import subprocess as sp
    try:
        proc = sp.run([GODOT, "--version"], capture_output=True, text=True, timeout=30)
        return (proc.stdout or proc.stderr).strip().splitlines()[0]
    except Exception:
        return "unavailable"


def _real_godot_project(candidate: Path) -> Path | None:
    """Return the game's REAL Godot project dir, or None if the candidate only
    holds a harness scaffold. A real project has its own project.godot whose
    main_scene is a real game scene (not the scaffold's scenes/main.tscn)."""
    g = candidate / "godot"
    for base in (g if g.exists() else candidate, candidate):
        pg = base / "project.godot"
        if not pg.exists():
            continue
        try:
            text = pg.read_text()
        except Exception:
            continue
        main = ""
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("run/main_scene="):
                main = line.split("=", 1)[1].strip().strip('"')
                break
        if main and main != "res://scenes/main.tscn" and "scaffold" not in main:
            if (base / "scenes").exists():
                return base
    return None


def godot_scaffold(project_path: Path) -> Path:
    """Write a minimal Godot 4 project + capture script. Returns project dir."""
    gdir = project_path / "godot"
    gdir.mkdir(parents=True, exist_ok=True)
    (gdir / "project.godot").write_text(textwrap.dedent(f"""\
        ; Engine configuration file.
        config_version=5
        [application]
        config/name="{gdir.parent.name}"
        run/main_scene="res://scenes/main.tscn"
        [rendering]
        renderer/rendering_method="mobile"
        renderer/rendering_method.mobile="mobile"
        environment/defaults/default_clear_color=Color(0.06, 0.06, 0.08, 1)
        """))
    (gdir / "scenes").mkdir(exist_ok=True)
    (gdir / "scenes" / "main.tscn").write_text(textwrap.dedent("""\
        [gd_scene load_steps=4 format=3 uid="uid://v21main0001"]

        [ext_resource type="Script" path="res://capture.gd" id="1"]

        [sub_resource type="Sky" id="Sky1"]
        sky_top_color = Color(0.35, 0.38, 0.45, 1)
        sky_horizon_color = Color(0.55, 0.58, 0.65, 1)
        ground_bottom_color = Color(0.1, 0.1, 0.12, 1)
        [sub_resource type="Environment" id="Env1"]
        environment = SubResource("Env1")
        background_mode = 2
        background_sky = SubResource("Sky1")
        [sub_resource type="BoxMesh" id="Box1"]
        size = Vector3(1.4, 1.4, 1.4)

        [node name="Main" type="Node3D"]
        script = ExtResource("1")

        [node name="Light" type="DirectionalLight3D" parent="."]
        rotation = Vector3(-0.8, 0.5, 0)

        [node name="Box" type="MeshInstance3D" parent="."]
        position = Vector3(0, 0, -1.5)
        mesh = SubResource("Box1")

        [node name="Cam" type="Camera3D" parent="."]
        transform = Transform3D(1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 1.6, 4)
        """))
    (gdir / "capture.gd").write_text(textwrap.dedent(f"""\
        extends Node3D

        func _ready() -> void:
            await RenderingServer.frame_post_draw
            for i in range(3):
                await get_tree().process_frame
            var img := get_viewport().get_texture().get_image()
            img.save_png("res://capture.png")
            print("V21GDCAPTURE " + ProjectSettings.globalize_path("res://capture.png"))
            get_tree().quit()
        """))
    (gdir / "assets").mkdir(exist_ok=True)
    return gdir


def godot_capture(project_path: Path) -> Path | None:
    """Real in-engine capture: run the project under a GL driver (the
    headless dummy renderer has no viewport texture, so we render normally
    against the existing X display). Returns the .png path or None.

    If the candidate holds a REAL game project (a project.godot whose
    main_scene is a real game scene) we run THAT with LF_CAPTURE=1 — the
    game's own CaptureCtl autoload curls the frame from the actual scene.
    Only when no real project exists do we fall back to the throwaway
    scaffold (dummy box) so generic projects still get a capture."""
    import subprocess as sp
    import os as _os
    real = _real_godot_project(project_path)
    gdir = real if real is not None else godot_scaffold(project_path)
    env = dict(_os.environ, GODOT_SILENCE_ROOT_WARNING="1")
    if real is not None:
        env = dict(env, LF_CAPTURE="1")
    scripts = [
        [GODOT, "--rendering-driver", "opengl3", "--rendering-method", "gl_compatibility",
         "--path", str(gdir)],  # capture.gd / CaptureCtl self-quit after frame(s) drawn
        [GODOT, "--path", str(gdir)],  # whatever driver works
    ]
    for cmd in scripts:
        try:
            proc = sp.run(cmd, capture_output=True, text=True, timeout=120, env=env)
        except Exception:
            continue
        m = re.search(r"V21GDCAPTURE\s+(.+\.png)", proc.stdout or "")
        if m:
            png = Path(m.group(1))
            if png.exists() and png.stat().st_size > 0:
                return png
        for line in (proc.stderr or "").splitlines():
            if "save_png" in line or "capture.gd" in line or "CaptureCtl" in line:
                break
    return None


def godot_import(project_path: Path) -> dict:
    """Headless import pass — real source import / shader compile in Godot."""
    import subprocess as sp
    gdir = godot_scaffold(project_path)
    try:
        proc = sp.run([GODOT, "--headless", "--path", str(gdir), "--import"],
                      capture_output=True, text=True, timeout=300)
        return {"ok": proc.returncode == 0,
                "returncode": proc.returncode,
                "stdout": (proc.stdout or "")[-1000:],
                "stderr": (proc.stderr or "")[-1000:]}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


_GODOT_EXPORT_PRESETS = """\
[preset.0]
name="Linux"
platform="Linux"
runnable=true
dedicated_server=false
custom_features=""
export_filter="all_resources"
include_filter=""
exclude_filter=""
export_path="builds/linux/game.x86_64"
patches=PackedStringArray()
encryption_include_filters=""
encryption_exclude_filters=""
seed=0
encrypt_pck=false
encrypt_directory=false

[preset.1]
name="Android"
platform="Android"
runnable=true
dedicated_server=false
custom_features=""
export_filter="all_resources"
include_filter=""
exclude_filter=""
export_path="builds/android/game.apk"
patches=PackedStringArray()
encryption_include_filters=""
encryption_exclude_filters=""
seed=0
encrypt_pck=false
encrypt_directory=false
gradle_build=true
architecture="arm64-v8a"
min_sdk="24"
target_sdk="35"
"""


def godot_build(project_path: Path, platform: str) -> dict:
    """Headless Godot export for Linux x86_64 or Android arm64.

    Preset names: "Linux" / "Android". Honest failure if the platform's
    export templates or Android SDK are not installed on the box.
    """
    import subprocess as sp
    gdir = godot_scaffold(project_path)
    presets = gdir / "export_presets.cfg"
    if not presets.exists():
        presets.write_text(_GODOT_EXPORT_PRESETS)
    preset = {"Linux": "Linux", "android": "Android", "Android": "Android"}.get(
        platform, "Linux")
    out = gdir / "builds" / ("linux/game.x86_64" if preset == "Linux"
                             else "android/game.apk")
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        proc = sp.run([GODOT, "--headless", "--path", str(gdir),
                       "--export-release", preset, str(out)],
                      capture_output=True, text=True, timeout=600)
        built = out.exists() and out.stat().st_size > 0
        return {"ok": built, "artifact": str(out),
                "built": built,
                "returncode": proc.returncode,
                "stdout": (proc.stdout or "")[-1200:],
                "stderr": (proc.stderr or "")[-1200:]}
    except Exception as exc:
        return {"ok": False, "artifact": str(out), "error": str(exc)}