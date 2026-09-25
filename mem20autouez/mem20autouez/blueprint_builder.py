"""Blueprint Builder — native absorption of AutoUE blueprint generation."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from .connection import UECommand


@dataclass
class BlueprintProperty:
    """Blueprint property definition."""
    name: str
    property_type: str
    default_value: Any = None
    category: str = "Default"
    tooltip: str = ""
    is_public: bool = True
    is_readonly: bool = False


@dataclass
class BlueprintFunction:
    """Blueprint function definition."""
    name: str
    parameters: List[BlueprintProperty] = field(default_factory=list)
    return_type: str = "None"
    is_pure: bool = False
    category: str = "Default"
    body: List[str] = field(default_factory=list)  # Blueprint nodes as text


@dataclass
class BlueprintComponent:
    """Blueprint component."""
    component_type: str
    name: str
    properties: Dict[str, Any] = field(default_factory=dict)
    parent: Optional[str] = None


class BlueprintBuilder:
    """Blueprint builder — absorption of AutoUE BlueprintBuilder.

    Every operation issues a real command over the WebSocket connection and
    interprets the engine's response. Definitions are serialized with the
    engine so nothing is fabricated locally.
    """

    def __init__(self, connection: Any):
        self.connection = connection

    async def create_blueprint(
        self,
        parent_class: str,
        name: str,
        path: str = "/Game/Blueprints",
    ) -> Optional[str]:
        """Create new blueprint asset; returns the engine-created asset path."""
        resp = await self.connection.send_command(UECommand("create_blueprint", {
            "parent_class": parent_class,
            "name": name,
            "path": path,
        }))
        if not resp.success:
            return None
        return resp.data if resp.data else f"{path}/{name}"

    async def add_property(self, blueprint_path: str, prop: BlueprintProperty) -> bool:
        """Add property to blueprint."""
        resp = await self.connection.send_command(UECommand("add_property", {
            "blueprint_path": blueprint_path,
            "property": asdict(prop),
        }))
        return resp.success

    async def add_function(self, blueprint_path: str, func: BlueprintFunction) -> bool:
        """Add function to blueprint."""
        resp = await self.connection.send_command(UECommand("add_function", {
            "blueprint_path": blueprint_path,
            "function": asdict(func),
        }))
        return resp.success

    async def add_component(self, blueprint_path: str, component: BlueprintComponent) -> bool:
        """Add component to blueprint."""
        resp = await self.connection.send_command(UECommand("add_component", {
            "blueprint_path": blueprint_path,
            "component": asdict(component),
        }))
        return resp.success

    async def compile_blueprint(self, blueprint_path: str) -> bool:
        """Compile blueprint."""
        resp = await self.connection.send_command(UECommand("compile_blueprint", {"blueprint_path": blueprint_path}))
        return resp.success

    async def generate_from_template(
        self,
        template_name: str,
        parameters: Dict[str, Any],
        output_path: str,
    ) -> Optional[str]:
        """Generate blueprint from template; returns the engine-created path."""
        resp = await self.connection.send_command(UECommand("generate_from_template", {
            "template_name": template_name,
            "parameters": parameters,
            "output_path": output_path,
        }))
        if not resp.success:
            return None
        return resp.data if resp.data else output_path

    # Common templates
    ACTOR_TEMPLATE = "Actor"
    CHARACTER_TEMPLATE = "Character"
    WIDGET_TEMPLATE = "UserWidget"
    ANIM_INSTANCE_TEMPLATE = "AnimInstance"