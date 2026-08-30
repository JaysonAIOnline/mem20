"""OPTIONAL Unity integration (shipped as a separate, pluggable module).

Unity is NOT a required dependency. The build/test tools degrade gracefully: when
Unity is not installed (or MEM20_UNITY_EXECUTABLE is unset / the default path is
absent), they return an informative message instead of failing.
"""
import os
import sys
import json
import re
import asyncio
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from mcp.server import Server
    from mcp.server.lowlevel.server import ServerRequestContext
    import mcp_types as mt
except ImportError:
    print("Error: mcp package not installed. Please install with: pip install mcp")
    sys.exit(1)

sys.path.insert(0, os.environ.get("MEM20_STORE_PATH", os.path.expanduser("~/.mem20/store")))
try:
    from memory import remember, recall, status as mem_status, rebuild_index, ledger_view
    MEMORY_SYSTEM_AVAILABLE = True
except ImportError:
    MEMORY_SYSTEM_AVAILABLE = False


class UnityToolsMixin:
    """Unity tools. Optional — requires the Unity Editor installed and on PATH, or MEM20_UNITY_EXECUTABLE."""

    def _resolve_optional_executable(self, name: str, provided: Optional[str], env_var: str, display: str):
        import shutil
        exe = provided or os.environ.get(env_var)
        if not exe:
            exe = shutil.which(display) or None
        if not exe or (not os.path.exists(exe) and shutil.which(os.path.basename(exe)) is None):
            return None, (
                f"{display} is an OPTIONAL integration and is not installed. Install {display} and ensure it is "
                f"on PATH, or pass '{name}_executable' / set {env_var} to its path, to use these tools."
            )
        return exe, None

    def register_unity_tools(self):
        self.tools["unity_create_script"] = mt.Tool(
            name="unity_create_script",
            title="Unity Create Script",
            description="Create a C# MonoBehaviour script in a Unity project. OPTIONAL integration: Unity must be installed.",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_path": {"type": "string", "description": "Path to Unity project"},
                    "script_name": {"type": "string", "description": "Script class name (e.g., PlayerController)"},
                    "namespace": {"type": "string", "description": "Namespace", "default": ""},
                    "base_class": {"type": "string", "description": "Base class", "default": "MonoBehaviour"},
                    "fields": {"type": "array", "items": {"type": "object", "properties": {"name": {"type": "string"}, "type": {"type": "string"}, "default_value": {"type": "string"}, "serialize_field": {"type": "boolean", "default": True}, "range_min": {"type": "number"}, "range_max": {"type": "number"}}}, "description": "Fields to add", "default": []},
                    "methods": {"type": "array", "items": {"type": "string"}, "description": "Lifecycle methods to include", "default": ["Awake", "Start", "Update"]},
                },
                "required": ["project_path", "script_name"],
            },
        )
        self.tools["unity_build_project"] = mt.Tool(
            name="unity_build_project",
            title="Unity Build Project",
            description="Build a Unity project for specified platform. OPTIONAL integration: Unity must be installed.",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_path": {"type": "string", "description": "Path to Unity project"},
                    "build_path": {"type": "string", "description": "Output build path"},
                    "platform": {"type": "string", "description": "Target platform", "enum": ["StandaloneWindows64", "StandaloneLinux64", "StandaloneOSX", "WebGL", "Android", "iOS"], "default": "StandaloneLinux64"},
                    "unity_executable": {"type": "string", "description": "Path to Unity executable (or set MEM20_UNITY_EXECUTABLE)", "default": ""},
                },
                "required": ["project_path", "build_path"],
            },
        )
        self.tools["unity_run_test"] = mt.Tool(
            name="unity_run_test",
            title="Unity Run Tests",
            description="Run Unity PlayMode or EditMode tests. OPTIONAL integration: Unity must be installed.",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_path": {"type": "string", "description": "Path to Unity project"},
                    "test_mode": {"type": "string", "description": "Test mode", "enum": ["PlayMode", "EditMode", "Both"], "default": "PlayMode"},
                    "unity_executable": {"type": "string", "description": "Path to Unity executable (or set MEM20_UNITY_EXECUTABLE)", "default": ""},
                },
                "required": ["project_path"],
            },
        )
        self.tools["unity_generate_asmdef"] = mt.Tool(
            name="unity_generate_asmdef",
            title="Unity Generate Assembly Definition",
            description="Generate an Assembly Definition (.asmdef) file. (Writes local files; does not require the Unity executable.)",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_path": {"type": "string", "description": "Path to Unity project"},
                    "asmdef_path": {"type": "string", "description": "Relative path for .asmdef file (e.g., Scripts/MyAssembly.asmdef)"},
                    "assembly_name": {"type": "string", "description": "Assembly name"},
                    "references": {"type": "array", "items": {"type": "string"}, "description": "Assembly references", "default": []},
                    "include_platforms": {"type": "array", "items": {"type": "string"}, "description": "Include platforms", "default": []},
                    "exclude_platforms": {"type": "array", "items": {"type": "string"}, "description": "Exclude platforms", "default": []},
                },
                "required": ["project_path", "asmdef_path", "assembly_name"],
            },
        )
        self.tools["unity_validate_project"] = mt.Tool(
            name="unity_validate_project",
            title="Unity Validate Project",
            description="Validate Unity project structure and check for common issues. (Reads local files; does not require the Unity executable.)",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_path": {"type": "string", "description": "Path to Unity project"},
                },
                "required": ["project_path"],
            },
        )

    async def _unity_create_script(self, args: Dict) -> str:
        project_path = args.get("project_path", "")
        script_name = args.get("script_name", "")
        namespace = args.get("namespace", "")
        base_class = args.get("base_class", "MonoBehaviour")
        fields = args.get("fields", [])
        methods = args.get("methods", ["Awake", "Start", "Update"])
        if not project_path or not script_name:
            return "Error: project_path and script_name are required"
        scripts_dir = f"{project_path}/Assets/Scripts"
        os.makedirs(scripts_dir, exist_ok=True)
        script_path = f"{scripts_dir}/{script_name}.cs"
        field_code = ""
        for field in fields:
            fname = field.get("name", "")
            ftype = field.get("type", "float")
            default = field.get("default_value", "")
            serialize = field.get("serialize_field", True)
            range_min = field.get("range_min")
            range_max = field.get("range_max")
            attrs = []
            if serialize:
                attrs.append("[SerializeField]")
            if range_min is not None and range_max is not None:
                attrs.append(f"[Range({range_min}, {range_max})]")
            attr_str = " ".join(attrs)
            default_str = f" = {default}" if default else ""
            field_code += f"    {attr_str} private {ftype} {fname}{default_str};\n"
        method_code = ""
        for method in methods:
            if method == "Awake":
                method_code += """
    private void Awake()
    {
        // Cache component references here
    }
"""
            elif method == "OnEnable":
                method_code += """
    private void OnEnable()
    {
        // Subscribe to events here
    }
"""
            elif method == "Start":
                method_code += """
    private void Start()
    {
        // Initialize after all Awake calls
    }
"""
            elif method == "Update":
                method_code += """
    private void Update()
    {
        // Per-frame logic (input, non-physics)
    }
"""
            elif method == "FixedUpdate":
                method_code += """
    private void FixedUpdate()
    {
        // Physics logic here
    }
"""
            elif method == "LateUpdate":
                method_code += """
    private void LateUpdate()
    {
        // Camera follow, post-physics updates
    }
"""
            elif method == "OnDisable":
                method_code += """
    private void OnDisable()
    {
        // Unsubscribe from events
    }
"""
            elif method == "OnDestroy":
                method_code += """
    private void OnDestroy()
    {
        // Cleanup
    }
"""
        namespace_block = f"namespace {namespace}\n" + "{" if namespace else ""
        script_content = f"""using UnityEngine;

{namespace_block}
public class {script_name} : {base_class}
{{
{field_code}
{method_code}
}}
"""
        if namespace:
            script_content = script_content.replace("\n}", "\n}\n}")
        try:
            Path(script_path).write_text(script_content)
            return f"Created script at {script_path}"
        except Exception as e:
            return f"Error creating script: {str(e)}"

    async def _unity_build_project(self, args: Dict) -> str:
        project_path = args.get("project_path", "")
        build_path = args.get("build_path", "")
        platform = args.get("platform", "StandaloneLinux64")
        unity_executable = args.get("unity_executable", "")
        if not project_path or not build_path:
            return "Error: project_path and build_path are required"
        unity_executable, err = self._resolve_optional_executable("unity", unity_executable, "MEM20_UNITY_EXECUTABLE", "Unity")
        if err:
            return err
        platform_map = {
            "StandaloneWindows64": "StandaloneWindows64",
            "StandaloneLinux64": "StandaloneLinux64",
            "StandaloneOSX": "StandaloneOSX",
            "WebGL": "WebGL",
            "Android": "Android",
            "iOS": "iOS",
        }
        target_platform = platform_map.get(platform, "StandaloneLinux64")
        if platform == "StandaloneWindows64":
            build_target = "-buildWindows64Player"
            build_file = f"{build_path}/{Path(project_path).name}.exe"
        elif platform == "StandaloneLinux64":
            build_target = "-buildLinux64Player"
            build_file = f"{build_path}/{Path(project_path).name}"
        elif platform == "StandaloneOSX":
            build_target = "-buildOSXUniversalPlayer"
            build_file = f"{build_path}/{Path(project_path).name}.app"
        elif platform == "WebGL":
            build_target = "-buildWebGLPlayer"
            build_file = build_path
        else:
            build_target = "-buildLinux64Player"
            build_file = f"{build_path}/{Path(project_path).name}"
        cmd = [
            unity_executable,
            "-batchmode",
            "-quit",
            "-projectPath", project_path,
            build_target, build_file,
            "-logFile", "-"
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            if result.returncode == 0:
                return f"Build successful!\nOutput: {build_file}\n{result.stdout[-2000:]}"
            else:
                return f"Build failed (code {result.returncode}):\n{result.stderr[-3000:]}"
        except subprocess.TimeoutExpired:
            return "Error: Build timed out after 10 minutes"
        except Exception as e:
            return f"Error: {str(e)}"

    async def _unity_run_test(self, args: Dict) -> str:
        project_path = args.get("project_path", "")
        test_mode = args.get("test_mode", "PlayMode")
        unity_executable = args.get("unity_executable", "")
        if not project_path:
            return "Error: project_path is required"
        unity_executable, err = self._resolve_optional_executable("unity", unity_executable, "MEM20_UNITY_EXECUTABLE", "Unity")
        if err:
            return err
        cmd = [
            unity_executable,
            "-batchmode",
            "-quit",
            "-projectPath", project_path,
            "-runTests",
            "-testPlatform", test_mode,
            "-logFile", "-"
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            return f"Tests {'passed' if result.returncode == 0 else 'failed'} (code {result.returncode}):\n{result.stdout[-3000:]}\n{result.stderr[-2000:]}"
        except subprocess.TimeoutExpired:
            return "Error: Tests timed out after 5 minutes"
        except Exception as e:
            return f"Error: {str(e)}"

    async def _unity_generate_asmdef(self, args: Dict) -> str:
        project_path = args.get("project_path", "")
        asmdef_path = args.get("asmdef_path", "")
        assembly_name = args.get("assembly_name", "")
        references = args.get("references", [])
        include_platforms = args.get("include_platforms", [])
        exclude_platforms = args.get("exclude_platforms", [])
        if not project_path or not asmdef_path or not assembly_name:
            return "Error: project_path, asmdef_path, and assembly_name are required"
        full_path = f"{project_path}/{asmdef_path}"
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        asmdef = {
            "name": assembly_name,
            "references": references,
            "includePlatforms": include_platforms,
            "excludePlatforms": exclude_platforms,
            "allowUnsafeCode": False,
            "overrideReferences": False,
            "precompiledReferences": [],
            "autoReferenced": True,
            "defineConstraints": [],
            "versionDefines": [],
            "noEngineReferences": False
        }
        try:
            Path(full_path).write_text(json.dumps(asmdef, indent=2))
            return f"Created Assembly Definition at {full_path}"
        except Exception as e:
            return f"Error creating asmdef: {str(e)}"

    async def _unity_validate_project(self, args: Dict) -> str:
        project_path = args.get("project_path", "")
        if not project_path:
            return "Error: project_path is required"
        issues = []
        warnings = []
        required_dirs = ["Assets", "ProjectSettings", "Packages"]
        for d in required_dirs:
            if not os.path.exists(f"{project_path}/{d}"):
                issues.append(f"Missing required directory: {d}")
        asmdefs = list(Path(project_path).rglob("*.asmdef"))
        if not asmdefs:
            warnings.append("No Assembly Definitions found - consider adding .asmdef files for better compilation")
        scripts = list(Path(project_path).rglob("*.cs"))
        no_namespace = []
        for script in scripts:
            content = script.read_text()
            if "namespace" not in content and "class " in content:
                no_namespace.append(str(script.relative_to(project_path)))
        if no_namespace:
            warnings.append(f"Scripts without namespace: {', '.join(no_namespace[:5])}")
        if not os.path.exists(f"{project_path}/ProjectSettings/ProjectSettings.asset"):
            issues.append("Missing ProjectSettings.asset")
        result = f"Validation for {project_path}:\n"
        if issues:
            result += f"\n❌ Issues ({len(issues)}):\n" + "\n".join(f"  - {i}" for i in issues)
        else:
            result += "\n✅ No critical issues found"
        if warnings:
            result += f"\n⚠️ Warnings ({len(warnings)}):\n" + "\n".join(f"  - {w}" for w in warnings)
        return result
