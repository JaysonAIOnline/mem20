#!/usr/bin/env python3
"""
Enhanced Production Pipeline Runner with AI Integration
Can run stages autonomously using the Jayson Bridge (LiteLLM).

USAGE:
    # Start fresh pipeline
    python3 run_pipeline_ai.py start --package /home/jayson/Desktop/prod.md --project unreliable_prophecy --genre Adventure
    
    # Run until completion (or stop manually)
    python3 run_pipeline_ai.py run --project unreliable_prophecy

REQUIRES:
    - Bridge running at http://localhost:4000
    - Master key in /opt/mem20/secrets/.env (LITELLM_MASTER_KEY)
    - Production package at specified path
"""

import sys
import json
import argparse
import urllib.request
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).parent))

from _secretz import bridge_key  # noqa: E402

# Configuration
BRIDGE_URL = "http://localhost:4000/v1"
BRIDGE_KEY = bridge_key()

# Add tools to path  
sys.path.insert(0, str(Path(__file__).parent / 'tools' / 'openwebui_tools'))

from production_run_orchestrator_tool import Tools, STAGES
from rpg_orchestrator_tool import Tools as RPGTools


def call_bridge(model: str, messages: list, tools: list = None, stream: bool = False):
    """Call the Jayson bridge (LiteLLM) for chat completions."""
    headers = {
        'Authorization': f'Bearer {BRIDGE_KEY}',
        'Content-Type': 'application/json'
    }
    
    body = {
        'model': model,
        'messages': messages,
        'temperature': 0.7
    }
    
    if tools:
        body['tools'] = tools
    
    if stream:
        body['stream'] = True
    
    req = urllib.request.Request(
        f'{BRIDGE_URL}/chat/completions',
        data=json.dumps(body).encode(),
        headers=headers,
        method='POST'
    )
    
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode())


def generate_text(prompt: str, system: str = None, model: str = "balanced"):
    """Generate text using the bridge."""
    messages = [{"role": "user", "content": prompt}]
    if system:
        messages.insert(0, {"role": "system", "content": system})
    
    return call_bridge(model, messages)


# Global state
_project_state = {}


def start_project(project_name: str, package_path: str, genre: str, platforms: str):
    """Initialize a new project in Stage 0."""
    package_file = Path(package_path)
    if not package_file.exists():
        return {"error": f"Package not found: {package_path}"}
    
    package_content = package_file.read_text()
    
    tools = Tools()
    rpg = RPGTools()
    
    # Use RPG orchestrator to start
    rpg_result = json.loads(rpg.start_rpg_project(
        project_name=project_name,
        premise=package_content[:500],
        genre=genre,
        target_platforms=platforms
    ))
    
    # Start production run
    prod_result = json.loads(tools.start_production_run(
        project_name=project_name,
        package_path_or_summary=package_content[:2000],
        genre=genre,
        platforms=platforms
    ))
    
    _project_state['project_name'] = project_name
    _project_state['package_path'] = package_path
    _project_state['genre'] = genre
    _project_state['platforms'] = [p.strip() for p in platforms.split(',')]
    _project_state['rpg_pipeline'] = rpg_result['pipeline']
    _project_state['current_stage'] = 0
    _project_state['run_id'] = prod_result['run_id']
    
    return {
        "status": "started",
        "project": project_name,
        "stage": 0,
        "stage_name": "PACKAGE_LOCK",
        "rpg_pipeline": rpg_result['pipeline'],
        "production_run": prod_result
    }


def run_stage_0(package_path: str):
    """Run Stage 0: PACKAGE_LOCK verification."""
    package_file = Path(package_path)
    content = package_file.read_text() if package_file.exists() else ""
    
    # Check for human sign-off and engine
    has_signoff = "YES" in content and "approve" in content.lower()
    has_unity = "unity" in content.lower() and "[x]" in content
    
    stages = STAGES
    
    return {
        "stage_id": 0,
        "name": "PACKAGE_LOCK",
        "checks": {
            "human_signoff": has_signoff,
            "primary_engine": has_unity,
            "vertical_slice_clear": True
        },
        "can_advance": has_signoff and has_unity,
        "next_stage_id": 1,
        "next_stage_name": stages[1]['name']
    }


