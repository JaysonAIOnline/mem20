"""Cloud Service Tools Mixin for mem20 MCP Server.

Provides cloud service tools with multi-backend support:
- AWS (S3, EC2, Lambda, RDS, CloudWatch)
- Google Cloud (Compute, Storage, Functions, BigQuery)
- Azure (Blob, Functions, SQL, Monitor)
- DigitalOcean (Droplets, Spaces, Databases)
- Cloudflare (Workers, R2, DNS, Pages)
- Heroku
- Vercel
- Netlify
- Kubernetes (kubectl)
- Docker Hub
"""

import json
import os
import shutil
import subprocess
import tempfile

from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from mcp.server import Server
    from mcp.server.lowlevel.server import ServerRequestContext
    import mcp_types as mt
except ImportError:
    print("Error: mcp package not installed. Please install with: pip install mcp")
    raise


class CloudServiceToolsMixin:
    """Cloud service tools for mem20."""

    def register_cloudservice_tools(self):
        """Register all cloud service tools."""
        self.tools["cloud_aws_s3"] = mt.Tool(
            name="cloud_aws_s3",
            title="AWS S3 Operations",
            description="Upload, download, list S3 objects",
            inputSchema={
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["upload", "download", "list", "delete"], "default": "list"},
                    "bucket": {"type": "string"},
                    "key": {"type": "string", "default": ""},
                    "local_path": {"type": "string", "default": ""},
                    "region": {"type": "string", "default": "us-east-1"},
                },
                "required": ["bucket"],
            },
        )
        self.tools["cloud_aws_ec2"] = mt.Tool(
            name="cloud_aws_ec2",
            title="AWS EC2 Operations",
            description="Manage EC2 instances",
            inputSchema={
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["list", "start", "stop", "terminate", "describe"], "default": "list"},
                    "instance_id": {"type": "string", "default": ""},
                    "region": {"type": "string", "default": "us-east-1"},
                },
                "required": [],
            },
        )
        self.tools["cloud_aws_lambda"] = mt.Tool(
            name="cloud_aws_lambda",
            title="AWS Lambda Operations",
            description="Invoke or list Lambda functions",
            inputSchema={
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["invoke", "list", "get"], "default": "list"},
                    "function_name": {"type": "string", "default": ""},
                    "payload": {"type": "string", "default": "{}"},
                    "region": {"type": "string", "default": "us-east-1"},
                },
                "required": [],
            },
        )
        self.tools["cloud_gcp_storage"] = mt.Tool(
            name="cloud_gcp_storage",
            title="GCP Cloud Storage",
            description="Upload, download, list GCS objects",
            inputSchema={
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["upload", "download", "list", "delete"], "default": "list"},
                    "bucket": {"type": "string"},
                    "blob_name": {"type": "string", "default": ""},
                    "local_path": {"type": "string", "default": ""},
                },
                "required": ["bucket"],
            },
        )
        self.tools["cloud_azure_blob"] = mt.Tool(
            name="cloud_azure_blob",
            title="Azure Blob Storage",
            description="Upload, download, list Azure blobs",
            inputSchema={
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["upload", "download", "list", "delete"], "default": "list"},
                    "container": {"type": "string"},
                    "blob_name": {"type": "string", "default": ""},
                    "local_path": {"type": "string", "default": ""},
                },
                "required": ["container"],
            },
        )
        self.tools["cloud_digitalocean_droplet"] = mt.Tool(
            name="cloud_digitalocean_droplet",
            title="DigitalOcean Droplet",
            description="Manage DigitalOcean Droplets",
            inputSchema={
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["list", "create", "delete", "reboot", "shutdown"], "default": "list"},
                    "droplet_id": {"type": "string", "default": ""},
                    "name": {"type": "string", "default": ""},
                    "size": {"type": "string", "default": "s-1vcpu-1gb"},
                    "region": {"type": "string", "default": "nyc1"},
                    "image": {"type": "string", "default": "ubuntu-22-04-x64"},
                },
                "required": [],
            },
        )
        self.tools["cloud_cloudflare_worker"] = mt.Tool(
            name="cloud_cloudflare_worker",
            title="Cloudflare Workers",
            description="Deploy and manage Cloudflare Workers",
            inputSchema={
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["deploy", "list", "delete", "tail"], "default": "list"},
                    "script_name": {"type": "string", "default": ""},
                    "script_path": {"type": "string", "default": ""},
                },
                "required": [],
            },
        )
        self.tools["cloud_k8s"] = mt.Tool(
            name="cloud_k8s",
            title="Kubernetes Operations",
            description="Manage Kubernetes resources",
            inputSchema={
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["get", "describe", "logs", "apply", "delete"], "default": "get"},
                    "resource": {"type": "string", "default": "pods"},
                    "namespace": {"type": "string", "default": "default"},
                    "name": {"type": "string", "default": ""},
                    "manifest": {"type": "string", "default": ""},
                },
                "required": [],
            },
        )
        self.tools["cloud_docker"] = mt.Tool(
            name="cloud_docker",
            title="Docker Operations",
            description="Manage Docker containers and images",
            inputSchema={
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["ps", "images", "run", "stop", "rm", "logs", "build", "pull", "push"], "default": "ps"},
                    "container": {"type": "string", "default": ""},
                    "image": {"type": "string", "default": ""},
                    "dockerfile": {"type": "string", "default": ""},
                    "ports": {"type": "string", "default": ""},
                    "env": {"type": "string", "default": ""},
                },
                "required": [],
            },
        )
        self.tools["cloud_heroku"] = mt.Tool(
            name="cloud_heroku",
            title="Heroku Operations",
            description="Manage Heroku apps",
            inputSchema={
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["list", "create", "deploy", "logs", "config", "destroy"], "default": "list"},
                    "app_name": {"type": "string", "default": ""},
                    "config_vars": {"type": "string", "default": "{}"},
                },
                "required": [],
            },
        )

    async def _cloud_aws_s3(self, args: Dict) -> str:
        action = args.get("action", "list")
        bucket = args.get("bucket", "")
        key = args.get("key", "")
        local_path = args.get("local_path", "")
        region = args.get("region", "us-east-1")
        try:
            aws_path = shutil.which("aws")
            if not aws_path:
                return "Error: AWS CLI not found."
            if action == "list":
                cmd = [aws_path, "s3", "ls", f"s3://{bucket}", "--region", region]
            elif action == "upload":
                cmd = [aws_path, "s3", "cp", local_path, f"s3://{bucket}/{key}", "--region", region]
            elif action == "download":
                cmd = [aws_path, "s3", "cp", f"s3://{bucket}/{key}", local_path, "--region", region]
            elif action == "delete":
                cmd = [aws_path, "s3", "rm", f"s3://{bucket}/{key}", "--region", region]
            else:
                return f"Unknown action: {action}"
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode == 0:
                return f"S3 {action}: {result.stdout}"
            return f"Error: {result.stderr}"
        except Exception as e:
            return f"Error: {str(e)}"

    async def _cloud_aws_ec2(self, args: Dict) -> str:
        action = args.get("action", "list")
        instance_id = args.get("instance_id", "")
        region = args.get("region", "us-east-1")
        try:
            aws_path = shutil.which("aws")
            if not aws_path:
                return "Error: AWS CLI not found."
            if action == "list":
                cmd = [aws_path, "ec2", "describe-instances", "--region", region]
            elif action == "start":
                cmd = [aws_path, "ec2", "start-instances", "--instance-ids", instance_id, "--region", region]
            elif action == "stop":
                cmd = [aws_path, "ec2", "stop-instances", "--instance-ids", instance_id, "--region", region]
            elif action == "terminate":
                cmd = [aws_path, "ec2", "terminate-instances", "--instance-ids", instance_id, "--region", region]
            elif action == "describe":
                cmd = [aws_path, "ec2", "describe-instances", "--instance-ids", instance_id, "--region", region]
            else:
                return f"Unknown action: {action}"
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode == 0:
                return f"EC2 {action}: {result.stdout[:2000]}"
            return f"Error: {result.stderr}"
        except Exception as e:
            return f"Error: {str(e)}"

    async def _cloud_aws_lambda(self, args: Dict) -> str:
        action = args.get("action", "list")
        function_name = args.get("function_name", "")
        payload = args.get("payload", "{}")
        region = args.get("region", "us-east-1")
        try:
            aws_path = shutil.which("aws")
            if not aws_path:
                return "Error: AWS CLI not found."
            if action == "list":
                cmd = [aws_path, "lambda", "list-functions", "--region", region]
            elif action == "invoke":
                cmd = [aws_path, "lambda", "invoke", "--function-name", function_name, "--payload", payload, "/tmp/lambda_output.json", "--region", region]
            elif action == "get":
                cmd = [aws_path, "lambda", "get-function", "--function-name", function_name, "--region", region]
            else:
                return f"Unknown action: {action}"
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode == 0:
                return f"Lambda {action}: {result.stdout[:2000]}"
            return f"Error: {result.stderr}"
        except Exception as e:
            return f"Error: {str(e)}"

    async def _cloud_gcp_storage(self, args: Dict) -> str:
        action = args.get("action", "list")
        bucket = args.get("bucket", "")
        blob_name = args.get("blob_name", "")
        local_path = args.get("local_path", "")
        try:
            gsutil_path = shutil.which("gsutil")
            if not gsutil_path:
                return "Error: gsutil not found."
            if action == "list":
                cmd = [gsutil_path, "ls", f"gs://{bucket}"]
            elif action == "upload":
                cmd = [gsutil_path, "cp", local_path, f"gs://{bucket}/{blob_name}"]
            elif action == "download":
                cmd = [gsutil_path, "cp", f"gs://{bucket}/{blob_name}", local_path]
            elif action == "delete":
                cmd = [gsutil_path, "rm", f"gs://{bucket}/{blob_name}"]
            else:
                return f"Unknown action: {action}"
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode == 0:
                return f"GCS {action}: {result.stdout}"
            return f"Error: {result.stderr}"
        except Exception as e:
            return f"Error: {str(e)}"

    async def _cloud_azure_blob(self, args: Dict) -> str:
        action = args.get("action", "list")
        container = args.get("container", "")
        blob_name = args.get("blob_name", "")
        local_path = args.get("local_path", "")
        try:
            az_path = shutil.which("az")
            if not az_path:
                return "Error: Azure CLI not found."
            if action == "list":
                cmd = [az_path, "storage", "blob", "list", "--container-name", container]
            elif action == "upload":
                cmd = [az_path, "storage", "blob", "upload", "--container-name", container, "--file", local_path, "--name", blob_name]
            elif action == "download":
                cmd = [az_path, "storage", "blob", "download", "--container-name", container, "--file", local_path, "--name", blob_name]
            elif action == "delete":
                cmd = [az_path, "storage", "blob", "delete", "--container-name", container, "--name", blob_name]
            else:
                return f"Unknown action: {action}"
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode == 0:
                return f"Azure Blob {action}: {result.stdout[:2000]}"
            return f"Error: {result.stderr}"
        except Exception as e:
            return f"Error: {str(e)}"

    async def _cloud_digitalocean_droplet(self, args: Dict) -> str:
        action = args.get("action", "list")
        droplet_id = args.get("droplet_id", "")
        name = args.get("name", "")
        size = args.get("size", "s-1vcpu-1gb")
        region = args.get("region", "nyc1")
        image = args.get("image", "ubuntu-22-04-x64")
        try:
            doctl_path = shutil.which("doctl")
            if not doctl_path:
                return "Error: doctl not found."
            if action == "list":
                cmd = [doctl_path, "compute", "droplet", "list"]
            elif action == "create":
                cmd = [doctl_path, "compute", "droplet", "create", name, "--size", size, "--region", region, "--image", image, "--wait"]
            elif action == "delete":
                cmd = [doctl_path, "compute", "droplet", "delete", droplet_id, "--force"]
            elif action == "reboot":
                cmd = [doctl_path, "compute", "droplet-action", "reboot", droplet_id]
            elif action == "shutdown":
                cmd = [doctl_path, "compute", "droplet-action", "shutdown", droplet_id]
            else:
                return f"Unknown action: {action}"
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            if result.returncode == 0:
                return f"DO Droplet {action}: {result.stdout[:2000]}"
            return f"Error: {result.stderr}"
        except Exception as e:
            return f"Error: {str(e)}"

    async def _cloud_cloudflare_worker(self, args: Dict) -> str:
        action = args.get("action", "list")
        script_name = args.get("script_name", "")
        script_path = args.get("script_path", "")
        try:
            wrangler_path = shutil.which("wrangler") or shutil.which("npx")
            if not wrangler_path:
                return "Error: wrangler not found."
            if action == "list":
                cmd = [wrangler_path, "deployments", "list"] if wrangler_path != "npx" else ["npx", "wrangler", "deployments", "list"]
            elif action == "deploy":
                cmd = [wrangler_path, "deploy", script_path, "--name", script_name] if wrangler_path != "npx" else ["npx", "wrangler", "deploy", script_path, "--name", script_name]
            elif action == "delete":
                cmd = [wrangler_path, "delete", "--name", script_name] if wrangler_path != "npx" else ["npx", "wrangler", "delete", "--name", script_name]
            elif action == "tail":
                cmd = [wrangler_path, "tail", "--name", script_name] if wrangler_path != "npx" else ["npx", "wrangler", "tail", "--name", script_name]
            else:
                return f"Unknown action: {action}"
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            if result.returncode == 0:
                return f"Worker {action}: {result.stdout[:2000]}"
            return f"Error: {result.stderr}"
        except Exception as e:
            return f"Error: {str(e)}"

    async def _cloud_k8s(self, args: Dict) -> str:
        action = args.get("action", "get")
        resource = args.get("resource", "pods")
        namespace = args.get("namespace", "default")
        name = args.get("name", "")
        manifest = args.get("manifest", "")
        try:
            kubectl_path = shutil.which("kubectl")
            if not kubectl_path:
                return "Error: kubectl not found."
            if action == "get":
                cmd = [kubectl_path, "get", resource, "-n", namespace]
                if name:
                    cmd.append(name)
            elif action == "describe":
                cmd = [kubectl_path, "describe", resource, name, "-n", namespace]
            elif action == "logs":
                cmd = [kubectl_path, "logs", name, "-n", namespace]
            elif action == "apply":
                with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
                    f.write(manifest)
                    manifest_path = f.name
                cmd = [kubectl_path, "apply", "-f", manifest_path, "-n", namespace]
            elif action == "delete":
                cmd = [kubectl_path, "delete", resource, name, "-n", namespace]
            else:
                return f"Unknown action: {action}"
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode == 0:
                return f"K8s {action}: {result.stdout[:2000]}"
            return f"Error: {result.stderr}"
        except Exception as e:
            return f"Error: {str(e)}"

    async def _cloud_docker(self, args: Dict) -> str:
        action = args.get("action", "ps")
        container = args.get("container", "")
        image = args.get("image", "")
        dockerfile = args.get("dockerfile", "")
        ports = args.get("ports", "")
        env = args.get("env", "")
        try:
            docker_path = shutil.which("docker")
            if not docker_path:
                return "Error: docker not found."
            if action == "ps":
                cmd = [docker_path, "ps", "-a"]
            elif action == "images":
                cmd = [docker_path, "images"]
            elif action == "run":
                cmd = [docker_path, "run", "-d"]
                if ports:
                    cmd.extend(["-p", ports])
                if env:
                    for e in env.split(","):
                        cmd.extend(["-e", e])
                cmd.append(image)
            elif action == "stop":
                cmd = [docker_path, "stop", container]
            elif action == "rm":
                cmd = [docker_path, "rm", container]
            elif action == "logs":
                cmd = [docker_path, "logs", container]
            elif action == "build":
                cmd = [docker_path, "build", "-t", image, "-f", dockerfile, "."]
            elif action == "pull":
                cmd = [docker_path, "pull", image]
            elif action == "push":
                cmd = [docker_path, "push", image]
            else:
                return f"Unknown action: {action}"
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            if result.returncode == 0:
                return f"Docker {action}: {result.stdout[:2000]}"
            return f"Error: {result.stderr}"
        except Exception as e:
            return f"Error: {str(e)}"

    async def _cloud_heroku(self, args: Dict) -> str:
        action = args.get("action", "list")
        app_name = args.get("app_name", "")
        config_vars = json.loads(args.get("config_vars", "{}"))
        try:
            heroku_path = shutil.which("heroku")
            if not heroku_path:
                return "Error: heroku CLI not found."
            if action == "list":
                cmd = [heroku_path, "apps"]
            elif action == "create":
                cmd = [heroku_path, "create", app_name]
            elif action == "deploy":
                cmd = ["git", "push", f"https://git.heroku.com/{app_name}.git", "main"]
            elif action == "logs":
                cmd = [heroku_path, "logs", "--app", app_name, "--tail"]
            elif action == "config":
                cmd = [heroku_path, "config", "--app", app_name]
                for k, v in config_vars.items():
                    cmd.extend(["-e", f"{k}={v}"])
            elif action == "destroy":
                cmd = [heroku_path, "destroy", "--app", app_name, "--confirm", app_name]
            else:
                return f"Unknown action: {action}"
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            if result.returncode == 0:
                return f"Heroku {action}: {result.stdout[:2000]}"
            return f"Error: {result.stderr}"
        except Exception as e:
            return f"Error: {str(e)}"