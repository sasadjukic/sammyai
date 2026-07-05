"""Deterministic system-prompt composition for agent workflows."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Iterable


class PromptLayerOrder(IntEnum):
    CORE = 10
    AGENT = 20
    WORKFLOW = 30
    OUTPUT = 40
    RUN = 50


@dataclass(frozen=True)
class PromptLayer:
    name: str
    content: str
    order: PromptLayerOrder

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("Prompt layer name cannot be empty")
        if not self.content.strip():
            raise ValueError("Prompt layer content cannot be empty")


class PromptComposer:
    """Compose named layers in a stable, inspectable order."""

    def compose(self, layers: Iterable[PromptLayer]) -> str:
        ordered = sorted(tuple(layers), key=lambda layer: (layer.order, layer.name))
        if not ordered:
            raise ValueError("At least one prompt layer is required")
        return "\n\n".join(
            f"## {layer.name.strip()}\n\n{layer.content.strip()}"
            for layer in ordered
        )
