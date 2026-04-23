"""system_config.py: declarative configuration for a block-based gas system.

The user assembles a model from individual blocks:
- capacity;
- tube;
- valve;
- orifice;
- environment.

Blocks are connected with graph edges and can be saved to or loaded from JSON.
This module contains only the configuration data model and helper functions.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from itertools import count
from typing import Any, Literal


BlockKind = Literal["capacity", "tube", "orifice", "valve", "environment"]
PlotParameter = Literal["pressure", "temperature", "flow"]


@dataclass
class BlockConfig:
    """Stores one block from the graphical configurator.

    The same structure is used for every block kind. Only the fields relevant
    to the selected ``kind`` participate in calculations.
    """

    block_id: str
    name: str
    kind: BlockKind
    x: float
    y: float
    temperature_celsius: float = 20.0
    volume_liters: float = 0.0
    initial_mass_kg: float = 0.0
    diameter_mm: float = 0.0
    length_m: float = 0.0
    pressure_bar: float = 1.01325
    is_open: bool = True
    plot_enabled: bool = False
    plot_parameter: PlotParameter = "pressure"

    def to_dict(self) -> dict[str, Any]:
        """Converts the block into a JSON-serializable dictionary."""

        return asdict(self)

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "BlockConfig":
        """Creates a block from saved JSON data."""

        return BlockConfig(**data)


@dataclass
class ConnectionConfig:
    """Stores one graphical connection between two blocks."""

    source_block_id: str
    target_block_id: str

    def to_dict(self) -> dict[str, Any]:
        """Converts the connection into a JSON-serializable dictionary."""

        return asdict(self)

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "ConnectionConfig":
        """Creates a connection from saved JSON data."""

        return ConnectionConfig(**data)


@dataclass
class SystemConfiguration:
    """Represents the full graph assembled in the configurator."""

    blocks: list[BlockConfig] = field(default_factory=list)
    connections: list[ConnectionConfig] = field(default_factory=list)

    def get_block(self, block_id: str) -> BlockConfig:
        """Returns one block by identifier or raises ``KeyError``."""

        for block in self.blocks:
            if block.block_id == block_id:
                return block
        raise KeyError(f"Unknown block_id: {block_id}")

    def remove_block(self, block_id: str) -> None:
        """Removes a block and every connection attached to it."""

        self.blocks = [block for block in self.blocks if block.block_id != block_id]
        self.connections = [
            connection
            for connection in self.connections
            if connection.source_block_id != block_id
            and connection.target_block_id != block_id
        ]

    def add_connection(self, source_block_id: str, target_block_id: str) -> None:
        """Adds one undirected connection unless it already exists."""

        if source_block_id == target_block_id:
            return

        canonical_pair = tuple(sorted((source_block_id, target_block_id)))
        for connection in self.connections:
            existing_pair = tuple(
                sorted((connection.source_block_id, connection.target_block_id))
            )
            if existing_pair == canonical_pair:
                return

        self.connections.append(
            ConnectionConfig(
                source_block_id=source_block_id,
                target_block_id=target_block_id,
            )
        )

    def to_dict(self) -> dict[str, Any]:
        """Converts the whole configuration into a JSON-compatible structure."""

        return {
            "blocks": [block.to_dict() for block in self.blocks],
            "connections": [connection.to_dict() for connection in self.connections],
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "SystemConfiguration":
        """Creates the configuration from a JSON-compatible structure."""

        return SystemConfiguration(
            blocks=[BlockConfig.from_dict(item) for item in data.get("blocks", [])],
            connections=[
                ConnectionConfig.from_dict(item)
                for item in data.get("connections", [])
            ],
        )


BLOCK_DEFAULTS: dict[BlockKind, dict[str, Any]] = {
    "capacity": {
        "temperature_celsius": 20.0,
        "volume_liters": 22.0,
        "initial_mass_kg": 1.0,
        "plot_enabled": True,
        "plot_parameter": "pressure",
    },
    "tube": {
        "temperature_celsius": 20.0,
        "diameter_mm": 1.0,
        "length_m": 1.0,
        "plot_enabled": False,
        "plot_parameter": "pressure",
    },
    "orifice": {
        "temperature_celsius": 20.0,
        "diameter_mm": 0.1,
        "plot_enabled": False,
        "plot_parameter": "pressure",
    },
    "valve": {
        "temperature_celsius": 20.0,
        "diameter_mm": 1.0,
        "is_open": False,
        "plot_enabled": False,
        "plot_parameter": "pressure",
    },
    "environment": {
        "temperature_celsius": 20.0,
        "pressure_bar": 1.01325,
        "plot_enabled": False,
        "plot_parameter": "pressure",
    },
}


BLOCK_EDITABLE_FIELDS: dict[BlockKind, list[str]] = {
    "capacity": [
        "name",
        "x",
        "y",
        "temperature_celsius",
        "volume_liters",
        "initial_mass_kg",
        "plot_enabled",
        "plot_parameter",
    ],
    "tube": [
        "name",
        "x",
        "y",
        "temperature_celsius",
        "diameter_mm",
        "length_m",
        "plot_enabled",
        "plot_parameter",
    ],
    "orifice": [
        "name",
        "x",
        "y",
        "temperature_celsius",
        "diameter_mm",
        "plot_enabled",
        "plot_parameter",
    ],
    "valve": [
        "name",
        "x",
        "y",
        "temperature_celsius",
        "diameter_mm",
        "is_open",
        "plot_enabled",
        "plot_parameter",
    ],
    "environment": [
        "name",
        "x",
        "y",
        "temperature_celsius",
        "pressure_bar",
        "plot_enabled",
        "plot_parameter",
    ],
}


def build_block(block_id: str, kind: BlockKind, x: float, y: float) -> BlockConfig:
    """Creates a new block using defaults for the chosen kind."""

    defaults = BLOCK_DEFAULTS[kind]
    readable_name = {
        "capacity": "Емкость",
        "tube": "Трубка",
        "orifice": "Дроссель",
        "valve": "Клапан",
        "environment": "Среда",
    }[kind]
    return BlockConfig(
        block_id=block_id,
        name=f"{readable_name} {block_id.split('_')[-1]}",
        kind=kind,
        x=x,
        y=y,
        **defaults,
    )


def _default_blocks() -> list[BlockConfig]:
    """Builds the initial demonstration model shown in the configurator."""

    return [
        build_block("capacity_1", "capacity", 100.0, 160.0),
        build_block("tube_1", "tube", 280.0, 160.0),
        build_block("valve_1", "valve", 460.0, 160.0),
        build_block("orifice_1", "orifice", 640.0, 160.0),
        build_block("environment_1", "environment", 820.0, 160.0),
    ]


def _default_connections() -> list[ConnectionConfig]:
    """Builds the initial linear connection chain for the demo model."""

    return [
        ConnectionConfig("capacity_1", "tube_1"),
        ConnectionConfig("tube_1", "valve_1"),
        ConnectionConfig("valve_1", "orifice_1"),
        ConnectionConfig("orifice_1", "environment_1"),
    ]


def build_default_configuration() -> SystemConfiguration:
    """Returns the default configuration loaded on first start."""

    return SystemConfiguration(
        blocks=_default_blocks(),
        connections=_default_connections(),
    )


def new_block_id(configuration: SystemConfiguration, kind: BlockKind) -> str:
    """Allocates a block identifier that does not clash with existing ones."""

    existing_ids = {block.block_id for block in configuration.blocks}
    for index in count(1):
        candidate = f"{kind}_{index}"
        if candidate not in existing_ids:
            return candidate
    raise RuntimeError("Unable to allocate a new block identifier.")


# Default configuration loaded by the application.
DEFAULT_SYSTEM_CONFIG = build_default_configuration()
