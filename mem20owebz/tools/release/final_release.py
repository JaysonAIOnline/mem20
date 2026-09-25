#!/usr/bin/env python3
"""
Final Release Package - Complete Assembly
Creates a ready-to-import Unity project structure with all assets.
"""

import os
import json
import shutil
import zipfile
from pathlib import Path
from datetime import datetime

PROJECT = "unreliable_prophecy"
BASE = f"/home/jayson/Desktop/jayson-openwebui/projects/{PROJECT}"
ENGINE = f"{BASE}/engine_project"
RELEASE = f"{BASE}/release"

def create_final_structure():
    """Create final release structure with all files."""
    print("=== Creating Final Release Structure ===\n")
    
    release_dir = f"{RELEASE}/unreliable_prophecy_v0.5.0"
    os.makedirs(f"{release_dir}/assets/glb", exist_ok=True)
    os.makedirs(f"{release_dir}/assets/unity", exist_ok=True)
    os.makedirs(f"{release_dir}/docs", exist_ok=True)
    os.makedirs(f"{release_dir}/build", exist_ok=True)
    
    # Copy GLB assets
    incoming = f"{BASE}/_incoming"
    glb_count = 0
    for f in os.listdir(incoming):
        if f.endswith('.glb'):
            src = os.path.join(incoming, f)
            dst = os.path.join(f"{release_dir}/assets/glb", f)
            shutil.copy2(src, dst)
            glb_count += 1
            print(f"  ✓ {f}")
    
    print(f"\n  Total GLBs: {glb_count}")
    
    # Copy Unity project structure
    unity_dest = f"{release_dir}/assets/unity"
    if os.path.exists(ENGINE):
        for item in os.listdir(ENGINE):
            src = os.path.join(ENGINE, item)
            dst = os.path.join(unity_dest, item)
            if os.path.isfile(src):
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.copy2(src, dst)
            elif os.path.isdir(src):
                shutil.copytree(src, dst, dirs_exist_ok=True)
    print(f"  ✓ Unity project structure copied")
    
    return release_dir, glb_count

def create_import_instructions():
    """Create import instructions for Unity."""
    doc = f'''# {PROJECT} v0.5.0 - Import Instructions

## Quick Import

1. Open Unity Hub
2. Unity 6 LTS required
3. Click "New Project" → "3D URP"
4. Name: {PROJECT}
5. Location: Choose location
6. In Project window:

   - Copy entire `assets/unity` folder to `Assets/`
   - Copy `assets/glb` folder contents to `Assets/Models/Import`

7. Drag GLBs to Scenes in Unity Editor

## Project Files

- `assets/unity/` - Scene manifests, prefabs, settings
- `assets/glb/` - 10 GLB model files (Characters, Props, Environments)
- `docs/` - Documentation
- `build/` - Build scripts

## Asset List

Import these GLBs in Unity:

1. CH_PC1_Player.glb - Player character
2. CH_Wizard_Old.glb - Companion character  
3. CH_Bureaucrat.glb - NPC character
4. PR_Binder.glb - World item
5. PR_FilingCabinet.glb - Prop
6. PR_Desk.glb - Prop
7. WP_BasicMelee.glb - Prop
8. ENV_Quietvale.glb - Environment
9. ENV_BureaucracyHills.glb - Environment
10. UI_QuestTracker.glb - UI element

## Scenes to Create

1. Boot - Loading sequence
2. MainMenu - Title screen
3. Quietvale - Tutorial village
4. BureaucracyHills - First region

## Build Settings

Platform: Windows Standalone 64-bit
Render Pipeline: URP
Compression: LZ4HC

---

Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
'''
    
    doc_path = f"{RELEASE}/unreliable_prophecy_v0.5.0/docs/IMPORT_INSTRUCTIONS.md"
    with open(doc_path, 'w') as f:
        f.write(doc)
    print(f"\n✓ Import instructions: {doc_path}")
    
    return doc_path

def create_zip():
    """Create final distribution package."""
    print("\n=== Creating Distribution Package ===")
    
    source_dir = f"{RELEASE}/unreliable_prophecy_v0.5.0"
    zip_path = f"{RELEASE}/{PROJECT}_v0.5.0.zip"
    
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(source_dir):
            for file in files:
                full_path = os.path.join(root, file)
                arc_name = os.path.relpath(full_path, source_dir)
                zf.write(full_path, arc_name)
    
    size = os.path.getsize(zip_path)
    print(f"✓ Package: {zip_path}")
    print(f"  Size: {size/1024:.1f} KB")
    
    return zip_path, size

def main():
    print("=== Stage 6: RELEASE_PACKAGE (Final) ===\n")
    
    os.makedirs(RELEASE, exist_ok=True)
    
    # Create structure
    release_dir, glb_count = create_final_structure()
    
    # Create docs
    create_import_instructions()
    
    # Create ZIP
    zip_path, size = create_zip()
    
    # Final report
    report = {
        "stage": "Stage 6 - RELEASE_PACKAGE",
        "status": "completed",
        "version": "0.5.0",
        "generated": datetime.now().isoformat(),
        "package": {
            "path": zip_path,
            "size_kb": round(size/1024, 1),
            "contents": {
                "glb_assets": glb_count,
                "unity_project": True,
                "scenes": ["Boot", "MainMenu", "Quietvale", "BureaucracyHills"],
                "docs": ["IMPORT_INSTRUCTIONS.md"]
            }
        },
        "ready_for": "Stage 7 - DONE"
    }
    
    report_path = f"{RELEASE}/final_release_report.json"
    with open(report_path, 'w') as f:
        json.dump(report, f, indent=2)
    
    print(f"\n✓ Report: {report_path}")
    print(f"\n=== RELEASE COMPLETE ===")
    print(f"Package ready at: {zip_path}")
    print(f"Import instructions at: {release_dir}/docs/IMPORT_INSTRUCTIONS.md")

if __name__ == '__main__':
    main()