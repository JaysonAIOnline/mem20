"""Filesystem Tools Mixin for mem20 MCP Server.

Provides advanced filesystem tools:
- File read/write with encoding detection
- Directory operations
- File search with glob/regex
- File metadata
- Symlink operations
- File comparison (diff)
- Archive operations (zip, tar)
- File watching
- Permission management
- Disk usage analysis
"""

import hashlib
import json
import os
import shutil
import tempfile
import zipfile
import tarfile

from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from mcp.server import Server
    from mcp.server.lowlevel.server import ServerRequestContext
    import mcp_types as mt
except ImportError:
    print("Error: mcp package not installed. Please install with: pip install mcp")
    raise


class FilesystemToolsMixin:
    """Advanced filesystem tools for mem20."""

    def register_filesystem_tools(self):
        """Register all filesystem tools."""
        self.tools["fs_read_advanced"] = mt.Tool(
            name="fs_read_advanced",
            title="Read File (Advanced)",
            description="Read file with encoding detection and line numbers",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path"},
                    "offset": {"type": "integer", "default": 1},
                    "limit": {"type": "integer", "default": 2000},
                    "encoding": {"type": "string", "description": "Force encoding", "default": ""},
                },
                "required": ["path"],
            },
        )
        self.tools["fs_write_advanced"] = mt.Tool(
            name="fs_write_advanced",
            title="Write File (Advanced)",
            description="Write file with encoding and atomic write support",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path"},
                    "content": {"type": "string", "description": "Content to write"},
                    "encoding": {"type": "string", "default": "utf-8"},
                    "append": {"type": "boolean", "default": False},
                    "atomic": {"type": "boolean", "default": True},
                },
                "required": ["path", "content"],
            },
        )
        self.tools["fs_search"] = mt.Tool(
            name="fs_search",
            title="Search Files",
            description="Search files by name pattern or content",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "default": "."},
                    "name_pattern": {"type": "string", "default": ""},
                    "content_pattern": {"type": "string", "default": ""},
                    "file_type": {"type": "string", "default": ""},
                    "max_results": {"type": "integer", "default": 50},
                },
                "required": ["path"],
            },
        )
        self.tools["fs_metadata"] = mt.Tool(
            name="fs_metadata",
            title="File Metadata",
            description="Get file metadata (size, modified, permissions, hash)",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "compute_hash": {"type": "boolean", "default": False},
                },
                "required": ["path"],
            },
        )
        self.tools["fs_diff"] = mt.Tool(
            name="fs_diff",
            title="File Diff",
            description="Compare two files and show differences",
            inputSchema={
                "type": "object",
                "properties": {
                    "file1": {"type": "string"},
                    "file2": {"type": "string"},
                    "context_lines": {"type": "integer", "default": 3},
                },
                "required": ["file1", "file2"],
            },
        )
        self.tools["fs_archive_create"] = mt.Tool(
            name="fs_archive_create",
            title="Create Archive",
            description="Create a zip or tar archive",
            inputSchema={
                "type": "object",
                "properties": {
                    "output_path": {"type": "string"},
                    "files": {"type": "string", "description": "JSON array of file paths"},
                    "format": {"type": "string", "enum": ["zip", "tar", "tar.gz"], "default": "zip"},
                },
                "required": ["output_path", "files"],
            },
        )
        self.tools["fs_archive_extract"] = mt.Tool(
            name="fs_archive_extract",
            title="Extract Archive",
            description="Extract a zip or tar archive",
            inputSchema={
                "type": "object",
                "properties": {
                    "archive_path": {"type": "string"},
                    "output_dir": {"type": "string"},
                    "format": {"type": "string", "enum": ["zip", "tar", "tar.gz"], "default": "zip"},
                },
                "required": ["archive_path", "output_dir"],
            },
        )
        self.tools["fs_disk_usage"] = mt.Tool(
            name="fs_disk_usage",
            title="Disk Usage",
            description="Analyze disk usage for a directory",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "default": "."},
                    "max_depth": {"type": "integer", "default": 2},
                    "limit": {"type": "integer", "default": 20},
                },
                "required": [],
            },
        )
        self.tools["fs_watch"] = mt.Tool(
            name="fs_watch",
            title="Watch Directory",
            description="Watch a directory for changes",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "duration_seconds": {"type": "integer", "default": 10},
                    "recursive": {"type": "boolean", "default": True},
                },
                "required": ["path"],
            },
        )
        self.tools["fs_permissions"] = mt.Tool(
            name="fs_permissions",
            title="Manage Permissions",
            description="Get or set file permissions",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "mode": {"type": "string", "description": "Octal mode (e.g., 755)", "default": ""},
                    "owner": {"type": "string", "default": ""},
                    "group": {"type": "string", "default": ""},
                },
                "required": ["path"],
            },
        )

    async def _fs_read_advanced(self, args: Dict) -> str:
        path = args.get("path", "")
        offset = args.get("offset", 1)
        limit = args.get("limit", 2000)
        encoding = args.get("encoding", "")
        try:
            file_path = Path(path)
            if not file_path.exists():
                return f"Error: File '{path}' not found"
            raw = file_path.read_bytes()
            if encoding:
                text = raw.decode(encoding)
            else:
                import chardet
                detected = chardet.detect(raw)
                text = raw.decode(detected.get("encoding", "utf-8"))
            lines = text.splitlines()
            start = max(0, offset - 1)
            end = min(len(lines), start + limit)
            selected = lines[start:end]
            result = "\n".join(f"{i+offset}|{line}" for i, line in enumerate(selected))
            result += f"\n\n[Total lines: {len(lines)}, showing {offset}-{end}]"
            return result
        except ImportError:
            return "Error: chardet not installed. Run: pip install chardet"
        except Exception as e:
            return f"Error: {str(e)}"

    async def _fs_write_advanced(self, args: Dict) -> str:
        path = args.get("path", "")
        content = args.get("content", "")
        encoding = args.get("encoding", "utf-8")
        append = args.get("append", False)
        atomic = args.get("atomic", True)
        try:
            file_path = Path(path)
            file_path.parent.mkdir(parents=True, exist_ok=True)
            if atomic:
                # Write to temp file then rename
                with tempfile.NamedTemporaryFile(
                    mode="w", encoding=encoding, delete=False,
                    dir=file_path.parent, suffix=".tmp"
                ) as f:
                    if append and file_path.exists():
                        f.write(file_path.read_text(encoding=encoding))
                    f.write(content)
                    temp_path = f.name
                shutil.move(temp_path, str(file_path))
            else:
                mode = "a" if append else "w"
                with open(file_path, mode, encoding=encoding) as f:
                    f.write(content)
            return f"Wrote {len(content)} chars to {path}"
        except Exception as e:
            return f"Error: {str(e)}"

    async def _fs_search(self, args: Dict) -> str:
        path = args.get("path", ".")
        name_pattern = args.get("name_pattern", "")
        content_pattern = args.get("content_pattern", "")
        file_type = args.get("file_type", "")
        max_results = args.get("max_results", 50)
        try:
            import fnmatch
            import re
            results = []
            for root, dirs, files in os.walk(path):
                for f in files:
                    filepath = os.path.join(root, f)
                    if file_type and not f.endswith(f".{file_type}"):
                        continue
                    if name_pattern and not fnmatch.fnmatch(f, name_pattern):
                        continue
                    if content_pattern:
                        try:
                            with open(filepath, "r", errors="ignore") as fh:
                                content = fh.read()
                            if not re.search(content_pattern, content):
                                continue
                        except:
                            continue
                    results.append(filepath)
                    if len(results) >= max_results:
                        break
                if len(results) >= max_results:
                    break
            if results:
                return f"Found {len(results)} files:\n" + "\n".join(results)
            return "No files found."
        except Exception as e:
            return f"Error: {str(e)}"

    async def _fs_metadata(self, args: Dict) -> str:
        path = args.get("path", "")
        compute_hash = args.get("compute_hash", False)
        try:
            file_path = Path(path)
            if not file_path.exists():
                return f"Error: '{path}' not found"
            stat = file_path.stat()
            result = f"File: {path}\n"
            result += f"Size: {stat.st_size} bytes\n"
            result += f"Modified: {stat.st_mtime}\n"
            result += f"Created: {stat.st_ctime}\n"
            result += f"Permissions: {oct(stat.st_mode)}\n"
            result += f"Owner UID: {stat.st_uid}\n"
            result += f"Group GID: {stat.st_gid}\n"
            if compute_hash:
                with open(file_path, "rb") as f:
                    content = f.read()
                result += f"MD5: {hashlib.md5(content).hexdigest()}\n"
                result += f"SHA256: {hashlib.sha256(content).hexdigest()}\n"
            return result
        except Exception as e:
            return f"Error: {str(e)}"

    async def _fs_diff(self, args: Dict) -> str:
        file1 = args.get("file1", "")
        file2 = args.get("file2", "")
        context_lines = args.get("context_lines", 3)
        try:
            import difflib
            with open(file1) as f:
                lines1 = f.readlines()
            with open(file2) as f:
                lines2 = f.readlines()
            diff = difflib.unified_diff(
                lines1, lines2,
                fromfile=file1, tofile=file2,
                n=context_lines
            )
            return "".join(diff)
        except Exception as e:
            return f"Error: {str(e)}"

    async def _fs_archive_create(self, args: Dict) -> str:
        output_path = args.get("output_path", "")
        files = json.loads(args.get("files", "[]"))
        fmt = args.get("format", "zip")
        try:
            if fmt == "zip":
                with zipfile.ZipFile(output_path, "w") as zf:
                    for f in files:
                        zf.write(f, os.path.basename(f))
            elif fmt in ["tar", "tar.gz"]:
                mode = "w:gz" if fmt == "tar.gz" else "w"
                with tarfile.open(output_path, mode) as tf:
                    for f in files:
                        tf.add(f, os.path.basename(f))
            return f"Archive created: {output_path} ({len(files)} files)"
        except Exception as e:
            return f"Error: {str(e)}"

    async def _fs_archive_extract(self, args: Dict) -> str:
        archive_path = args.get("archive_path", "")
        output_dir = args.get("output_dir", "")
        fmt = args.get("format", "zip")
        try:
            os.makedirs(output_dir, exist_ok=True)
            if fmt == "zip":
                with zipfile.ZipFile(archive_path, "r") as zf:
                    zf.extractall(output_dir)
            elif fmt in ["tar", "tar.gz"]:
                mode = "r:gz" if fmt == "tar.gz" else "r"
                with tarfile.open(archive_path, mode) as tf:
                    tf.extractall(output_dir)
            return f"Extracted to: {output_dir}"
        except Exception as e:
            return f"Error: {str(e)}"

    async def _fs_disk_usage(self, args: Dict) -> str:
        path = args.get("path", ".")
        max_depth = args.get("max_depth", 2)
        limit = args.get("limit", 20)
        try:
            sizes = {}
            for root, dirs, files in os.walk(path):
                depth = root.replace(path, "").count(os.sep)
                if depth > max_depth:
                    continue
                total = 0
                for f in files:
                    fp = os.path.join(root, f)
                    try:
                        total += os.path.getsize(fp)
                    except:
                        pass
                sizes[root] = total
            sorted_sizes = sorted(sizes.items(), key=lambda x: x[1], reverse=True)
            output = f"Disk Usage (top {limit}):\n"
            for p, size in sorted_sizes[:limit]:
                if size > 1024 * 1024:
                    output += f"  {p}: {size / (1024*1024):.1f} MB\n"
                elif size > 1024:
                    output += f"  {p}: {size / 1024:.1f} KB\n"
                else:
                    output += f"  {p}: {size} bytes\n"
            return output
        except Exception as e:
            return f"Error: {str(e)}"

    async def _fs_watch(self, args: Dict) -> str:
        path = args.get("path", "")
        duration = args.get("duration_seconds", 10)
        recursive = args.get("recursive", True)
        try:
            import time
            from watchdog.observers import Observer
            from watchdog.events import FileSystemEventHandler
            changes = []

            class Handler(FileSystemEventHandler):
                def on_modified(self, event):
                    changes.append(f"Modified: {event.src_path}")

                def on_created(self, event):
                    changes.append(f"Created: {event.src_path}")

                def on_deleted(self, event):
                    changes.append(f"Deleted: {event.src_path}")

            observer = Observer()
            observer.schedule(Handler(), path, recursive=recursive)
            observer.start()
            time.sleep(duration)
            observer.stop()
            observer.join()
            if changes:
                return f"Changes in {path} ({len(changes)}):\n" + "\n".join(changes[:50])
            return f"No changes detected in {path} during {duration}s"
        except ImportError:
            return "Error: watchdog not installed. Run: pip install watchdog"
        except Exception as e:
            return f"Error: {str(e)}"

    async def _fs_permissions(self, args: Dict) -> str:
        path = args.get("path", "")
        mode = args.get("mode", "")
        owner = args.get("owner", "")
        group = args.get("group", "")
        try:
            if mode:
                os.chmod(path, int(mode, 8))
            if owner or group:
                import pwd
                import grp
                uid = pwd.getpwnam(owner).pw_uid if owner else -1
                gid = grp.getgrnam(group).gr_gid if group else -1
                os.chown(path, uid, gid)
            stat = os.stat(path)
            return f"Permissions for {path}: {oct(stat.st_mode)}"
        except Exception as e:
            return f"Error: {str(e)}"