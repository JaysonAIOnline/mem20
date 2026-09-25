#!/usr/bin/env python3
"""
Rate-Limited Production Pipeline Queue System
Handles rate limiting gracefully with backoff and retry logic.

Usage:
    python3 run_pipeline_queued.py start --package prod.md --project mygame
    python3 run_pipeline_queued.py run-stage 0
    python3 run_pipeline_queued.py list-runs
    python3 run_pipeline_queued.py status
"""

import sys
import json
import time
import argparse
import hashlib
import re
import urllib.request
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).parent))

from _secretz import bridge_key  # noqa: E402

# Configuration
BRIDGE_URL = "http://localhost:4000/v1"
BRIDGE_KEY = bridge_key()
RATE_LIMIT_WAIT = 30
MAX_RETRIES = 3

# Add tools to path
sys.path.insert(0, str(Path(__file__).parent / 'tools' / 'openwebui_tools'))

# State storage
STATE_DIR = Path.home() / '.pipeline_runs'
STATE_DIR.mkdir(exist_ok=True)


class RateLimitedBridge:
    """Bridge client with rate-limit handling."""
    
    def __init__(self):
        self.last_request = 0
        self.consecutive_429s = 0
        
    def call(self, model: str, messages: list, tools: list = None) -> dict:
        """Make a rate-limited bridge call."""
        elapsed = time.time() - self.last_request
        if elapsed < 2:
            time.sleep(2 - elapsed)
        
        headers = {
            'Authorization': f'Bearer {BRIDGE_KEY}',
            'Content-Type': 'application/json'
        }
        
        body = json.dumps({
            'model': model,
            'messages': messages,
            'temperature': 0.7
        }).encode()
        
        req = urllib.request.Request(
            f'{BRIDGE_URL}/chat/completions',
            data=body,
            headers=headers,
            method='POST'
        )
        
        for attempt in range(MAX_RETRIES):
            try:
                self.last_request = time.time()
                with urllib.request.urlopen(req, timeout=120) as resp:
                    self.consecutive_429s = 0
                    return json.loads(resp.read().decode())
            except urllib.error.HTTPError as e:
                if e.code == 429:
                    wait = RATE_LIMIT_WAIT * (2 ** self.consecutive_429s)
                    print(f"  Rate limited (429), waiting {wait}s... (attempt {attempt + 1}/{MAX_RETRIES})")
                    time.sleep(wait)
                    self.consecutive_429s += 1
                else:
                    raise
            except Exception as e:
                if attempt < MAX_RETRIES - 1:
                    time.sleep(5)
                    continue
                raise
        
        raise Exception(f"Failed after {MAX_RETRIES} retries due to rate limiting")


class PipelineQueue:
    """Manages pipeline state and queues."""
    
    def __init__(self, project_name: str):
        self.project_name = project_name
        self.state_file = STATE_DIR / f"{hashlib.md5(project_name.encode()).hexdigest()}.json"
        self.bridge = RateLimitedBridge()
        self.load_state()
    
    def load_state(self):
        if self.state_file.exists():
            with open(self.state_file) as f:
                self.state = json.load(f)
        else:
            self.state = {
                'project_name': self.project_name,
                'started_at': datetime.now(timezone.utc).isoformat(),
                'current_stage': 0,
                'stages': [],
                'artifacts': {},
                'qa_results': []
            }
    
    def save_state(self):
        with open(self.state_file, 'w') as f:
            json.dump(self.state, f, indent=2, default=str)
    
    def current_stage(self):
        from production_run_orchestrator_tool import STAGES
        stage_id = self.state.get('current_stage', 0)
        if stage_id < len(STAGES):
            return STAGES[stage_id]
        return None
    
    def advance(self):
        stage = self.current_stage()
        if stage:
            self.state['current_stage'] += 1
            self.save_state()
            return True
        return False


def start_pipeline(project_name: str, package_path: str, genre: str, platforms: str):
    """Initialize a new pipeline run."""
    pkg_file = Path(package_path)
    if not pkg_file.exists():
        return {'error': f'Package not found: {package_path}'}
    
    content = pkg_file.read_text()
    
    pipeline = PipelineQueue(project_name)
    pipeline.state['package_path'] = str(package_path)
    pipeline.state['genre'] = genre
    pipeline.state['platforms'] = [p.strip() for p in platforms.split(',')]
    pipeline.state['package_content'] = content[:3000]
    pipeline.state['run_id'] = datetime.now().strftime('%Y%m%d%H%M%S')
    
    # Better detection for sign-off and engine
    has_signoff = bool(re.search(r'YES', content[:5000])) or 'approved' in content.lower()
    has_unity = 'unity' in content.lower() and ('[x]' in content or 'unity 6' in content.lower() or 'unity' in content.lower()[:100])
    
    pipeline.state['stage_0'] = {
        'human_signoff': has_signoff,
        'primary_engine': 'Unity' if has_unity else 'unknown',
        'can_proceed': has_signoff and has_unity
    }
    
    pipeline.save_state()
    
    return {
        'status': 'started',
        'run_id': pipeline.state['run_id'],
        'project_name': project_name,
        'stage': 0,
        'stage_name': 'PACKAGE_LOCK',
        'verification': pipeline.state['stage_0'],
        'can_advance': pipeline.state['stage_0']['can_proceed'],
        'state_file': str(pipeline.state_file)
    }


