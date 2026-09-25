import json, sys
payload=json.loads(sys.stdin.read() or "{}")
if payload.get("__malformed__"):
    print("malformed request",file=sys.stderr); raise SystemExit(2)
print(json.dumps({"message":f"Hello, {payload.get('name','FreeStack')}!","microapp":"hello_py"}))
