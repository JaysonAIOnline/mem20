"""Perception — native absorption of UniKit perception."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple
from enum import Enum
import math


@dataclass
class Stimulus:
    """Sensory stimulus."""
    stimulus_type: str
    source_id: str
    intensity: float
    position: Tuple[float, float]
    metadata: Dict = field(default_factory=dict)
    timestamp: float = 0.0

    def distance_to(self, position: Tuple[float, float]) -> float:
        return math.hypot(self.position[0] - position[0], self.position[1] - position[1])


class Sensor:
    """Base sensor."""

    def __init__(self, sensor_type: str, range: float = 10.0, fov: float = 360.0):
        self.sensor_type = sensor_type
        self.range = range
        self.fov = fov
        self.enabled = True

    def detect(self, agent_position: Tuple[float, float], agent_rotation: float, world: Any) -> List[Any]:
        return []


class VisionSensor:
    """Vision sensor."""

    def __init__(self, range: float = 10.0, fov: float = 90.0):
        self.sensor_type = "vision"
        self.range = range
        self.fov = fov

    def detect(self, agent_position: Tuple[float, float], agent_rotation: float, world: Any) -> List[Dict]:
        return []


class HearingSensor:
    """Hearing sensor."""

    def __init__(self, range: float = 20.0):
        self.sensor_type = "hearing"
        self.range = range

    def detect(self, agent_position: Tuple[float, float], agent_rotation: float, world: Any) -> List[Dict]:
        return []


class PerceptionSystem:
    """Perception system for agents."""

    def __init__(self):
        self.sensors: List[Any] = []
        self.stimuli: List[Any] = []

    def add_sensor(self, sensor: Any) -> None:
        self.sensors.append(sensor)

    def update(self, agent_position: Tuple[float, float], agent_rotation: float, world: Any, dt: float) -> List[Any]:
        all_stimuli = []
        for sensor in self.sensors:
            if hasattr(sensor, 'enabled') and sensor.enabled:
                stimuli = sensor.detect(agent_position, agent_rotation, world)
                all_stimuli.extend(stimuli)
        return all_stimuli

    def get_stimuli_by_type(self, stimulus_type: str) -> List[Any]:
        return [s for s in self.stimuli if getattr(s, 'stimulus_type', '') == stimulus_type]

    def get_strongest_stimulus(self, stimulus_type: str) -> Optional[Any]:
        stimuli = self.get_stimuli_by_type(stimulus_type)
        if not stimuli:
            return None
        return max(stimuli, key=lambda s: getattr(s, 'intensity', 0))


class PerceptionManager:
    """Manages perception for multiple agents."""

    def __init__(self):
        self.agents: Dict[str, Any] = {}

    def create_agent_perception(self, agent_id: str) -> Any:
        from types import SimpleNamespace
        ps = SimpleNamespace()
        ps.sensors = []
        ps.stimuli = []
        ps.add_sensor = lambda s: ps.sensors.append(s)
        ps.update = lambda pos, rot, world, dt: []
        self.agents[agent_id] = ps
        return ps

    def get_agent_perception(self, agent_id: str) -> Optional[Any]:
        return self.agents.get(agent_id)

    def update_all(self, positions: Dict[str, Tuple[float, float]], rotations: Dict[str, float], world: Any, dt: float):
        for agent_id, ps in self.agents.items():
            pos = positions.get(agent_id, (0, 0))
            rot = rotations.get(agent_id, 0)
            if hasattr(ps, 'update'):
                ps.update(pos, rot, world, dt)

    def remove_agent(self, agent_id: str) -> bool:
        if agent_id in self.agents:
            del self.agents[agent_id]
            return True
        return False