"""Shared scan policy: what counts as source, and what never ships."""

from __future__ import annotations

import fnmatch
from pathlib import Path

SCHEMA = "mem20-sitemap-v1"

SOURCE_DIR_GLOBS = (
    ".git",
    ".hg",
    ".svn",
    "__pycache__",
    "node_modules",
    ".venv",
    "venv",
    ".env.d",
    "dist",
    "build",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".eggs",
    "*.egg-info",
    ".idea",
    ".vscode",
    "secrets",
    "backups",
    "incoming",
    "proof",
    ".sitemap",
    ".cache",
    "site-packages",
)

BINARY_DIR_GLOBS = (
    "models",
    "checkpoints",
    "blobs",
    "chrome-profile",
)

SOURCE_SUFFIXES = (
    ".py",
    ".pyi",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".mjs",
    ".cjs",
    ".json",
    ".jsonl",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".cfg",
    ".md",
    ".txt",
    ".sh",
    ".bash",
    ".sql",
    ".html",
    ".css",
    ".scss",
    ".xml",
    ".svg",
    ".proto",
    ".tf",
    ".dockerfile",
    ".makefile",
    ".cmake",
    ".rs",
    ".go",
    ".c",
    ".h",
    ".cpp",
    ".hpp",
    ".cs",
    ".lua",
    ".gd",
    ".glsl",
    ".vert",
    ".frag",
    ".asm",
    ".s",
    ".zig",
    ".ex",
    ".exs",
    ".erl",
    ".clj",
    ".rb",
    ".pl",
    ".php",
    ".swift",
    ".kt",
    ".kts",
    ".scala",
    ".dart",
    ".vue",
    ".svelte",
)

SKIP_SUFFIXES = (
    ".pyc",
    ".pyo",
    ".pyd",
    ".so",
    ".dylib",
    ".dll",
    ".a",
    ".o",
    ".class",
    ".jar",
    ".war",
    ".db",
    ".db-wal",
    ".db-shm",
    ".sqlite",
    ".sqlite3",
    ".faiss",
    ".pkl",
    ".pickle",
    ".npy",
    ".npz",
    ".onnx",
    ".pt",
    ".pth",
    ".bin",
    ".safetensors",
    ".gguf",
    ".ckpt",
    ".msgpack",
    ".pack",
    ".idx",
    ".log",
    ".swp",
    ".zip",
    ".tar",
    ".gz",
    ".bz2",
    ".xz",
    ".7z",
    ".rar",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".bmp",
    ".tiff",
    ".ico",
    ".mp3",
    ".wav",
    ".flac",
    ".ogg",
    ".mp4",
    ".mov",
    ".avi",
    ".mkv",
    ".webm",
    ".blend",
    ".fbx",
    ".obj",
    ".glb",
    ".gltf",
    ".unity",
    ".prefab",
    ".ttf",
    ".otf",
    ".woff",
    ".woff2",
    ".eot",
)

DOC_NAMES = ("README.md", "AGENTS.md", "CONFWORK.md", "PROPOSAL.md", "NOTES.md", "TODO.md")

UNPREFIXED_SERVICES = (
    "braid",
    "cog",
    "memory_engine",
    "chroma",
    "kanban",
    "mcp",
    "gateway",
    "dashboard",
    "toolchest",
    "reference_store",
    "store",
    "tools",
    "loaders",
    "notes",
    "packaging",
    "roadmaps",
    "verification",
    "entries",
    "mem20_mcp",
    "mem20-orchestration",
)


def is_skipped_dir(name: str, extra: tuple[str, ...] = ()) -> bool:
    patterns = SOURCE_DIR_GLOBS + extra
    return any(fnmatch.fnmatch(name, pat) for pat in patterns)


def is_skipped_file(path: Path, extra_suffixes: tuple[str, ...] = ()) -> bool:
    name = path.name
    suffix = path.suffix.lower()
    if suffix in SKIP_SUFFIXES or suffix in extra_suffixes:
        return True
    for pat in SOURCE_DIR_GLOBS + BINARY_DIR_GLOBS:
        if name == pat:
            return True
    return False


def is_source_file(path: Path) -> bool:
    suffix = path.suffix.lower()
    if suffix in SKIP_SUFFIXES:
        return False
    if suffix in SOURCE_SUFFIXES:
        return True
    return path.name in ("Makefile", "Dockerfile", "LICENSE", "Jenkinsfile", "Procfile")


def language_of(path: Path) -> str:
    suffix = path.suffix.lower()
    table = {
        ".py": "python",
        ".pyi": "python",
        ".ts": "typescript",
        ".tsx": "typescript",
        ".js": "javascript",
        ".jsx": "javascript",
        ".mjs": "javascript",
        ".cjs": "javascript",
        ".rs": "rust",
        ".go": "go",
        ".c": "c",
        ".h": "c",
        ".cpp": "cpp",
        ".hpp": "cpp",
        ".cs": "csharp",
        ".lua": "lua",
        ".gd": "gdscript",
        ".sh": "shell",
        ".bash": "shell",
        ".sql": "sql",
        ".md": "markdown",
        ".json": "json",
        ".jsonl": "jsonl",
        ".yaml": "yaml",
        ".yml": "yaml",
        ".toml": "toml",
        ".html": "html",
        ".css": "css",
        ".scss": "scss",
        ".xml": "xml",
        ".svg": "svg",
        ".tf": "terraform",
        ".zig": "zig",
        ".ex": "elixir",
        ".exs": "elixir",
        ".erl": "erlang",
        ".rb": "ruby",
        ".pl": "perl",
        ".php": "php",
        ".swift": "swift",
        ".kt": "kotlin",
        ".kts": "kotlin",
        ".scala": "scala",
        ".dart": "dart",
        ".vue": "vue",
        ".svelte": "svelte",
        ".glsl": "glsl",
        ".proto": "protobuf",
    }
    if suffix in table:
        return table[suffix]
    if path.name in ("Makefile", "Dockerfile"):
        return "make"
    return "other"
