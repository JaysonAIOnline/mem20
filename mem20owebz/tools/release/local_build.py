#!/usr/bin/env python3
"""
Local Unity Build Script
Builds using the Unity Editor you have installed locally.
"""

import subprocess
import os
import sys
import json
from pathlib import Path

def find_unity_editor():
    """Find Unity Editor binary on this system."""
    common_paths = [
        '/home/jayson/Unity/Hub/Editor/6000.5.9f1/Editor/Unity',
        '/home/jayson/Unity/Hub/Editor/6000.3.22f1/Editor/Unity',
        '/opt/Unity/Editor/Unity',
        '/usr/local/unity/Editor/Unity',
    ]
    
    for path in common_paths:
        if os.path.exists(path):
            return path
    
    # Check PATH
    result = subprocess.run(['which', 'unity'], capture_output=True, text=True)
    if result.returncode == 0:
        return result.stdout.strip()
    
    return None

def build_project(project_path, output_path, unity_path=None):
    """Build the Unity project."""
    
    # Find Unity if not specified
    if not unity_path:
        unity_path = find_unity_editor()
        if not unity_path:
            print("✗ Unity Editor not found! Install Unity 6 LTS and try again.")
            return False
    
    print(f"Using Unity at: {unity_path}")
    print(f"Project: {project_path}")
    print(f"Output: {output_path}")
    
    # Check Unity version
    result = subprocess.run([unity_path, '--version'], capture_output=True, text=True, timeout=10)
    version = result.stdout.strip() or result.stderr.strip()
    print(f"Unity Version: {version}")
    
    # Create output directory
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    # Run build
    cmd = [
        unity_path,
        '-quit',
        '-batchmode',
        '-projectPath', project_path,
        '-buildTarget', 'StandaloneWindows64',
        '-logFile', os.path.join(os.path.dirname(output_path), 'build.log')
    ]
    
    # Check for executeMethod
    build_script = os.path.join(project_path, 'Assets/Editor/BuildAutomation.cs')
    if os.path.exists(build_script):
        cmd.extend(['-executeMethod', 'BuildAutomation.BuildWindows'])
    
    # Add output path via environment or args
    cmd.extend(['-customBuildPath', output_path])
    
    print("\nRunning build...")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    
    # Check output
    if result.returncode == 0:
        print("\n✓ Build completed successfully!")
        if os.path.exists(output_path):
            size = os.path.getsize(output_path)
            print(f"  Executable: {output_path} ({size/1024/1024:.2f} MB)")
        return True
    else:
        print(f"\n✗ Build failed (exit code: {result.returncode})")
        if result.stderr:
            print(f"  Error: {result.stderr[:500]}")
        return False

def main():
    print("=== Local Unity Build ===\n")
    
    project_path = '/home/jayson/Desktop/jayson-openwebui/projects/unreliable_prophecy/engine_project'
    output_path = '/home/jayson/Desktop/jayson-openwebui/projects/unreliable_prophecy/release/build/unreliable_prophecy.exe'
    
    if not os.path.exists(project_path):
        print(f"✗ Project not found: {project_path}")
        print("  Run: python3 tools/unity/unity_assembly.py first")
        return 1
    
    success = build_project(project_path, output_path)
    
    if success:
        print("\n=== Build Complete ===")
        print("Run the executable: " + output_path)
    else:
        print("\n=== Build Failed ===")
        print("Check build.log for details")
    
    return 0 if success else 1

if __name__ == '__main__':
    sys.exit(main())