"""math_model.py: physics helpers for block-based gas-system simulation.

Each block kind has its own local model:
- capacity: stores mass and converts it to pressure through the ideal gas law;
- tube: stores mass, has its own volume, and contributes a flow area;
- valve: behaves like a tube when open and blocks flow when closed;
- orifice: contributes the narrow restriction area;
- environment: supplies a constant boundary pressure and acts as an infinite sink.

The simulation engine combines these local block models along connection paths.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import pi, sqrt

from gas_system_sim.physical_constants import PhysicalConstants
from gas_system_sim.system_config import BlockConfig


@dataclass(frozen=True)
class PathFlowReport:
    """Describes one resolved flow segment between two storage-like nodes."""

    upstream_block_id: str
    downstream_block_id: str
    traversed_block_ids: list[str]
    upstream_pressure_pa: float
    downstream_pressure_pa: float
    mass_flow_kg_s: float
    representative_temperature_kelvin: float


def temperature_kelvin(block: BlockConfig) -> float:
    """Converts the configured block temperature from Celsius to kelvin."""

    return block.temperature_celsius + 273.15


def area_from_diameter_mm(diameter_mm: float) -> float:
    """Converts a diameter in millimeters into a circular flow area in m²."""

    radius_m = diameter_mm / 1000.0 / 2.0
    return pi * radius_m * radius_m


def capacity_pressure_pa(
    block: BlockConfig,
    gas_mass_kg: float,
    constants: PhysicalConstants,
) -> float:
    """Returns the pressure inside a capacity block using the ideal gas law."""

    volume_m3 = block.volume_liters / 1000.0
    return gas_mass_kg * constants.specific_gas_constant * temperature_kelvin(block) / volume_m3


def tube_volume_m3(block: BlockConfig) -> float:
    """Returns the gas volume inside the tube from diameter and length."""

    return area_from_diameter_mm(block.diameter_mm) * block.length_m


def tube_pressure_pa(
    block: BlockConfig,
    gas_mass_kg: float,
    constants: PhysicalConstants,
) -> float:
    """Returns the pressure inside a tube treated as a finite gas volume."""

    volume_m3 = tube_volume_m3(block)
    if volume_m3 <= 0.0:
        return 0.0
    return gas_mass_kg * constants.specific_gas_constant * temperature_kelvin(block) / volume_m3


def capacity_equilibrium_mass_kg(
    block: BlockConfig,
    ambient_pressure_pa: float,
    constants: PhysicalConstants,
) -> float:
    """Mass remaining in a capacity when it reaches the target ambient pressure."""

    volume_m3 = block.volume_liters / 1000.0
    return (
        ambient_pressure_pa
        * volume_m3
        / (constants.specific_gas_constant * temperature_kelvin(block))
    )


def tube_equilibrium_mass_kg(
    block: BlockConfig,
    ambient_pressure_pa: float,
    constants: PhysicalConstants,
) -> float:
    """Mass remaining in a tube when it reaches the target pressure."""

    volume_m3 = tube_volume_m3(block)
    return (
        ambient_pressure_pa
        * volume_m3
        / (constants.specific_gas_constant * temperature_kelvin(block))
    )


def environment_pressure_pa(block: BlockConfig) -> float:
    """Returns the constant pressure of the external environment in pascals."""

    return block.pressure_bar * 100_000.0


def tube_effective_area_m2(block: BlockConfig) -> float:
    """Returns the flow area of a tube block."""

    return area_from_diameter_mm(block.diameter_mm)


def orifice_effective_area_m2(block: BlockConfig) -> float:
    """Returns the flow area of a throttle washer block."""

    return area_from_diameter_mm(block.diameter_mm)


def valve_effective_area_m2(block: BlockConfig) -> float:
    """Returns zero for a closed valve or the valve area for an open valve."""

    if not block.is_open:
        return 0.0
    return area_from_diameter_mm(block.diameter_mm)


def block_effective_area_m2(block: BlockConfig) -> float:
    """Returns the area contribution of a block in a discharge path."""

    if block.kind == "tube":
        return tube_effective_area_m2(block)
    if block.kind == "valve":
        return valve_effective_area_m2(block)
    if block.kind == "orifice":
        return orifice_effective_area_m2(block)
    return float("inf")


def block_has_flow_model(block: BlockConfig) -> bool:
    """Returns ``True`` for flow elements that restrict a path."""

    return block.kind in {"tube", "valve", "orifice"}


def block_is_storage(block: BlockConfig) -> bool:
    """Returns ``True`` for blocks that own gas volume and pressure state."""

    return block.kind in {"capacity", "tube", "environment"}


def critical_pressure_ratio(constants: PhysicalConstants) -> float:
    """Returns the pressure ratio that separates choked and subcritical flow."""

    kappa = constants.adiabatic_index
    return (2.0 / (kappa + 1.0)) ** (kappa / (kappa - 1.0))


def compressible_mass_flow_kg_s(
    upstream_pressure_pa: float,
    downstream_pressure_pa: float,
    effective_area_m2: float,
    representative_temperature_kelvin: float,
    constants: PhysicalConstants,
    discharge_coefficient: float = 0.8,
) -> float:
    """Computes gas discharge through the path bottleneck.

    The formula uses the same compressible-flow approximation as the earlier
    single-vessel example. The engine feeds it the narrowest effective area
    found along the whole path.
    """

    if effective_area_m2 <= 0.0 or upstream_pressure_pa <= downstream_pressure_pa:
        return 0.0

    kappa = constants.adiabatic_index
    gas_constant = constants.specific_gas_constant
    pressure_ratio = downstream_pressure_pa / upstream_pressure_pa

    if pressure_ratio <= critical_pressure_ratio(constants):
        flow_factor = sqrt(
            kappa
            / (gas_constant * representative_temperature_kelvin)
            * (2.0 / (kappa + 1.0)) ** ((kappa + 1.0) / (kappa - 1.0))
        )
        return discharge_coefficient * effective_area_m2 * upstream_pressure_pa * flow_factor

    flow_factor = sqrt(
        (2.0 * kappa)
        / (gas_constant * representative_temperature_kelvin * (kappa - 1.0))
        * (
            pressure_ratio ** (2.0 / kappa)
            - pressure_ratio ** ((kappa + 1.0) / kappa)
        )
    )
    return discharge_coefficient * effective_area_m2 * upstream_pressure_pa * flow_factor


def representative_path_temperature_kelvin(path_blocks: list[BlockConfig]) -> float:
    """Returns one representative temperature for the current discharge path."""

    temperatures = [temperature_kelvin(block) for block in path_blocks]
    if not temperatures:
        return 293.15
    return sum(temperatures) / len(temperatures)
