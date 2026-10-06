"""Hermetic tests for mem20autouez.

These exercise the real library behavior: command serialization, engine
response parsing, error paths, and a loopback WebSocket roundtrip through the
actual `websockets` client. No stub returns are asserted.
"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
import unittest
from typing import Any, Dict, List, Optional

from mem20autouez.config import AutoUEConfig, DEFAULT_CONFIG
from mem20autouez.connection import UEConnection, UECommand, UEResponse
from mem20autouez.asset_manager import AssetManager, AssetInfo
from mem20autouez.blueprint_builder import (
    BlueprintBuilder,
    BlueprintProperty,
    BlueprintFunction,
    BlueprintComponent,
)
from mem20autouez.level_streamer import (
    LevelStreamer,
    StreamingLevel,
    LevelStreamingConfig,
)


class FakeConnection:
    """Recording async connection that returns canned engine responses."""

    def __init__(self, responses: Optional[List[UEResponse]] = None):
        self._responses: List[UEResponse] = list(responses or [])
        self.sent: List[UECommand] = []

    def enqueue(self, response: UEResponse) -> None:
        self._responses.append(response)

    async def send_command(self, command: UECommand) -> UEResponse:
        self.sent.append(command)
        if not self._responses:
            return UEResponse(request_id=command.request_id, success=False, error="no canned response")
        return self._responses.pop(0)


def success(data: Any = None) -> UEResponse:
    return UEResponse(request_id="0", success=True, data=data)


def fail(error: str = "engine error") -> UEResponse:
    return UEResponse(request_id="0", success=False, error=error)


class TestConfig(unittest.TestCase):
    """Config tests."""

    def test_defaults(self):
        cfg = AutoUEConfig()
        self.assertEqual(cfg.port, 8004)
        self.assertEqual(cfg.gateway_url, "http://127.0.0.1:4000")
        self.assertEqual(cfg.ue_host, "127.0.0.1")
        self.assertEqual(cfg.ue_port, 30010)

    def test_load_from_yaml(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("port: 9000\ngateway_url: \"http://localhost:4100\"\n")
            f.flush()
            cfg = AutoUEConfig.load(f.name)
        os.unlink(f.name)
        self.assertEqual(cfg.port, 9000)
        self.assertEqual(cfg.gateway_url, "http://localhost:4100")

    def test_save_roundtrip(self):
        cfg = AutoUEConfig(port=7777)
        path = tempfile.mktemp(suffix=".yaml")
        cfg.save(path)
        try:
            loaded = AutoUEConfig.load(path)
            self.assertEqual(loaded.port, 7777)
            self.assertEqual(loaded.ue_host, cfg.ue_host)
        finally:
            os.unlink(path)

    def test_default_config_reused(self):
        self.assertIsInstance(DEFAULT_CONFIG, AutoUEConfig)


class TestUECommand(unittest.TestCase):
    """UE command tests."""

    def test_command_creation(self):
        cmd = UECommand("test", {"key": "value"})
        self.assertEqual(cmd.command_type, "test")
        self.assertEqual(cmd.parameters, {"key": "value"})
        self.assertIsNotNone(cmd.request_id)

    def test_command_request_id_unique(self):
        self.assertNotEqual(UECommand("a").request_id, UECommand("b").request_id)

    def test_response(self):
        resp = UEResponse(request_id="123", success=True, data={"result": "ok"})
        self.assertTrue(resp.success)
        self.assertEqual(resp.data, {"result": "ok"})

        resp = UEResponse(request_id="123", success=False, error="Failed")
        self.assertFalse(resp.success)
        self.assertEqual(resp.error, "Failed")

    def test_send_command_when_not_connected(self):
        conn = UEConnection(host="127.0.0.1", port=1)
        resp = asyncio.run(conn.send_command(UECommand("test", {})))
        self.assertFalse(resp.success)
        self.assertEqual(resp.error, "Not connected")

    def test_websocket_roundtrip(self):
        """Real websockets.connect() loopback: command in, parsed response out."""

        async def scenario():
            received: List[Dict[str, Any]] = []

            async def handler(ws):
                async for message in ws:
                    data = json.loads(message)
                    received.append(data)
                    await ws.send(json.dumps({
                        "request_id": data.get("request_id"),
                        "success": True,
                        "data": {"echo": data.get("parameters"), "type": data.get("type")},
                    }))

            from websockets.asyncio.server import serve

            async with serve(handler, "127.0.0.1", 0) as server:
                port = server.sockets[0].getsockname()[1]
                conn = UEConnection(host="127.0.0.1", port=port)
                self.assertTrue(await conn.connect())
                self.assertIsNotNone(conn.websocket)
                resp = await conn.send_command(UECommand("get_actor_info", {"actor_path": "/Game/Actors/A"}))
                self.assertTrue(resp.success)
                self.assertEqual(resp.data["type"], "get_actor_info")
                self.assertEqual(resp.data["echo"], {"actor_path": "/Game/Actors/A"})
                await conn.disconnect()

        asyncio.run(scenario())


class TestAssetManager(unittest.TestCase):
    """Asset manager tests."""

    def setUp(self):
        self.mock_conn = FakeConnection()
        self.mgr = AssetManager(self.mock_conn)

    def test_asset_info(self):
        info = AssetInfo(path="/Game/Assets/Test", asset_type="StaticMesh", size_bytes=1024)
        self.assertEqual(info.path, "/Game/Assets/Test")
        self.assertEqual(info.asset_type, "StaticMesh")

    def test_asset_tags(self):
        info = AssetInfo(path="/Game/Test", asset_type="Material", tags=["PBR", "Master"])
        self.assertIn("PBR", info.tags)

    def test_list_assets_parses_response(self):
        self.mock_conn.enqueue(success([
            {"path": "/Game/Assets/Cube", "asset_type": "StaticMesh", "size_bytes": 1024, "tags": ["PBR"]},
            {"path": "/Game/Assets/Wall", "asset_type": "StaticMesh"},
        ]))
        assets = asyncio.run(self.mgr.list_assets("/Game/Assets"))
        self.assertEqual(len(assets), 2)
        self.assertEqual(assets[0].path, "/Game/Assets/Cube")
        self.assertEqual(assets[0].size_bytes, 1024)
        self.assertEqual(assets[1].asset_type, "StaticMesh")
        cmd = self.mock_conn.sent[0]
        self.assertEqual(cmd.command_type, "list_assets")
        self.assertEqual(cmd.parameters, {"path": "/Game/Assets"})
        self.assertIn("/Game/Assets/Cube", self.mgr.asset_cache)

    def test_list_assets_failure_returns_empty(self):
        self.mock_conn.enqueue(fail("engine down"))
        self.assertEqual(asyncio.run(self.mgr.list_assets()), [])
        self.assertEqual(len(self.mgr.asset_cache), 0)

    def test_get_asset_info_cache_hit_does_not_resend(self):
        self.mock_conn.enqueue(success({"path": "/Game/A", "asset_type": "Material", "tags": ["Master"]}))
        info = asyncio.run(self.mgr.get_asset_info("/Game/A"))
        self.assertEqual(info.asset_type, "Material")
        self.assertEqual(len(self.mock_conn.sent), 1)
        self.assertIs(asyncio.run(self.mgr.get_asset_info("/Game/A")), info)
        self.assertEqual(len(self.mock_conn.sent), 1)

    def test_get_asset_info_not_found(self):
        self.mock_conn.enqueue(fail("not found"))
        self.assertIsNone(asyncio.run(self.mgr.get_asset_info("/Game/Missing")))

    def test_import_export_delete_use_connection(self):
        self.mock_conn.enqueue(success())
        self.assertTrue(asyncio.run(self.mgr.import_asset("/tmp/source.fbx", "/Game/Assets/x", "StaticMesh")))
        self.assertEqual(self.mock_conn.sent[-1].command_type, "import_asset")
        self.mock_conn.enqueue(success())
        self.assertTrue(asyncio.run(self.mgr.export_asset("/Game/Assets/x", "/tmp/out.fbx")))
        self.assertEqual(self.mock_conn.sent[-1].command_type, "export_asset")
        self.mock_conn.enqueue(success())
        self.assertTrue(asyncio.run(self.mgr.delete_asset("/Game/Assets/x")))
        self.assertEqual(self.mock_conn.sent[-1].command_type, "delete_asset")

    def test_delete_failure_returns_false(self):
        self.mock_conn.enqueue(fail("locked"))
        self.assertFalse(asyncio.run(self.mgr.delete_asset("/Game/Assets/x")))

    def test_find_referencers(self):
        self.mock_conn.enqueue(success(["/Game/Assets/Using", "/Game/Assets/Also"]))
        refs = asyncio.run(self.mgr.find_referencers("/Game/Assets/Foo"))
        self.assertEqual(refs, ["/Game/Assets/Using", "/Game/Assets/Also"])

    def test_bulk_rename(self):
        self.mock_conn.enqueue(success(3))
        self.assertEqual(asyncio.run(self.mgr.bulk_rename("BP_*", "BP2_*")), 3)
        self.mock_conn.enqueue(fail())
        self.assertEqual(asyncio.run(self.mgr.bulk_rename("BP_*", "BP2_*")), 0)

    def test_validate_assets(self):
        self.mock_conn.enqueue(success({"valid": ["/Game/A"], "invalid": ["/Game/B"]}))
        result = asyncio.run(self.mgr.validate_assets(["/Game/A", "/Game/B"]))
        self.assertEqual(result["valid"], ["/Game/A"])
        self.assertEqual(result["invalid"], ["/Game/B"])


class TestBlueprintBuilder(unittest.TestCase):
    """Blueprint builder tests."""

    def setUp(self):
        self.mock_conn = FakeConnection()
        self.builder = BlueprintBuilder(self.mock_conn)

    def test_property(self):
        prop = BlueprintProperty(name="Health", property_type="Float", default_value=100.0, category="Stats")
        self.assertEqual(prop.name, "Health")
        self.assertEqual(prop.default_value, 100.0)

    def test_function(self):
        func = BlueprintFunction(
            name="TakeDamage",
            parameters=[BlueprintProperty(name="Amount", property_type="Float")],
            return_type="Void",
            body=["ApplyDamage", "CheckDeath"],
        )
        self.assertEqual(func.name, "TakeDamage")
        self.assertEqual(len(func.parameters), 1)

    def test_component(self):
        comp = BlueprintComponent(
            component_type="StaticMeshComponent",
            name="Mesh",
            properties={"StaticMesh": "/Game/Meshes/Cube"},
        )
        self.assertEqual(comp.component_type, "StaticMeshComponent")

    def test_create_blueprint_returns_engine_path(self):
        self.mock_conn.enqueue(success("/Game/Blueprints/BP_Foo"))
        path = asyncio.run(self.builder.create_blueprint("Actor", "BP_Foo"))
        self.assertEqual(path, "/Game/Blueprints/BP_Foo")
        cmd = self.mock_conn.sent[0]
        self.assertEqual(cmd.command_type, "create_blueprint")
        self.assertEqual(cmd.parameters, {"parent_class": "Actor", "name": "BP_Foo", "path": "/Game/Blueprints"})

    def test_create_blueprint_failure_returns_none(self):
        self.mock_conn.enqueue(fail("name conflict"))
        self.assertIsNone(asyncio.run(self.builder.create_blueprint("Actor", "BP_Foo")))

    def test_add_property_serializes(self):
        self.mock_conn.enqueue(success())
        result = asyncio.run(self.builder.add_property(
            "/Game/Blueprints/BP_Foo",
            BlueprintProperty(name="Health", property_type="Float", default_value=100.0, category="Stats"),
        ))
        self.assertTrue(result)
        params = self.mock_conn.sent[0].parameters
        self.assertEqual(params["blueprint_path"], "/Game/Blueprints/BP_Foo")
        self.assertEqual(params["property"]["name"], "Health")
        self.assertEqual(params["property"]["property_type"], "Float")
        self.assertEqual(params["property"]["default_value"], 100.0)

    def test_add_function_serializes(self):
        self.mock_conn.enqueue(success())
        result = asyncio.run(self.builder.add_function(
            "/Game/Blueprints/BP_Foo",
            BlueprintFunction(name="TakeDamage", body=["ApplyDamage"]),
        ))
        self.assertTrue(result)
        params = self.mock_conn.sent[0].parameters
        self.assertEqual(params["function"]["name"], "TakeDamage")
        self.assertEqual(params["function"]["body"], ["ApplyDamage"])

    def test_add_component_serializes(self):
        self.mock_conn.enqueue(success())
        result = asyncio.run(self.builder.add_component(
            "/Game/Blueprints/BP_Foo",
            BlueprintComponent(component_type="StaticMeshComponent", name="Mesh"),
        ))
        self.assertTrue(result)
        params = self.mock_conn.sent[0].parameters
        self.assertEqual(params["component"]["component_type"], "StaticMeshComponent")

    def test_compile_blueprint(self):
        self.mock_conn.enqueue(success())
        self.assertTrue(asyncio.run(self.builder.compile_blueprint("/Game/Blueprints/BP_Foo")))
        self.assertEqual(self.mock_conn.sent[0].command_type, "compile_blueprint")
        self.mock_conn.enqueue(fail("compile errors"))
        self.assertFalse(asyncio.run(self.builder.compile_blueprint("/Game/Blueprints/BP_Foo")))

    def test_generate_from_template(self):
        self.mock_conn.enqueue(success("/Game/Generated/BP_Widget"))
        path = asyncio.run(self.builder.generate_from_template("UserWidget", {"Title": "Hi"}, "/Game/Generated"))
        self.assertEqual(path, "/Game/Generated/BP_Widget")
        self.mock_conn.enqueue(fail())
        self.assertIsNone(asyncio.run(self.builder.generate_from_template("UserWidget", {}, "/Game/Generated")))


class TestLevelStreamer(unittest.TestCase):
    """Level streamer tests."""

    def setUp(self):
        self.mock_conn = FakeConnection()
        self.streamer = LevelStreamer(self.mock_conn)

    def test_streaming_level(self):
        level = StreamingLevel(package_name="Level1", level_name="Level1", is_loaded=True, is_visible=True)
        self.assertTrue(level.is_loaded)

    def test_config(self):
        config = LevelStreamingConfig(streaming_distance=10000.0)
        self.assertEqual(config.streaming_distance, 10000.0)

    def test_load_level_success_updates_state(self):
        self.mock_conn.enqueue(success({"package_name": "/Game/Levels/L1", "level_name": "L1", "is_loaded": True, "is_visible": True}))
        self.assertTrue(asyncio.run(self.streamer.load_level("L1")))
        self.assertIn("L1", self.streamer.loaded_levels)
        self.assertTrue(self.streamer.loaded_levels["L1"].is_loaded)
        self.assertEqual(self.mock_conn.sent[0].command_type, "load_level")

    def test_load_level_failure_leaves_state_empty(self):
        self.mock_conn.enqueue(fail("level missing"))
        self.assertFalse(asyncio.run(self.streamer.load_level("L1")))
        self.assertNotIn("L1", self.streamer.loaded_levels)

    def test_load_unload_roundtrip(self):
        self.mock_conn.enqueue(success())
        self.assertTrue(asyncio.run(self.streamer.load_level("L1", make_visible=True, should_block=False)))
        self.assertIn("L1", self.streamer.loaded_levels)
        self.assertTrue(self.streamer.loaded_levels["L1"].is_visible)
        self.mock_conn.enqueue(success())
        self.assertTrue(asyncio.run(self.streamer.unload_level("L1")))
        self.assertNotIn("L1", self.streamer.loaded_levels)

    def test_unload_failure_keeps_level(self):
        self.mock_conn.enqueue(success())
        asyncio.run(self.streamer.load_level("L1"))
        self.mock_conn.enqueue(fail("in use"))
        self.assertFalse(asyncio.run(self.streamer.unload_level("L1")))
        self.assertIn("L1", self.streamer.loaded_levels)

    def test_get_streaming_levels_parses_engine_state(self):
        self.mock_conn.enqueue(success([
            {"package_name": "/Game/Levels/A", "level_name": "A", "is_loaded": True, "is_visible": False},
            {"package_name": "/Game/Levels/B", "level_name": "B", "is_loaded": True, "is_visible": True},
        ]))
        levels = asyncio.run(self.streamer.get_streaming_levels())
        self.assertEqual(len(levels), 2)
        self.assertFalse(levels[0].is_visible)
        self.assertIn("A", self.streamer.loaded_levels)
        self.assertEqual(self.streamer.loaded_levels["B"].is_visible, True)

    def test_set_level_visibility(self):
        self.mock_conn.enqueue(success())
        asyncio.run(self.streamer.load_level("L1"))
        self.mock_conn.enqueue(success())
        self.assertTrue(asyncio.run(self.streamer.set_level_visibility("L1", False)))
        self.assertFalse(self.streamer.loaded_levels["L1"].is_visible)

    def test_set_streaming_distance(self):
        self.mock_conn.enqueue(success())
        self.assertTrue(asyncio.run(self.streamer.set_streaming_distance(12345.0)))
        self.assertEqual(self.streamer.config.streaming_distance, 12345.0)

    def test_get_level_bounds(self):
        self.mock_conn.enqueue(success({"min": [-10, -20, -30], "max": [10, 20, 30]}))
        bounds = asyncio.run(self.streamer.get_level_bounds("L1"))
        self.assertEqual(bounds, ((-10, -20, -30), (10, 20, 30)))
        self.mock_conn.enqueue(fail())
        self.assertIsNone(asyncio.run(self.streamer.get_level_bounds("L1")))

    def test_is_level_loaded(self):
        self.assertFalse(asyncio.run(self.streamer.is_level_loaded("L1")))
        self.mock_conn.enqueue(success())
        asyncio.run(self.streamer.load_level("L1"))
        self.assertTrue(asyncio.run(self.streamer.is_level_loaded("L1")))


class TestPublicSurface(unittest.TestCase):
    """Package exports are real, importable symbols."""

    def test_package_exports(self):
        import mem20autouez as pkg

        for name in pkg.__all__:
            self.assertTrue(hasattr(pkg, name), f"missing export: {name}")

        self.assertTrue(callable(UEConnection.connect))
        self.assertTrue(callable(AssetManager.list_assets))
        self.assertTrue(callable(BlueprintBuilder.create_blueprint))
        self.assertTrue(callable(LevelStreamer.load_level))

    def test_star_import(self):
        ns: Dict[str, Any] = {}
        exec("from mem20autouez import *", ns)
        for name in ("UEConnection", "AssetManager", "BlueprintBuilder", "LevelStreamer", "AutoUEConfig"):
            self.assertIn(name, ns)


if __name__ == "__main__":
    unittest.main()