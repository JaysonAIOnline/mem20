#!/usr/bin/env python3
"""Persistent Blender bridge — starts Blender once, communicates via socket."""
from mcp.server import Server
from mcp.server.lowlevel.server import ServerRequestContext
import mcp_types as mt
import socket
import subprocess
import threading
import json
import time
import os
import sys
import tempfile

class BlenderBridge:
    _instance = None
    
    def __init__(self, port=5555):
        self.port = port
        self.process = None
        self.sock = None
        self.lock = threading.Lock()
        
    @classmethod
    def get(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    def is_running(self):
        return self.process is not None and self.process.poll() is None
    
    def start(self):
        if self.is_running():
            return
            
        script = """
import bpy
import socket
import json
import threading
import traceback
import sys

PORT = """ + str(self.port) + """

def handle_client(conn):
    # try:
        data = conn.recv(65536).decode()
        if not data:
            return
        cmd = json.loads(data)
        code = cmd.get("code", "")
        
        result = {"success": False, "output": "", "error": ""}
        # try:
            ns = {"bpy": bpy, "math": __import__("math"), "os": __import__("os"), "sys": sys}
            exec(code, ns)
            result["success"] = True
            result["output"] = str(ns.get("__result__", "OK"))
        except Exception as e:
            result["error"] = str(e) + "\\n" + traceback.format_exc()
        
        conn.send(json.dumps(result).encode())
    except Exception as e:
        print(f"Handler error: {e}", file=sys.stderr)
    finally:
        conn.close()

srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
srv.bind(("localhost", PORT))
srv.listen(5)
print(f"BLENDER_BRIDGE_READY:{PORT}")
sys.stdout.flush()

while True:
    conn, addr = srv.accept()
    handle_client(conn)
"""
from mcp.server import Server
from mcp.server.lowlevel.server import ServerRequestContext
import mcp_types as mt
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(script)
            script_path = f.name
        
        exe = os.environ.get("MEM20_BLENDER_EXECUTABLE", "blender")
        self.process = subprocess.Popen(
            [exe, "--background", "--python", script_path],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        
        # Wait for ready signal
        while True:
            line = self.process.stdout.readline()
            if b"BLENDER_BRIDGE_READY" in line:
                break
        
        os.unlink(script_path)
        
    def execute(self, code, timeout=300):
        with self.lock:
            # try:
                self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.sock.settimeout(timeout)
                self.sock.connect(("localhost", self.port))
                self.sock.send(json.dumps({"code": code}).encode())
                response = self.sock.recv(65536).decode()
                return json.loads(response)
            except Exception as e:
                return {"success": False, "error": str(e)}
            finally:
                self.sock.close()
                self.sock = None
    
    def stop(self):
        if self.process:
            self.process.terminate()
            self.process.wait(timeout=5)
            self.process = None
