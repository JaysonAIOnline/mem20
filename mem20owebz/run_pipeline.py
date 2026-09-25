#!/usr/bin/env python3
"""
Production Pipeline Executor - Direct CLI for Jayson
Usage:
    python3 run_pipeline.py --package /home/jayson/Desktop/prod.md --project unreliable_prophecy --genre Adventure
"""

import sys
import json
import argparse
from pathlib import Path

# Add tools to path
sys.path.insert(0, str(Path(__file__).parent / 'tools' / 'openwebui_tools'))

from production_run_orchestrator_tool import Tools, STAGES
from rpg_orchestrator_tool import Tools as RPGTools


def main():
    parser = argparse.ArgumentParser(description='Run Game Production Pipeline')
    parser.add_argument('--package', required=True, help='Path to production package MD')
    parser.add_argument('--project', default='game_project', help='Project name')
    parser.add_argument('--genre', default='Adventure', help='Game genre')
    parser.add_argument('--platforms', default='Windows', help='Platforms CSV')
    parser.add_argument('--step', type=int, default=0, help='Current stage (0=start)')
    parser.add_argument('--action', choices=['start', 'status', 'advance'], default='start')
    args = parser.parse_args()
    
    # Load package
    package_path = Path(args.package)
    if not package_path.exists():
        print(f"Error: Package not found: {package_path}")
        sys.exit(1)
    
    package_content = package_path.read_text()[:2000]
    
    # Create tool instances
    prod_tool = Tools()
    rpg_tool = RPGTools()
    
    if args.action == 'start':
        result = prod_tool.start_production_run(
            project_name=args.project,
            package_path_or_summary=package_content,
            genre=args.genre,
            platforms=args.platforms
        )
        print("=== PIPELINE STARTED ===")
        print(result)
        
    elif args.action == 'status':
        result = prod_tool.production_run_status(
            project_name=args.project,
            current_stage_id=args.step
        )
        print("=== PIPELINE STATUS ===")
        print(result)
        
    elif args.action == 'advance':
        # Get next stage info
        if args.step < len(STAGES) - 1:
            next_stage = STAGES[args.step + 1]
            print(f"\n=== ADVANCE TO STAGE {args.step + 1} ===")
            print(f"Name: {next_stage['name']}")
            print(f"Goal: {next_stage['goal']}")
            print(f"Tools: {next_stage['tools']}")
            print(f"QA: {next_stage['qa']}")
        else:
            print("✓ PIPELINE COMPLETE!")


if __name__ == '__main__':
    main()