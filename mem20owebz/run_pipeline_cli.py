#!/usr/bin/env python3
"""
Production Pipeline Runner - CLI Version
Waits for rate limit cooldown automatically.

Usage:
    python3 run_pipeline_cli.py generate-assets --project unreliable_prophecy
"""

import time
import json
import subprocess
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).parent))

from _secretz import bridge_key  # noqa: E402

print("=== Stage 3: ASSET_PRODUCTION CLI Runner ===")
print()

_bridge_key = bridge_key()

# Check if bridge is ready
print("Checking bridge availability...")
import urllib.request

ready = False
attempts = 0
while not ready and attempts < 6:
    try:
        with urllib.request.urlopen('http://localhost:4000/health/liveliness', timeout=5) as r:
            if r.status == 200:
                ready = True
                print("✓ Bridge is healthy")
    except:
        attempts += 1
        print(f"  Waiting... (attempt {attempts}/6)")
        time.sleep(15)

if not ready:
    print("✗ Bridge still cooling down. Try again in 1-2 minutes.")
    exit(1)

# Now generate assets using curl
print("\nGenerating asset batch 1 (P0 characters)...")

prompt = '''
Generate a text prompt for a 3D character asset in the adventure game "The Unreliable Prophecy".

Character: Old Wizard
- Appearance: Ancient, tired celestial wizard
- Style: Fantasy, readable silhouette, wrinkled robes
- Color: Muted blues and greys with occasional starlight
- Mood: Cynical, weary, ancient mentor
- Poly budget: ≤20k tris

Return ONLY the prompt that would work with a text-to-3D AI.
'''

result = subprocess.run([
    'curl', '-s', '-X', 'POST', 'http://localhost:4000/v1/chat/completions',
    '-H', f'Authorization: Bearer {_bridge_key}',
    '-H', 'Content-Type: application/json',
    '-d', json.dumps({
        'model': 'balanced',
        'messages': [{'role': 'user', 'content': prompt}],
        'max_tokens': 200,
        'temperature': 0.7
    })
], capture_output=True, text=True, timeout=60)

if result.returncode == 0:
    try:
        data = json.loads(result.stdout)
        if 'error' in data:
            print(f"  Error: {data['error']['message']}")
        else:
            content = data['choices'][0]['message']['content']
            print("✓ Generated prompt:")
            print(f"  {content[:300]}...")
    except:
        print(f"  Raw output: {result.stdout[:200]}")
else:
    print(f"  Curl failed: {result.stderr[:100]}")

print("\n=== Asset Generation Command Complete ===")
print("Store output in: projects/unreliable_prophecy/_incoming/")
print("Update manifest in: projects/unreliable_prophecy/assets_manifest.csv")