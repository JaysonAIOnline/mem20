#!/usr/bin/env python3
"""
Unity Scene Assembly Generator
Creates Unity project structure and scene files from GLB assets.
"""

import os
import subprocess
import json
from pathlib import Path

# Paths
PROJECT_NAME = "unreliable_prophecy"
UNITY_PROJECT = f"/home/jayson/Desktop/jayson-openwebui/projects/{PROJECT_NAME}/engine_project"
ASSETS_IN = f"/home/jayson/Desktop/jayson-openwebui/projects/{PROJECT_NAME}_assets"
GLB_PATH = f"/home/jayson/Desktop/jayson-openwebui/projects/{PROJECT_NAME}/_incoming"

def create_unity_project():
    """Create Unity project folder structure."""
    print("Creating Unity project structure...\n")
    
    paths = [
        f"{UNITY_PROJECT}",
        f"{UNITY_PROJECT}/Assets",
        f"{UNITY_PROJECT}/Assets/Characters",
        f"{UNITY_PROJECT}/Assets/Props",
        f"{UNITY_PROJECT}/Assets/Environments", 
        f"{UNITY_PROJECT}/Assets/UI",
        f"{UNITY_PROJECT}/Assets/Scenes",
        f"{UNITY_PROJECT}/Assets/Prefabs",
        f"{UNITY_PROJECT}/Assets/Materials",
        f"{UNITY_PROJECT}/Assets/Scripts",
        f"{UNITY_PROJECT}/ProjectSettings",
    ]
    
    for p in paths:
        os.makedirs(p, exist_ok=True)
        print(f"  ✓ Created: {p}")
    
    # Create project settings
    settings = {
        "bundleVersion": "0.5.0",
        "companyName": "Jayson",
        "productName": PROJECT_NAME,
        "projectVersion": "6.0.0",
        "apiCompatibilityLevel": ".NETStandard2.1"
    }
    
    os.makedirs(f"{UNITY_PROJECT}/ProjectSettings", exist_ok=True)
    with open(f"{UNITY_PROJECT}/ProjectSettings/ProjectVersion.txt", 'w') as f:
        f.write(f"m_EditorVersion: 6.0.0\n")
    
    print(f"\n✓ Unity project created at {UNITY_PROJECT}")
    return True

def generate_scene_manifest():
    """Generate scene manifest for Unity."""
    scenes = {
        "Boot": {
            "name": "Boot Scene",
            "description": "Initial loading sequence",
            "prefabs": [],
            "lighting": "main_menu"
        },
        "MainMenu": {
            "name": "Main Menu",
            "description": "Title screen and menu",
            "prefabs": ["UI_QuestTracker"],
            "lighting": "soft"
        },
        "Quietvale": {
            "name": "Quietvale Village",
            "description": "Starter region - tutorial area",
            "prefabs": ["CH_PC1_Player", "CH_Wizard_Old", "PR_Binder", "PR_Desk"],
            "environments": ["ENV_Quietvale"],
            "lighting": "warm_morning"
        },
        "BureaucracyHills": {
            "name": "Bureaucracy Hills",
            "description": "First regional area",
            "prefabs": ["CH_Bureaucrat", "PR_FilingCabinet", "WP_BasicMelee"],
            "environments": ["ENV_BureaucracyHills"],
            "lighting": "institutional"
        },
        "CombatTest": {
            "name": "Combat Test Area",
            "description": "Enemy testing space",
            "prefabs": ["CH_PC1_Player", "CH_Bureaucrat"],
            "lighting": "neutral"
        }
    }
    
    manifest_path = f"{UNITY_PROJECT}/Assets/Scenes/scenes_manifest.json"
    with open(manifest_path, 'w') as f:
        json.dump(scenes, f, indent=2)
    
    print(f"✓ Scene manifest created: {manifest_path}")
    return scenes

def create_prefab_links():
    """Create prefab links from GLBs."""
    print("\nLinking GLBs to Prefabs:")
    
    links = {}
    for f in os.listdir(GLB_PATH):
        if f.endswith('.glb'):
            name = f.replace('.glb', '')
            links[name] = f"{GLB_PATH}/{f}"
            print(f"  ✓ {name} -> {GLB_PATH}/{f}")
    
    links_path = f"{UNITY_PROJECT}/Assets/Prefabs/prefab_links.json"
    with open(links_path, 'w') as f:
        json.dump(links, f, indent=2)
    
    return links

def generate_unity_scene(scene_name, scene_data):
    """Generate a partial YAML scene file."""
    # Unity scenes are YAML/JSON based
    scene = {
        "m_ObjectHideFlags": 0,
        "m_CorrespondingSourceObject": {"m_ObjectHideFlags": 0},
        "m_PrefabInstance": {
            "m_ObjectHideFlags": 0,
            "m_CorrespondingSourceObject": {"m_ObjectHideFlags": 0}
        },
        "m_GameObject": {
            "m_Name": scene_name,
            "m_Tag": "Untagged",
            "m_Layer": 0,
            "m_Component": [],
            "m_Enabled": 1
        }
    }
    
    # Add prefabs to scene
    for prefab in scene_data.get('prefabs', []):
        go = {
            "m_Name": prefab,
            "m_Tag": "Untagged",
            "m_Layer": 0,
            "m_Component": [],
            "m_Enabled": 1
        }
        print(f"  | Added {prefab} to {scene_name}")
    
    return scene

def main():
    print("=== Unity Scene Assembly Generator ===\n")
    
    # Create project
    create_unity_project()
    
    # Generate scene manifest
    scenes = generate_scene_manifest()
    
    # Create prefab links
    links = create_prefab_links()
    
    # Print summary
    print(f"\n=== Assembly Summary ===")
    print(f"Project: {PROJECT_NAME}")
    print(f"Location: {UNITY_PROJECT}")
    print(f"Scenes: {list(scenes.keys())}")
    print(f"Prefabs linked: {len(links)}")
    
    # Save assembly report
    report = {
        "project": PROJECT_NAME,
        "stage": "Stage 4 - ASSEMBLY",
        "status": "generated",
        "scenes": scenes,
        "prefab_links": links,
        "output_path": UNITY_PROJECT
    }
    
    with open(f"{UNITY_PROJECT}/ASSEMBLY_REPORT.json", 'w') as f:
        json.dump(report, f, indent=2)
    
    print(f"\n✓ Assembly report: {UNITY_PROJECT}/ASSEMBLY_REPORT.json")

if __name__ == '__main__':
    main()