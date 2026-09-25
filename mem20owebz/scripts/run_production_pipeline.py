#!/usr/bin/env python3
"""
Production Pipeline Runner - CLI version
Runs the idea->game pipeline without requiring Open WebUI GUI.

Usage:
    python3 scripts/run_production_pipeline.py \
        --project "my_first_game" \
        --package "projects/my_first_game/PRODUCTION_PACKAGE.md" \
        --genre "RPG" \
        --platforms "Windows,Linux"
"""

import argparse
import json
import os
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

# Bridge connection
BRIDGE_URL = os.environ.get('JAYSON_BRIDGE_URL', 'http://localhost:4000/v1')
BRIDGE_KEY = os.environ.get('JAYSON_BRIDGE_KEY', 'jayson-bridge-secret-change-me')

# Import the tool logic from the OpenWebUI tools
sys.path.insert(0, str(Path(__file__).parent.parent / 'tools' / 'openwebui_tools'))

from production_run_orchestrator_tool import STAGES


def call_bridge(model: str, messages: list, tools: list = None):
    """Call the Jayson bridge (LiteLLM) with a chat completion."""
    headers = {
        'Authorization': f'Bearer {BRIDGE_KEY}',
        'Content-Type': 'application/json'
    }
    
    body = {
        'model': model,
        'messages': messages
    }
    
    if tools:
        body['tools'] = tools
    
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        BRIDGE_URL + '/chat/completions',
        data=data,
        headers=headers,
        method='POST'
    )
    
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode())


def start_production_run(project_name: str, package_path: str, genre: str, platforms: str):
    """Initialize a production run."""
    # Read the package
    with open(package_path, 'r') as f:
        package_content = f.read()[:2000]
    
    platforms_list = [p.strip() for p in platforms.split(',') if p.strip()]
    
    run_config = {
        'run_id': datetime.utcnow().strftime("%Y%m%d%H%M%S"),
        'project_name': project_name,
        'package_ref': package_content,
        'genre': genre,
        'platforms': platforms_list,
        'supervision': 'every_handoff',
        'fidelity_target': 0.94,
        'current_stage_id': 0,
        'stages': STAGES,
        'status': 'RUNNING',
        'current_stage': STAGES[0]
    }
    
    return run_config


def get_stage(stage_id: int):
    """Get stage info by ID."""
    for s in STAGES:
        if s['id'] == stage_id:
            return s
    return None


def advance_stage(current_id: int, qa_verdict: str, evidence: str):
    """Advance to next stage if QA passed."""
    stage = get_stage(current_id)
    if not stage:
        return {'error': 'Invalid stage id'}
    
    verdict = (qa_verdict or '').upper().strip()
    if verdict not in ('PASS', 'PASS_WITH_NOTES'):
        return {
            'advanced': False,
            'reason': 'QA did not pass',
            'qa_verdict': verdict,
            'stay_on_stage': current_id
        }
    
    next_id = stage.get('next_on_pass')
    next_stage = get_stage(next_id) if next_id else None
    
    return {
        'advanced': True,
        'from': stage['name'],
        'to': next_stage['name'] if next_stage else 'DONE',
        'to_stage_id': next_id,
        'evidence': evidence
    }


def run_pipeline(project_name: str, package_path: str, genre: str, platforms: str):
    """Run the full production pipeline."""
    print(f"Starting production pipeline for: {project_name}")
    print(f"Package: {package_path}")
    print(f"Genre: {genre}")
    print(f"Platforms: {platforms}")
    print("=" * 60)
    
    # Initialize
    config = start_production_run(project_name, package_path, genre, platforms)
    current_stage = config['current_stage']
    stage_id = 0
    
    print(f"Stage 0: {current_stage['name']}")
    print(f"Goal: {current_stage['goal']}")
    
    # For CLI, we simulate the pipeline stages
    # In production, this would be interactive
    for stage in STAGES:
        stage_id = stage['id']
        stage_name = stage['name']
        
        if stage_name == 'DONE':
            print("\n✓ PRODUCTION COMPLETE!")
            break
        
        print(f"\n--- Stage {stage_id}: {stage_name} ---")
        print(f"Goal: {stage['goal']}")
        print(f"Tools: {', '.join(stage['tools'])}")
        print(f"QA requirement: {stage['qa']}")
        
        # In a real CLI, you'd run the actual tools here
        # For now, simulate progression
        print(f"You would execute this stage now.")
        print(f"To advance after QA PASS, run: python3 scripts/run_production_pipeline.py --advance {stage_id} --verdict PASS --evidence '...'")
        
    return config


def main():
    parser = argparse.ArgumentParser(description='Production Pipeline Runner')
    parser.add_argument('--project', required=True, help='Project name')
    parser.add_argument('--package', required=True, help='Path to PRODUCTION_PACKAGE.md')
    parser.add_argument('--genre', default='RPG', help='Game genre')
    parser.add_argument('--platforms', default='Windows', help='Comma-separated platforms')
    parser.add_argument('--advance', type=int, help='Advance from stage ID')
    parser.add_argument('--verdict', default='PASS', help='QA verdict')
    parser.add_argument('--evidence', default='CLI advancement', help='QA evidence')
    
    args = parser.parse_args()
    
    if args.advance is not None:
        result = advance_stage(args.advance, args.verdict, args.evidence)
        print(json.dumps(result, indent=2))
    else:
        if not os.path.exists(args.package):
            print(f"Error: Package not found: {args.package}")
            sys.exit(1)
        
        result = run_pipeline(args.project, args.package, args.genre, args.platforms)
        print(json.dumps(result, indent=2, default=str))


if __name__ == '__main__':
    main()