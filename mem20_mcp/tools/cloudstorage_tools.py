"""
Cloud Storage Tools Mixin for mem20 MCP Server

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
import mcp_types as mt


import os
import sys
import json
import subprocess
import asyncio
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional



class CloudStorageToolsMixin:
    """Cloud storage tools for mem20."""

    def register_cloudstorage_tools(self):
        """Register all cloud storage tools."""
        self.tools["cloudstorage_upload"] = mt.Tool(
            name="cloudstorage_upload",
            title="Upload File",
            description="Upload a file to cloud storage (S3, GCS, Azure, R2)",
            input_schema={
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
            input_schema={
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
            input_schema={
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
            input_schema={
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
            input_schema={
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
            input_schema={
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
            input_schema={
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
            input_schema={
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
