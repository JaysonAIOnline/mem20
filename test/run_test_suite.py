#!/usr/bin/env python3
"""
Production Test Suite for mem20 Cognitive Substrate
Tests all 22 bots with complex tasks and logs evolutionary learning results.
"""

import os
import sys
import json
import time
import sqlite3
import subprocess
from datetime import datetime
from pathlib import Path

# ── Configuration ──────────────────────────────────────────────────────

BOTS = [
    "advertising", "analyst", "assistant", "betatesting", "blendie",
    "business", "ceo", "cloud", "coach", "coder", "gamemaster",
    "github", "jayson", "kickstarter", "mem20", "mem20-bot", "qamaster",
    "radar", "research", "shrink", "skillresearcher", "unito", "webdev"
]

COMPLEX_TASKS = [
    {
        "name": "multi_path_decision",
        "prompt": "I need to choose between three different approaches for building a real-time chat system. Each has different trade-offs in cost, latency, and complexity. Help me decide which is best for a startup with limited budget but high growth expectations.",
        "expected_branches": 3,
    },
    {
        "name": "safety_critical",
        "prompt": "Write a script that deletes all files in a directory that haven't been accessed in 30 days. Make sure it's safe and won't accidentally delete important files.",
        "expected_safety_check": True,
    },
    {
        "name": "idempotency_test",
        "prompt": "Create a database migration that adds a new column to a table. It should be safe to run multiple times without errors.",
        "expected_idempotent": True,
    },
    {
        "name": "context_drift",
        "prompt": "First, tell me about the history of Python. Then explain how Python 3.12 improves performance. Then tell me which Python web framework is best for a REST API. Finally, summarize the key points about Python's evolution.",
        "expected_drift_check": True,
    },
    {
        "name": "expensive_action",
        "prompt": "I need to process 10 million records from a CSV file and upload them to a database. What's the most efficient approach?",
        "expected_resource_analysis": True,
    },
]

DB_PATH = os.path.expanduser("~/.mem20/tot_state.db")
RESULTS_DIR = os.path.expanduser("~/.mem20/test_results")

# ── Test Runner ────────────────────────────────────────────────────────

def init_results_dir():
    os.makedirs(RESULTS_DIR, exist_ok=True)

def get_db_connection():
    return sqlite3.connect(DB_PATH)

def count_nodes(session_id):
    """Count ToT nodes for a session."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM tot_nodes WHERE session_id = ?", (session_id,))
        count = cursor.fetchone()[0]
        conn.close()
        return count
    except Exception:
        return 0

def count_pruned(session_id):
    """Count pruned nodes for a session."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM tot_nodes WHERE session_id = ? AND status = 'pruned'", (session_id,))
        count = cursor.fetchone()[0]
        conn.close()
        return count
    except Exception:
        return 0

def get_score_deltas(session_id):
    """Get all score deltas for a session."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT heuristic_score_delta FROM tot_nodes WHERE session_id = ?", (session_id,))
        deltas = [row[0] for row in cursor.fetchall()]
        conn.close()
        return deltas
    except Exception:
        return []

def run_bot_task(bot_name, task):
    """Run a single task through a bot and measure results."""
    session_id = f"test-{bot_name}-{task['name']}-{int(time.time())}"
    
    start_time = time.time()
    
    try:
        # Run the bot with the task prompt
        result = subprocess.run(
            ["hermes", "-p", bot_name, "chat", "-q", task["prompt"]],
            capture_output=True,
            text=True,
            timeout=120,
        )
        
        elapsed = time.time() - start_time
        output = result.stdout.strip()
        success = result.returncode == 0
        
        # Check ToT state
        node_count = count_nodes(session_id)
        pruned_count = count_pruned(session_id)
        score_deltas = get_score_deltas(session_id)
        
        return {
            "bot": bot_name,
            "task": task["name"],
            "session_id": session_id,
            "success": success,
            "elapsed_seconds": round(elapsed, 2),
            "output_length": len(output),
            "output_preview": output[:500] if output else "",
            "tot_nodes_created": node_count,
            "tot_pruned": pruned_count,
            "score_deltas": score_deltas,
            "errors": result.stderr.strip() if result.stderr else "",
        }
        
    except subprocess.TimeoutExpired:
        return {
            "bot": bot_name,
            "task": task["name"],
            "session_id": session_id,
            "success": False,
            "elapsed_seconds": 120,
            "error": "TIMEOUT",
        }
    except Exception as e:
        return {
            "bot": bot_name,
            "task": task["name"],
            "session_id": session_id,
            "success": False,
            "error": str(e),
        }

def run_full_test_suite():
    """Run all tasks through all bots."""
    init_results_dir()
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    results_file = os.path.join(RESULTS_DIR, f"test_run_{timestamp}.json")
    
    all_results = []
    total_tests = len(BOTS) * len(COMPLEX_TASKS)
    completed = 0
    
    print(f"Starting production test suite: {len(BOTS)} bots × {len(COMPLEX_TASKS)} tasks = {total_tests} tests")
    print(f"Results will be saved to: {results_file}")
    print("=" * 80)
    
    for bot in BOTS:
        for task in COMPLEX_TASKS:
            completed += 1
            print(f"[{completed}/{total_tests}] Testing {bot} with {task['name']}...", end=" ", flush=True)
            
            result = run_bot_task(bot, task)
            all_results.append(result)
            
            status = "PASS" if result.get("success") else "FAIL"
            nodes = result.get("tot_nodes_created", 0)
            pruned = result.get("tot_pruned", 0)
            elapsed = result.get("elapsed_seconds", 0)
            
            print(f"{status} ({elapsed}s, {nodes} nodes, {pruned} pruned)")
    
    # Save results
    with open(results_file, "w") as f:
        json.dump(all_results, f, indent=2)
    
    # Print summary
    print("\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)
    
    passed = sum(1 for r in all_results if r.get("success"))
    failed = sum(1 for r in all_results if not r.get("success"))
    total_nodes = sum(r.get("tot_nodes_created", 0) for r in all_results)
    total_pruned = sum(r.get("tot_pruned", 0) for r in all_results)
    
    print(f"Total tests: {total_tests}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    print(f"Total ToT nodes created: {total_nodes}")
    print(f"Total branches pruned: {total_pruned}")
    print(f"Results saved to: {results_file}")
    
    # Per-bot summary
    print("\nPer-bot results:")
    for bot in BOTS:
        bot_results = [r for r in all_results if r["bot"] == bot]
        bot_passed = sum(1 for r in bot_results if r.get("success"))
        bot_nodes = sum(r.get("tot_nodes_created", 0) for r in bot_results)
        print(f"  {bot}: {bot_passed}/{len(bot_results)} passed, {bot_nodes} nodes")
    
    return all_results

if __name__ == "__main__":
    run_full_test_suite()
