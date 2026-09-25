#!/usr/bin/env python3
"""
Jayson Bridge — Usage Summary
Prints a clean per-model request / token summary from the LiteLLM SQLite DB.
"""

import sqlite3
import sys
from pathlib import Path
from collections import defaultdict

DB_CANDIDATES = [
    Path("/app/bridge_usage.db"),
    Path("./bridge_usage.db"),
    Path("/app/litellm.db"),
    Path("./litellm.db"),
]


def find_db():
    for p in DB_CANDIDATES:
        if p.exists():
            return p
    return None


def main():
    db_path = find_db()
    if not db_path:
        print("No usage database found.")
        print("Looked for:", ", ".join(str(p) for p in DB_CANDIDATES))
        print("\nMake sure the bridge has received at least one request.")
        sys.exit(1)

    print(f"Reading: {db_path}\n")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Discover tables
    tables = [r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    print("Tables found:", ", ".join(tables) or "(none)")
    print("-" * 60)

    # Try the most common LiteLLM spend log table
    spend_table = None
    for candidate in ["LiteLLM_SpendLogs", "spendlogs", "SpendLogs", "liteLLM_spendlogs"]:
        if candidate in tables:
            spend_table = candidate
            break

    if not spend_table:
        print("No spend/request log table found yet.")
        print("Send a few requests through the bridge, then run this again.")
        conn.close()
        sys.exit(0)

    # Get column names
    cols = [r[1] for r in cur.execute(f"PRAGMA table_info({spend_table})").fetchall()]
    print(f"Using table: {spend_table}")
    print(f"Columns: {', '.join(cols)}\n")

    # Flexible aggregation
    model_col = next((c for c in cols if c.lower() in ("model", "model_id", "model_group")), None)
    tokens_col = next((c for c in cols if "total_token" in c.lower() or c.lower() == "total_tokens"), None)
    spend_col = next((c for c in cols if c.lower() in ("spend", "cost", "response_cost")), None)

    if not model_col:
        print("Could not find a model column. Showing last 10 rows instead:\n")
        rows = cur.execute(f"SELECT * FROM {spend_table} ORDER BY rowid DESC LIMIT 10").fetchall()
        for r in rows:
            print(dict(r))
        conn.close()
        return

    # Aggregate
    query = f"SELECT {model_col} as model, COUNT(*) as requests"
    if tokens_col:
        query += f", SUM({tokens_col}) as total_tokens"
    if spend_col:
        query += f", SUM({spend_col}) as total_spend"
    query += f" FROM {spend_table} GROUP BY {model_col} ORDER BY requests DESC"

    rows = cur.execute(query).fetchall()

    if not rows:
        print("No requests logged yet.")
        conn.close()
        return

    print(f"{'Model':<45} {'Requests':>10}", end="")
    if tokens_col:
        print(f" {'Tokens':>12}", end="")
    if spend_col:
        print(f" {'Spend':>10}", end="")
    print()
    print("-" * 80)

    total_req = 0
    for r in rows:
        model = r["model"] or "unknown"
        reqs = r["requests"] or 0
        total_req += reqs
        line = f"{model:<45} {reqs:>10}"
        if tokens_col:
            line += f" {r['total_tokens'] or 0:>12}"
        if spend_col:
            spend = r["total_spend"] or 0
            line += f" {spend:>10.4f}"
        print(line)

    print("-" * 80)
    print(f"{'TOTAL':<45} {total_req:>10}")
    print()

    conn.close()


if __name__ == "__main__":
    main()