def run_current_stage(project_name: str, auto_qa: bool = True) -> dict:
    """Execute the current stage."""
    pipeline = PipelineQueue(project_name)
    stage = pipeline.current_stage()
    
    if not stage:
        return {'status': 'complete', 'message': 'Pipeline finished'}
    
    result = {
        'stage_id': stage['id'],
        'stage_name': stage['name'],
        'started_at': datetime.now().isoformat(),
        'goal': stage['goal']
    }
    
    print(f"\n{'='*50}")
    print(f"Running Stage {stage['id']}: {stage['name']}")
    print(f"Goal: {stage['goal']}")
    print(f"Tools: {', '.join(stage['tools'])}")
    print(f"{'='*50}\n")
    
    if stage['id'] == 0:
        verification = pipeline.state.get('stage_0', {})
        result['checks'] = verification
        result['status'] = 'complete' if verification.get('can_proceed') else 'stuck'
        print(f"✓ Sign-off: {verification.get('human_signoff', False)}")
        print(f"✓ Engine: {verification.get('primary_engine', 'unknown')}")
        print(f"  Can advance: {verification.get('can_proceed', False)}")
        
    elif stage['id'] == 1:
        print("Generating world design...")
        try:
            response = pipeline.bridge.call('balanced', [
                {'role': 'system', 'content': 'You are WorldBuilder, a specialist RPG designer. Focus on vertical slice only.'},
                {'role': 'user', 'content': f"""
Generate a world bible for the Adventure game "The Unreliable Prophecy".

Key details:
- Setting: Fantasy world with celestial bureaucracy  
- Tone: Dry, institutional, understated
- Vertical slice: Quietvale village + Bureaucracy Hills region
- Must include: Regions, cultures, historical notes, tone guides

Return as markdown with clear sections.
"""}
            ], max_tokens=600)
            
            content = response['choices'][0]['message']['content']
            artifact_path = STATE_DIR / f"{project_name}_world_bible.md"
            artifact_path.write_text(content)
            
            pipeline.state['artifacts']['world_bible'] = str(artifact_path)
            pipeline.save_state()
            
            result['output'] = str(artifact_path)
            result['content_preview'] = content[:500]
            result['status'] = 'complete'
            print(f"✓ World bible generated: {artifact_path}")
            
        except Exception as e:
            result['error'] = str(e)
            result['status'] = 'error'
            print(f"✗ Error: {e}")
            
    elif stage['id'] == 2:
        print("Generating level specs...")
        try:
            response = pipeline.bridge.call('balanced', [
                {'role': 'system', 'content': 'You are a game designer specializing in level design.'},
                {'role': 'user', 'content': '''
Generate level specifications for the vertical slice of "The Unreliable Prophecy".

Regions in scope (P0):
1. Quietvale - Starter village
2. Bureaucracy Hills - First major region

For each region, specify:
- Key landmarks  
- Encounter types
- Visual themes
- Bureaucratic elements

Keep it concise for vertical slice planning.
'''}
            ], max_tokens=400)
            
            content = response['choices'][0]['message']['content']
            artifact_path = STATE_DIR / f"{project_name}_level_specs.md"
            artifact_path.write_text(content)
            
            pipeline.state['artifacts']['level_specs'] = str(artifact_path)
            pipeline.save_state()
            
            result['output'] = str(artifact_path)
            result['status'] = 'complete'
            print(f"✓ Level specs generated: {artifact_path}")
            
        except Exception as e:
            result['error'] = str(e)
            result['status'] = 'error'
    
    else:
        result['status'] = 'skip'
        result['message'] = f'Stage {stage["id"]} needs custom implementation'
        print(f"⏭️ Stage {stage['id']} - placeholder")
    
    return result


def list_runs():
    """List all pipeline runs."""
    runs = []
    for state_file in STATE_DIR.glob('*.json'):
        if state_file.name == 'state.json':
            continue
        with open(state_file) as f:
            state = json.load(f)
            runs.append({
                'run_id': state.get('run_id', state_file.stem),
                'project_name': state.get('project_name', 'unknown'),
                'current_stage': state.get('current_stage', 0),
                'started_at': state.get('started_at', 'unknown')
            })
    
    return {'runs': runs, 'count': len(runs)}


def status(project_name: str = None):
    """Get current pipeline status."""
    if project_name:
        pipeline = PipelineQueue(project_name)
        return {
            'project_name': project_name,
            'run_id': pipeline.state.get('run_id'),
            'current_stage': pipeline.state.get('current_stage', 0),
            'stage_name': pipeline.current_stage()['name'] if pipeline.current_stage() else 'DONE',
            'artifacts': list(pipeline.state.get('artifacts', {}).keys()),
            'state_file': str(pipeline.state_file)
        }
    return list_runs()


def main():
    parser = argparse.ArgumentParser(description='Rate-Limited Pipeline Queue')
    subparsers = parser.add_subparsers(dest='action', help='Actions')
    
    # Start command
    subparsers.add_parser('start')
    # Status command
    subparsers.add_parser('status')
    # List runs command
    subparsers.add_parser('list-runs')
    
    parser.add_argument('--project', default='unreliable_prophecy')
    parser.add_argument('--package', default='/home/jayson/Desktop/prod.md')
    parser.add_argument('--genre', default='Adventure')
    parser.add_argument('--platforms', default='Windows')
    parser.add_argument('--stage', type=int, default=None)
    
    args = parser.parse_args()
    
    if args.action == 'start':
        result = start_pipeline(args.project, args.package, args.genre, args.platforms)
        print(json.dumps(result, indent=2))
        
    elif args.action == 'status':
        result = status(args.project)
        print(json.dumps(result, indent=2))
        
    elif args.action == 'list-runs':
        result = list_runs()
        print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()