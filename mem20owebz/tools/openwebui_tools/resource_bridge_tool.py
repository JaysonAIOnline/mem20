"""
title: Resource Bridge
author: Jayson
version: 1.0
description: Catalog multi-cloud storage backends (hot disk, R2 releases, backups). Does not merge disks.
"""

from pydantic import BaseModel, Field
from typing import Optional
import json


class Tools:
    class Valves(BaseModel):
        config_note: str = Field(
            default="resource_bridge/config.yaml",
            description="Path to backend config (documentation/runtime later)",
        )

    def __init__(self):
        self.valves = self.Valves()

    def storage_plan(self, project_name: str, artifact_kind: str = "release") -> str:
        """
        Suggest where an artifact should live.
        :param project_name: Game/project id
        :param artifact_kind: release | backup | hot_project | package
        """
        mapping = {
            "release": "jayson://releases/{p}/",
            "backup": "jayson://backups/{p}/",
            "hot_project": "jayson://hot/projects/{p}/",
            "package": "jayson://hot/projects/{p}/PRODUCTION_PACKAGE.md",
        }
        kind = artifact_kind if artifact_kind in mapping else "backup"
        return json.dumps({
            "project": project_name,
            "kind": kind,
            "uri": mapping[kind].format(p=project_name),
            "rule": "Object stores for portable artifacts. Hot block only for engine/project files. Never DDC on R2.",
        }, indent=2)

    def storage_backends(self) -> str:
        """List logical backends from the 2.0-beta1 config contract."""
        return json.dumps({
            "hot": "local/SSH filesystem on the build VM",
            "releases": "Cloudflare R2 (free egress)",
            "backups": "second-cloud S3-compatible",
            "status": "catalog only until 3.0 FastAPI service",
        }, indent=2)
