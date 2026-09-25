"""Cloud Storage Tools Mixin for mem20 MCP Server.

Provides cloud storage tools with multi-backend support:
- AWS S3 (detailed operations)
- Google Cloud Storage
- Azure Blob Storage
- Cloudflare R2
- DigitalOcean Spaces
- Backblaze B2
- MinIO (self-hosted)
- SFTP/FTPS
- File sync (rclone)
- Multi-cloud sync
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


class CloudStorageToolsMixin:
    """Cloud storage tools for mem20."""

    def register_cloudstorage_tools(self):
        """Register all cloud storage tools."""
        self.tools["cloudstorage_upload"] = mt.Tool(
            name="cloudstorage_upload",
            title="Upload File",
            description="Upload a file to cloud storage (S3, GCS, Azure, R2)",
            inputSchema={
                "type": "object",
                "properties": {
                    "local_path": {"type": "string"},
                    "remote_path": {"type": "string"},
                    "provider": {"type": "string", "enum": ["s3", "gcs", "azure", "r2", "spaces", "b2", "minio"], "default": "s3"},
                    "bucket": {"type": "string"},
                    "make_public": {"type": "boolean", "default": False},
                },
                "required": ["local_path", "remote_path", "bucket"],
            },
        )
        self.tools["cloudstorage_download"] = mt.Tool(
            name="cloudstorage_download",
            title="Download File",
            description="Download a file from cloud storage",
            inputSchema={
                "type": "object",
                "properties": {
                    "remote_path": {"type": "string"},
                    "local_path": {"type": "string"},
                    "provider": {"type": "string", "enum": ["s3", "gcs", "azure", "r2", "spaces", "b2", "minio"], "default": "s3"},
                    "bucket": {"type": "string"},
                },
                "required": ["remote_path", "local_path", "bucket"],
            },
        )
        self.tools["cloudstorage_list"] = mt.Tool(
            name="cloudstorage_list",
            title="List Objects",
            description="List objects in cloud storage bucket",
            inputSchema={
                "type": "object",
                "properties": {
                    "provider": {"type": "string", "enum": ["s3", "gcs", "azure", "r2", "spaces", "b2", "minio"], "default": "s3"},
                    "bucket": {"type": "string"},
                    "prefix": {"type": "string", "default": ""},
                    "limit": {"type": "integer", "default": 100},
                },
                "required": ["bucket"],
            },
        )
        self.tools["cloudstorage_delete"] = mt.Tool(
            name="cloudstorage_delete",
            title="Delete Object",
            description="Delete an object from cloud storage",
            inputSchema={
                "type": "object",
                "properties": {
                    "remote_path": {"type": "string"},
                    "provider": {"type": "string", "enum": ["s3", "gcs", "azure", "r2", "spaces", "b2", "minio"], "default": "s3"},
                    "bucket": {"type": "string"},
                },
                "required": ["remote_path", "bucket"],
            },
        )
        self.tools["cloudstorage_copy"] = mt.Tool(
            name="cloudstorage_copy",
            title="Copy Object",
            description="Copy object between buckets or providers",
            inputSchema={
                "type": "object",
                "properties": {
                    "source_path": {"type": "string"},
                    "dest_path": {"type": "string"},
                    "source_provider": {"type": "string", "enum": ["s3", "gcs", "azure", "r2", "spaces", "b2", "minio"], "default": "s3"},
                    "dest_provider": {"type": "string", "enum": ["s3", "gcs", "azure", "r2", "spaces", "b2", "minio"], "default": "s3"},
                    "source_bucket": {"type": "string"},
                    "dest_bucket": {"type": "string"},
                },
                "required": ["source_path", "dest_path", "source_bucket", "dest_bucket"],
            },
        )
        self.tools["cloudstorage_sync"] = mt.Tool(
            name="cloudstorage_sync",
            title="Sync Directory",
            description="Sync a local directory with cloud storage using rclone",
            inputSchema={
                "type": "object",
                "properties": {
                    "local_dir": {"type": "string"},
                    "remote": {"type": "string"},
                    "direction": {"type": "string", "enum": ["upload", "download", "bidirectional"], "default": "upload"},
                    "dry_run": {"type": "boolean", "default": False},
                },
                "required": ["local_dir", "remote"],
            },
        )
        self.tools["cloudstorage_metadata"] = mt.Tool(
            name="cloudstorage_metadata",
            title="Object Metadata",
            description="Get metadata for a cloud storage object",
            inputSchema={
                "type": "object",
                "properties": {
                    "remote_path": {"type": "string"},
                    "provider": {"type": "string", "enum": ["s3", "gcs", "azure", "r2", "spaces", "b2", "minio"], "default": "s3"},
                    "bucket": {"type": "string"},
                },
                "required": ["remote_path", "bucket"],
            },
        )
        self.tools["cloudstorage_presigned_url"] = mt.Tool(
            name="cloudstorage_presigned_url",
            title="Presigned URL",
            description="Generate a presigned URL for temporary access",
            inputSchema={
                "type": "object",
                "properties": {
                    "remote_path": {"type": "string"},
                    "provider": {"type": "string", "enum": ["s3", "gcs", "azure", "r2", "spaces", "b2"], "default": "s3"},
                    "bucket": {"type": "string"},
                    "expiry_seconds": {"type": "integer", "default": 3600},
                },
                "required": ["remote_path", "bucket"],
            },
        )

    async def _cloudstorage_upload(self, args: Dict) -> str:
        local_path = args.get("local_path", "")
        remote_path = args.get("remote_path", "")
        provider = args.get("provider", "s3")
        bucket = args.get("bucket", "")
        make_public = args.get("make_public", False)
        try:
            if provider == "s3":
                aws_path = shutil.which("aws")
                if not aws_path:
                    return "Error: AWS CLI not found."
                cmd = [aws_path, "s3", "cp", local_path, f"s3://{bucket}/{remote_path}"]
                if make_public:
                    cmd.extend(["--acl", "public-read"])
            elif provider == "gcs":
                gsutil_path = shutil.which("gsutil")
                if not gsutil_path:
                    return "Error: gsutil not found."
                cmd = [gsutil_path, "cp", local_path, f"gs://{bucket}/{remote_path}"]
            elif provider == "azure":
                az_path = shutil.which("az")
                if not az_path:
                    return "Error: Azure CLI not found."
                cmd = [az_path, "storage", "blob", "upload", "--file", local_path, "--name", remote_path, "--container-name", bucket]
            elif provider == "r2":
                # Cloudflare R2 uses S3-compatible API
                aws_path = shutil.which("aws")
                if not aws_path:
                    return "Error: AWS CLI not found."
                account_id = os.environ.get("CF_ACCOUNT_ID", "")
                endpoint = f"https://{account_id}.r2.cloudflarestorage.com"
                cmd = [aws_path, "s3", "cp", local_path, f"s3://{bucket}/{remote_path}", "--endpoint-url", endpoint]
            elif provider == "spaces":
                # DigitalOcean Spaces is S3-compatible
                aws_path = shutil.which("aws")
                if not aws_path:
                    return "Error: AWS CLI not found."
                region = os.environ.get("DO_REGION", "nyc3")
                endpoint = f"https://{region}.digitaloceanspaces.com"
                cmd = [aws_path, "s3", "cp", local_path, f"s3://{bucket}/{remote_path}", "--endpoint-url", endpoint]
            elif provider == "b2":
                b2_path = shutil.which("b2")
                if not b2_path:
                    return "Error: B2 CLI not found."
                cmd = [b2_path, "upload-file", bucket, local_path, remote_path]
            elif provider == "minio":
                mc_path = shutil.which("mc")
                if not mc_path:
                    return "Error: mc (MinIO Client) not found."
                # Assuming alias 'myminio' is configured
                cmd = [mc_path, "cp", local_path, f"myminio/{bucket}/{remote_path}"]
            else:
                return f"Unknown provider: {provider}"
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            if result.returncode == 0:
                return f"File uploaded: {local_path} -> {provider}://{bucket}/{remote_path}"
            return f"Error: {result.stderr}"
        except Exception as e:
            return f"Error: {str(e)}"

    async def _cloudstorage_download(self, args: Dict) -> str:
        remote_path = args.get("remote_path", "")
        local_path = args.get("local_path", "")
        provider = args.get("provider", "s3")
        bucket = args.get("bucket", "")
        try:
            if provider == "s3":
                aws_path = shutil.which("aws")
                if not aws_path:
                    return "Error: AWS CLI not found."
                cmd = [aws_path, "s3", "cp", f"s3://{bucket}/{remote_path}", local_path]
            elif provider == "gcs":
                gsutil_path = shutil.which("gsutil")
                if not gsutil_path:
                    return "Error: gsutil not found."
                cmd = [gsutil_path, "cp", f"gs://{bucket}/{remote_path}", local_path]
            elif provider == "azure":
                az_path = shutil.which("az")
                if not az_path:
                    return "Error: Azure CLI not found."
                cmd = [az_path, "storage", "blob", "download", "--file", local_path, "--name", remote_path, "--container-name", bucket]
            elif provider == "r2":
                aws_path = shutil.which("aws")
                account_id = os.environ.get("CF_ACCOUNT_ID", "")
                endpoint = f"https://{account_id}.r2.cloudflarestorage.com"
                cmd = [aws_path, "s3", "cp", f"s3://{bucket}/{remote_path}", local_path, "--endpoint-url", endpoint]
            elif provider == "spaces":
                aws_path = shutil.which("aws")
                region = os.environ.get("DO_REGION", "nyc3")
                endpoint = f"https://{region}.digitaloceanspaces.com"
                cmd = [aws_path, "s3", "cp", f"s3://{bucket}/{remote_path}", local_path, "--endpoint-url", endpoint]
            elif provider == "b2":
                b2_path = shutil.which("b2")
                if not b2_path:
                    return "Error: B2 CLI not found."
                cmd = [b2_path, "download-file-by-name", bucket, remote_path, local_path]
            elif provider == "minio":
                mc_path = shutil.which("mc")
                if not mc_path:
                    return "Error: mc not found."
                cmd = [mc_path, "cp", f"myminio/{bucket}/{remote_path}", local_path]
            else:
                return f"Unknown provider: {provider}"
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            if result.returncode == 0:
                return f"File downloaded: {provider}://{bucket}/{remote_path} -> {local_path}"
            return f"Error: {result.stderr}"
        except Exception as e:
            return f"Error: {str(e)}"

    async def _cloudstorage_list(self, args: Dict) -> str:
        provider = args.get("provider", "s3")
        bucket = args.get("bucket", "")
        prefix = args.get("prefix", "")
        limit = args.get("limit", 100)
        try:
            if provider == "s3":
                aws_path = shutil.which("aws")
                if not aws_path:
                    return "Error: AWS CLI not found."
                cmd = [aws_path, "s3", "ls", f"s3://{bucket}/{prefix}", "--recursive", "--human-readable"]
            elif provider == "gcs":
                gsutil_path = shutil.which("gsutil")
                if not gsutil_path:
                    return "Error: gsutil not found."
                cmd = [gsutil_path, "ls", "-l", f"gs://{bucket}/{prefix}"]
            elif provider == "azure":
                az_path = shutil.which("az")
                if not az_path:
                    return "Error: Azure CLI not found."
                cmd = [az_path, "storage", "blob", "list", "--container-name", bucket, "--prefix", prefix]
            elif provider == "r2":
                aws_path = shutil.which("aws")
                account_id = os.environ.get("CF_ACCOUNT_ID", "")
                endpoint = f"https://{account_id}.r2.cloudflarestorage.com"
                cmd = [aws_path, "s3", "ls", f"s3://{bucket}/{prefix}", "--endpoint-url", endpoint]
            elif provider == "spaces":
                aws_path = shutil.which("aws")
                region = os.environ.get("DO_REGION", "nyc3")
                endpoint = f"https://{region}.digitaloceanspaces.com"
                cmd = [aws_path, "s3", "ls", f"s3://{bucket}/{prefix}", "--endpoint-url", endpoint]
            elif provider == "b2":
                b2_path = shutil.which("b2")
                if not b2_path:
                    return "Error: B2 CLI not found."
                cmd = [b2_path, "ls", f"b2://{bucket}/{prefix}"]
            elif provider == "minio":
                mc_path = shutil.which("mc")
                if not mc_path:
                    return "Error: mc not found."
                cmd = [mc_path, "ls", f"myminio/{bucket}/{prefix}"]
            else:
                return f"Unknown provider: {provider}"
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode == 0:
                return f"Objects ({provider}://{bucket}/{prefix}):\n{result.stdout[:2000]}"
            return f"Error: {result.stderr}"
        except Exception as e:
            return f"Error: {str(e)}"

    async def _cloudstorage_delete(self, args: Dict) -> str:
        remote_path = args.get("remote_path", "")
        provider = args.get("provider", "s3")
        bucket = args.get("bucket", "")
        try:
            if provider == "s3":
                aws_path = shutil.which("aws")
                if not aws_path:
                    return "Error: AWS CLI not found."
                cmd = [aws_path, "s3", "rm", f"s3://{bucket}/{remote_path}"]
            elif provider == "gcs":
                gsutil_path = shutil.which("gsutil")
                if not gsutil_path:
                    return "Error: gsutil not found."
                cmd = [gsutil_path, "rm", f"gs://{bucket}/{remote_path}"]
            elif provider == "azure":
                az_path = shutil.which("az")
                if not az_path:
                    return "Error: Azure CLI not found."
                cmd = [az_path, "storage", "blob", "delete", "--container-name", bucket, "--name", remote_path]
            elif provider == "r2":
                aws_path = shutil.which("aws")
                account_id = os.environ.get("CF_ACCOUNT_ID", "")
                endpoint = f"https://{account_id}.r2.cloudflarestorage.com"
                cmd = [aws_path, "s3", "rm", f"s3://{bucket}/{remote_path}", "--endpoint-url", endpoint]
            elif provider == "spaces":
                aws_path = shutil.which("aws")
                region = os.environ.get("DO_REGION", "nyc3")
                endpoint = f"https://{region}.digitaloceanspaces.com"
                cmd = [aws_path, "s3", "rm", f"s3://{bucket}/{remote_path}", "--endpoint-url", endpoint]
            elif provider == "b2":
                b2_path = shutil.which("b2")
                if not b2_path:
                    return "Error: B2 CLI not found."
                cmd = [b2_path, "delete-file-version", remote_path, bucket]
            elif provider == "minio":
                mc_path = shutil.which("mc")
                if not mc_path:
                    return "Error: mc not found."
                cmd = [mc_path, "rm", f"myminio/{bucket}/{remote_path}"]
            else:
                return f"Unknown provider: {provider}"
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode == 0:
                return f"Deleted: {provider}://{bucket}/{remote_path}"
            return f"Error: {result.stderr}"
        except Exception as e:
            return f"Error: {str(e)}"

    async def _cloudstorage_copy(self, args: Dict) -> str:
        source_path = args.get("source_path", "")
        dest_path = args.get("dest_path", "")
        source_provider = args.get("source_provider", "s3")
        dest_provider = args.get("dest_provider", "s3")
        source_bucket = args.get("source_bucket", "")
        dest_bucket = args.get("dest_bucket", "")
        try:
            # Download from source to temp, then upload to dest
            with tempfile.NamedTemporaryFile(delete=False) as tmp:
                tmp_path = tmp.name
            # Download
            download_args = {
                "remote_path": source_path,
                "local_path": tmp_path,
                "provider": source_provider,
                "bucket": source_bucket,
            }
            result = await self._cloudstorage_download(download_args)
            if "Error" in result and "not found" not in result.lower():
                return f"Copy failed at download: {result}"
            # Upload
            upload_args = {
                "local_path": tmp_path,
                "remote_path": dest_path,
                "provider": dest_provider,
                "bucket": dest_bucket,
            }
            result = await self._cloudstorage_upload(upload_args)
            os.unlink(tmp_path)
            if "Error" in result and "not found" not in result.lower():
                return f"Copy failed at upload: {result}"
            return f"Copied: {source_provider}://{source_bucket}/{source_path} -> {dest_provider}://{dest_bucket}/{dest_path}"
        except Exception as e:
            return f"Error: {str(e)}"

    async def _cloudstorage_sync(self, args: Dict) -> str:
        local_dir = args.get("local_dir", "")
        remote = args.get("remote", "")
        direction = args.get("direction", "upload")
        dry_run = args.get("dry_run", False)
        try:
            rclone_path = shutil.which("rclone")
            if not rclone_path:
                return "Error: rclone not found."
            if direction == "upload":
                cmd = [rclone_path, "sync", local_dir, remote]
            elif direction == "download":
                cmd = [rclone_path, "sync", remote, local_dir]
            elif direction == "bidirectional":
                cmd = [rclone_path, "bisync", local_dir, remote]
            else:
                return f"Unknown direction: {direction}"
            if dry_run:
                cmd.append("--dry-run")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            if result.returncode == 0:
                return f"Sync complete: {result.stdout[:2000]}"
            return f"Error: {result.stderr}"
        except Exception as e:
            return f"Error: {str(e)}"

    async def _cloudstorage_metadata(self, args: Dict) -> str:
        remote_path = args.get("remote_path", "")
        provider = args.get("provider", "s3")
        bucket = args.get("bucket", "")
        try:
            if provider == "s3":
                aws_path = shutil.which("aws")
                if not aws_path:
                    return "Error: AWS CLI not found."
                cmd = [aws_path, "s3api", "head-object", "--bucket", bucket, "--key", remote_path]
            elif provider == "gcs":
                gsutil_path = shutil.which("gsutil")
                if not gsutil_path:
                    return "Error: gsutil not found."
                cmd = [gsutil_path, "stat", f"gs://{bucket}/{remote_path}"]
            elif provider == "azure":
                az_path = shutil.which("az")
                if not az_path:
                    return "Error: Azure CLI not found."
                cmd = [az_path, "storage", "blob", "show", "--container-name", bucket, "--name", remote_path]
            elif provider == "r2":
                aws_path = shutil.which("aws")
                account_id = os.environ.get("CF_ACCOUNT_ID", "")
                endpoint = f"https://{account_id}.r2.cloudflarestorage.com"
                cmd = [aws_path, "s3api", "head-object", "--bucket", bucket, "--key", remote_path, "--endpoint-url", endpoint]
            elif provider == "spaces":
                aws_path = shutil.which("aws")
                region = os.environ.get("DO_REGION", "nyc3")
                endpoint = f"https://{region}.digitaloceanspaces.com"
                cmd = [aws_path, "s3api", "head-object", "--bucket", bucket, "--key", remote_path, "--endpoint-url", endpoint]
            elif provider == "b2":
                b2_path = shutil.which("b2")
                if not b2_path:
                    return "Error: B2 CLI not found."
                cmd = [b2_path, "file-info", f"b2://{bucket}/{remote_path}"]
            elif provider == "minio":
                mc_path = shutil.which("mc")
                if not mc_path:
                    return "Error: mc not found."
                cmd = [mc_path, "stat", f"myminio/{bucket}/{remote_path}"]
            else:
                return f"Unknown provider: {provider}"
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode == 0:
                return f"Metadata ({provider}://{bucket}/{remote_path}):\n{result.stdout[:2000]}"
            return f"Error: {result.stderr}"
        except Exception as e:
            return f"Error: {str(e)}"

    async def _cloudstorage_presigned_url(self, args: Dict) -> str:
        remote_path = args.get("remote_path", "")
        provider = args.get("provider", "s3")
        bucket = args.get("bucket", "")
        expiry_seconds = args.get("expiry_seconds", 3600)
        try:
            if provider == "s3":
                aws_path = shutil.which("aws")
                if not aws_path:
                    return "Error: AWS CLI not found."
                cmd = [aws_path, "s3", "presign", f"s3://{bucket}/{remote_path}", "--expires-in", str(expiry_seconds)]
            elif provider == "gcs":
                gsutil_path = shutil.which("gsutil")
                if not gsutil_path:
                    return "Error: gsutil not found."
                cmd = [gsutil_path, "signurl", "-d", f"{expiry_seconds}s", f"gs://{bucket}/{remote_path}"]
            elif provider == "azure":
                az_path = shutil.which("az")
                if not az_path:
                    return "Error: Azure CLI not found."
                cmd = [az_path, "storage", "blob", "generate-sas", "--container-name", bucket, "--name", remote_path, "--permissions", "r", "--expiry", f"+{expiry_seconds}s"]
            elif provider == "r2":
                aws_path = shutil.which("aws")
                account_id = os.environ.get("CF_ACCOUNT_ID", "")
                endpoint = f"https://{account_id}.r2.cloudflarestorage.com"
                cmd = [aws_path, "s3", "presign", f"s3://{bucket}/{remote_path}", "--expires-in", str(expiry_seconds), "--endpoint-url", endpoint]
            elif provider == "spaces":
                aws_path = shutil.which("aws")
                region = os.environ.get("DO_REGION", "nyc3")
                endpoint = f"https://{region}.digitaloceanspaces.com"
                cmd = [aws_path, "s3", "presign", f"s3://{bucket}/{remote_path}", "--expires-in", str(expiry_seconds), "--endpoint-url", endpoint]
            elif provider == "b2":
                b2_path = shutil.which("b2")
                if not b2_path:
                    return "Error: B2 CLI not found."
                cmd = [b2_path, "get-download-url", "--duration", str(expiry_seconds), f"b2://{bucket}/{remote_path}"]
            else:
                return f"Unknown provider: {provider}"
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode == 0:
                return f"Presigned URL ({expiry_seconds}s):\n{result.stdout}"
            return f"Error: {result.stderr}"
        except Exception as e:
            return f"Error: {str(e)}"