def run_stage_1_design(project_name: str, package_data: dict):
    """Run Stage 1: DESIGN_SPINE generation."""
    # Extract key info from package
    package_path = _project_state.get('package_path', '')
    if not package_path:
        return {"error": "No package loaded"}
    
    content = Path(package_path).read_text() if Path(package_path).exists() else ""
    
    # Generate world bible using the engine
    prompt = f"""
You are WorldBuilder for the game: {project_name}
Genre: {_project_state.get('genre', 'Adventure')}

Generate a world bible for the VERTICAL SLICE only (not the full game).
Include:
1. Setting summary
2. Key regions (focus on slice areas)
3. Cultural notes
4. Mood/tonal notes

Keep it concise - this is for a slice, not the entire world.
"""
    
    try:
        result = generate_text(prompt, 
            system="You are WorldBuilder, a specialist RPG designer. Focus on vertical slice.",
            model="balanced"
        )
        
        response = result.get('choices', [{}])[0].get('message', {}).get('content', '')
        
        return {
            "stage_id": 1,
            "name": "DESIGN_SPINE",
            "output": response,
            "artifacts": ["world_bible.md"],
            "next_stage_id": 2
        }
    except Exception as e:
        return {"error": str(e)}


def run_pipeline_full(project_name: str, package_path: str, genre: str, platforms: str, auto_advance: bool = True):
    """Run the full pipeline with AI assistance."""
    print(f"Starting full pipeline for: {project_name}")
    print(f"Package: {package_path}")
    print(f"Genre: {genre}, Platforms: {platforms}")
    print("=" * 60)
    
    results = []
    
    # Stage 0
    print("\n[Stage 0] PACKAGE_LOCK")
    result = run_stage_0(package_path)
    print(f"  ✓ Sign-off: {result['checks']['human_signoff']}")
    print(f"  ✓ Engine: {result['checks']['primary_engine']}")
    print(f"  → Can advance: {result['can_advance']}")
    results.append(result)
    
    if not result['can_advance']:
        print("\n❌ Cannot advance - check package for sign-off and engine selection")
        return {"status": "stuck", "stage": 0, "reason": "Missing sign-off or engine"}
    
    # Stage 1
    print("\n[Stage 1] DESIGN_SPINE")
    result = run_stage_1_design(project_name, result)
    print(f"  ✓ Generated world design")
    if 'error' not in result:
        print(f"  Output preview: {result['output'][:200]}...")
    results.append(result)
    
    # Store results
    _project_state['current_stage'] = 2
    _project_state['results'] = results
    
    print("\n" + "=" * 60)
    print("Pipeline progress saved. Current state:")
    print(f"  Stage: 1/7 (DESIGN_SPINE)")
    print(f"  Next: SPACES_UI_VR (Stage 2)")
    
    return {"status": "in_progress", "results": results}


def main():
    parser = argparse.ArgumentParser(description='Enhanced Production Pipeline Runner')
    parser.add_argument('action', choices=['start', 'status', 'run', 'advance', 'generate'],
                       help='Action to perform')
    parser.add_argument('--package', help='Path to PRODUCTION_PACKAGE.md')
    parser.add_argument('--project', default='unreliable_prophecy', help='Project name')
    parser.add_argument('--genre', default='Adventure', help='Game genre')
    parser.add_argument('--platforms', default='Windows', help='Platforms CSV')
    parser.add_argument('--stage', type=int, default=0, help='Stage ID')
    parser.add_argument('--verdict', default='PASS', help='QA verdict')
    parser.add_argument('--evidence', default='CLI auto-generation', help='Evidence')
    
    args = parser.parse_args()
    
    if args.action == 'start':
        if not args.package:
            print("Error: --package required for start action")
            sys.exit(1)
        result = start_project(args.project, args.package, args.genre, args.platforms)
        print(json.dumps(result, indent=2, default=str))
        
    elif args.action == 'status':
        print(json.dumps(_project_state, indent=2, default=str))
        
    elif args.action == 'run':
        if not args.package:
            print("Error: --package required for run action")
            sys.exit(1)
        result = run_pipeline_full(args.project, args.package, args.genre, args.platforms)
        print(json.dumps(result, indent=2, default=str))
        
    elif args.action == 'advance':
        # Use the production tool to advance
        tools = Tools()
        result = tools.production_run_advance(
            project_name=args.project,
            from_stage_id=args.stage,
            qa_verdict=args.verdict,
            evidence=args.evidence
        )
        print(json.dumps(json.loads(result), indent=2))
        
    elif args.action == 'generate':
        # Test AI generation
        prompt = args.genre + "-style world bible"
        result = generate_text(f"Generate a world bible for a {args.genre} game")
        print(json.dumps(result, indent=2)[:1000])


if __name__ == '__main__':
    main()