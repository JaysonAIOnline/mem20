"""Hermetic tests for mem20officez — no network, no real keys."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from mem20officez.config import OfficeConfig
from mem20officez.server import OfficeServer

HERE = Path(__file__).parent
HARVEST = HERE.parent.parent / "src_harvest"


class TestConfig(unittest.TestCase):
    """Config loading and defaults."""

    def test_defaults(self):
        cfg = OfficeConfig()
        self.assertEqual(cfg.host, "0.0.0.0")
        self.assertEqual(cfg.port, 3000)
        self.assertEqual(cfg.gateway_url, "http://127.0.0.1:4000")
        self.assertEqual(cfg.secrets_home, "/opt/mem20/secrets")
        self.assertTrue(cfg.enable_phaser)
        self.assertTrue(cfg.enable_wellness)
        self.assertTrue(cfg.enable_dashboard)

    def test_load_from_yaml(self):
        import tempfile
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("port: 3100\ngateway_url: \"http://localhost:4100\"\n")
            f.flush()
            cfg = OfficeConfig.load(f.name)
        os.unlink(f.name)
        self.assertEqual(cfg.port, 3100)
        self.assertEqual(cfg.gateway_url, "http://localhost:4100")


class TestServerRoutes(unittest.TestCase):
    """Server route registration and handlers."""

    def setUp(self):
        self.cfg = OfficeConfig()
        self.cfg.harvest_root = HARVEST
        self.server = OfficeServer(self.cfg)

    def test_routes_registered(self):
        routes = [r.resource.canonical for r in self.server.app.router.routes()]
        expected = ["/health", "/api/office", "/api/gateway/models", "/api/gateway/chat",
                    "/wellness", "/wellness/demo", "/wellness/embed", "/dashboard"]
        for e in expected:
            self.assertIn(e, routes, f"Missing route: {e}")

    def test_health_response(self):
        async def test():
            mock_request = MagicMock()
            resp = await self.server.health(mock_request)
            self.assertEqual(resp.status, 200)
            data = resp.body
            import json
            j = json.loads(data.decode())
            self.assertEqual(j["service"], "mem20officez")
            self.assertEqual(j["status"], "ok")
        import asyncio
        asyncio.run(test())


class TestHarvestFiles(unittest.TestCase):
    """Harvest directory has expected files."""

    def test_wellness_files_exist(self):
        for f in ["wellness-checkin.html", "wellness-checkin-demo.html",
                  "wellness-checkin-embed.js", "mem20-dashboard.html"]:
            p = HARVEST / f
            self.assertTrue(p.exists(), f"Missing: {f}")

    def test_package_json_exists(self):
        self.assertTrue((HARVEST / "package.json").exists())

    def test_scripts_exist(self):
        for f in ["clawd3d-start.sh", "claw3doctor.mjs"]:
            p = HARVEST / "scripts" / f
            self.assertTrue(p.exists(), f"Missing: {f}")
        # These are in harvest root
        for f in ["get_angles.js", "make_continents.js"]:
            p = HARVEST / f
            self.assertTrue(p.exists(), f"Missing: {f}")

    def test_server_adapters_exist(self):
        for f in ["mem20-gateway-adapter.js", "gateway-proxy.js", "access-gate.js"]:
            p = HARVEST / "server" / f
            self.assertTrue(p.exists(), f"Missing: {f}")

    def test_phaser_scenes_exist(self):
        p = HARVEST / "src" / "features" / "office" / "phaser"
        self.assertTrue(p.exists())
        self.assertTrue((p / "OfficeBuilderScene.ts").exists())
        self.assertTrue((p / "OfficeViewerScene.ts").exists())

    def test_assets_exist(self):
        p = HARVEST / "public" / "office-assets" / "models" / "furniture"
        self.assertTrue(p.exists())
        # At least some furniture models
        self.assertGreater(len(list(p.glob("*.glb"))), 5)

    def test_docs_exist(self):
        docs = HARVEST / "docs"
        self.assertTrue(docs.exists())
        expected = ["mem20-gateway.md", "roadmap.md", "qa-department-spec.md"]
        for d in expected:
            self.assertTrue((docs / d).exists(), f"Missing doc: {d}")


class TestBuildOutput(unittest.TestCase):
    """Build output exists after npm run build."""

    def test_next_build_exists(self):
        build_dir = HERE.parent.parent / "build"
        self.assertTrue((build_dir / ".next").exists())
        self.assertTrue((build_dir / ".next" / "server" / "app" / "index.html").exists())
        self.assertTrue((build_dir / ".next" / "server" / "app" / "office.html").exists())
        self.assertTrue((build_dir / "public").exists())


if __name__ == "__main__":
    unittest.main()