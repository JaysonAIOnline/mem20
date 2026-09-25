"""Behavior Tree — native absorption of UniKit behavior trees."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional
import uuid


class NodeStatus(str, Enum):
    """Behavior tree node status."""
    SUCCESS = "success"
    FAILURE = "failure"
    RUNNING = "running"


class NodeType(str, Enum):
    """Behavior tree node type."""
    SEQUENCE = "sequence"
    SELECTOR = "selector"
    PARALLEL = "parallel"
    DECORATOR = "decorator"
    ACTION = "action"
    CONDITION = "condition"


@dataclass
class Blackboard:
    """Shared data storage for behavior tree."""
    data: Dict[str, Any] = field(default_factory=dict)

    def set(self, key: str, value: Any) -> None:
        self.data[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)

    def has(self, key: str) -> bool:
        return key in self.data

    def remove(self, key: str) -> None:
        self.data.pop(key, None)


class BTNode(ABC):
    """Base behavior tree node."""

    def __init__(self, name: str = None):
        self.name = name or self.__class__.__name__
        self.id = uuid.uuid4().hex[:8]
        self.children: List["BTNode"] = []
        self.parent: Optional["BTNode"] = None
        self.blackboard: Optional[Blackboard] = None

    def add_child(self, child: "BTNode") -> "BTNode":
        child.parent = self
        if self.blackboard:
            child.blackboard = self.blackboard
        self.children.append(child)
        return child

    def add_children(self, *children: "BTNode") -> "BTNode":
        for child in children:
            self.add_child(child)
        return self

    @abstractmethod
    def tick(self) -> NodeStatus:
        pass

    def reset(self) -> None:
        for child in self.children:
            child.reset()


class CompositeNode(BTNode):
    """Composite node base class."""

    def __init__(self, name: str = None, children: List[BTNode] = None):
        super().__init__(name)
        if children:
            for child in children:
                self.add_child(child)


class Sequence(CompositeNode):
    """Sequence node - runs children in order, fails if any fails."""

    def tick(self) -> NodeStatus:
        for child in self.children:
            status = child.tick()
            if status != NodeStatus.SUCCESS:
                return status
        return NodeStatus.SUCCESS


class Selector(CompositeNode):
    """Selector node - runs children in order, succeeds if any succeeds."""

    def tick(self) -> NodeStatus:
        for child in self.children:
            status = child.tick()
            if status != NodeStatus.FAILURE:
                return status
        return NodeStatus.FAILURE


class Parallel(CompositeNode):
    """Parallel node - runs all children, succeeds if enough succeed."""

    def __init__(self, name: str = None, children: List[BTNode] = None, success_threshold: int = 1):
        super().__init__(name, children)
        self.success_threshold = success_threshold

    def tick(self) -> NodeStatus:
        success_count = 0
        for child in self.children:
            status = child.tick()
            if status == NodeStatus.SUCCESS:
                success_count += 1
            elif status == NodeStatus.FAILURE:
                return NodeStatus.FAILURE
        if success_count >= self.success_threshold:
            return NodeStatus.SUCCESS
        return NodeStatus.RUNNING


class DecoratorNode(BTNode):
    """Decorator node base class."""

    def __init__(self, name: str = None, child: BTNode = None):
        super().__init__(name)
        if child:
            self.add_child(child)


class Inverter(DecoratorNode):
    """Inverter - flips success/failure."""

    def tick(self) -> NodeStatus:
        if not self.children:
            return NodeStatus.FAILURE
        status = self.children[0].tick()
        if status == NodeStatus.SUCCESS:
            return NodeStatus.FAILURE
        elif status == NodeStatus.FAILURE:
            return NodeStatus.SUCCESS
        return NodeStatus.RUNNING


class Repeater(DecoratorNode):
    """Repeater - repeats child N times."""

    def __init__(self, name: str = None, child: BTNode = None, count: int = 1):
        super().__init__(name, child)
        self.count = count
        self.current = 0

    def tick(self) -> NodeStatus:
        if not self.children:
            return NodeStatus.FAILURE
        while self.current < self.count:
            status = self.children[0].tick()
            if status == NodeStatus.FAILURE:
                self.current = 0
                return NodeStatus.FAILURE
            elif status == NodeStatus.SUCCESS:
                self.current += 1
                if self.current >= self.count:
                    self.current = 0
                    return NodeStatus.SUCCESS
            else:  # RUNNING
                return NodeStatus.RUNNING
        self.current = 0
        return NodeStatus.SUCCESS


class UntilSuccess(DecoratorNode):
    """Repeats until child succeeds."""

    def tick(self) -> NodeStatus:
        if not self.children:
            return NodeStatus.FAILURE
        status = self.children[0].tick()
        if status == NodeStatus.SUCCESS:
            return NodeStatus.SUCCESS
        return NodeStatus.RUNNING


class UntilFailure(DecoratorNode):
    """Repeats until child fails."""

    def tick(self) -> NodeStatus:
        if not self.children:
            return NodeStatus.FAILURE
        status = self.children[0].tick()
        if status == NodeStatus.FAILURE:
            return NodeStatus.FAILURE
        return NodeStatus.RUNNING


# Leaf nodes
class ActionNode(BTNode):
    """Action leaf node."""

    def __init__(self, name: str = None, action: Callable = None):
        super().__init__(name)
        self.action = action or (lambda bb: NodeStatus.SUCCESS)

    def tick(self) -> NodeStatus:
        if self.blackboard:
            return self.action(self.blackboard)
        return self.action(None)


class ConditionNode(BTNode):
    """Condition leaf node."""

    def __init__(self, name: str = None, condition: Callable = None):
        super().__init__(name)
        self.condition = condition or (lambda bb: True)

    def tick(self) -> NodeStatus:
        if self.blackboard:
            return NodeStatus.SUCCESS if self.condition(self.blackboard) else NodeStatus.FAILURE
        return NodeStatus.SUCCESS if self.condition(None) else NodeStatus.FAILURE


class BehaviorTree:
    """Behavior tree runner."""

    def __init__(self, root: BTNode, blackboard: Blackboard = None):
        self.root = root
        self.blackboard = blackboard or Blackboard()
        self._propagate_blackboard(self.root, self.blackboard)

    def _propagate_blackboard(self, node: BTNode, bb: Blackboard):
        node.blackboard = bb
        for child in node.children:
            self._propagate_blackboard(child, bb)

    def tick(self) -> NodeStatus:
        return self.root.tick()

    def reset(self) -> None:
        self.root.reset()

    def set_blackboard(self, bb: Blackboard) -> None:
        self.blackboard = bb
        self._propagate_blackboard(self.root, bb)


def create_bt_from_dict(data: Dict, blackboard: Blackboard = None) -> BehaviorTree:
    """Create behavior tree from dictionary definition."""
    # Simple factory for common patterns
    bb = blackboard or Blackboard()
    # This would be expanded with full deserialization
    return BehaviorTree(ActionNode(name="root"), bb)