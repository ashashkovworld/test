"""math_model.py: contains the physics and numerical formulas of the model.

This module is responsible for:
- converting gas mass inside the vessel into pressure;
- calculating outflow through the orifice;
- defining the differential equation for gas mass change;
- integrating that equation one step forward in time.
"""

from dataclasses import dataclass
from math import sqrt

from gas_system_sim.physical_constants import PhysicalConstants
from gas_system_sim.system_config import SystemConfiguration


@dataclass(frozen=True)
class ModelState:
    """Represents one fully evaluated physical state of the vessel."""

    time_seconds: float
    gas_mass_kg: float
    pressure_pa: float
    mass_flow_kg_s: float


def pressure_from_mass(
    gas_mass_kg: float,
    configuration: SystemConfiguration,
    constants: PhysicalConstants,
) -> float:
    """Computes vessel pressure using the ideal gas law in SI units."""

    return (
        gas_mass_kg
        * constants.specific_gas_constant
        * configuration.vessel_temperature_kelvin
        / configuration.vessel_volume_m3
    )


def equilibrium_gas_mass_kg(
    configuration: SystemConfiguration,
    constants: PhysicalConstants,
) -> float:
    """Mass that remains when vessel pressure becomes equal to ambient pressure."""

    return (
        configuration.ambient_pressure_pa
        * configuration.vessel_volume_m3
        / (constants.specific_gas_constant * configuration.vessel_temperature_kelvin)
    )


def critical_pressure_ratio(constants: PhysicalConstants) -> float:
    """Pressure ratio at which the outflow switches to choked flow."""

    kappa = constants.adiabatic_index
    return (2.0 / (kappa + 1.0)) ** (kappa / (kappa - 1.0))


def mass_flow_rate_kg_s(
    pressure_pa: float,
    configuration: SystemConfiguration,
    constants: PhysicalConstants,
) -> float:
    """Calculates mass flow through the hole for the current vessel pressure.

    Two flow regimes are handled:
    - choked flow, when the downstream pressure is low enough;
    - subcritical flow, when the outlet no longer reaches sonic velocity.
    """

    if pressure_pa <= configuration.ambient_pressure_pa:
        return 0.0

    kappa = constants.adiabatic_index
    gas_constant = constants.specific_gas_constant
    temperature_kelvin = configuration.vessel_temperature_kelvin
    pressure_ratio = configuration.ambient_pressure_pa / pressure_pa
    area_m2 = configuration.orifice_area_m2
    coefficient = configuration.discharge_coefficient

    if pressure_ratio <= critical_pressure_ratio(constants):
        # Choked flow: the gas velocity at the opening reaches the speed of sound,
        # so the downstream pressure no longer increases the mass flow.
        flow_factor = sqrt(
            kappa
            / (gas_constant * temperature_kelvin)
            * (2.0 / (kappa + 1.0)) ** ((kappa + 1.0) / (kappa - 1.0))
        )
        return coefficient * area_m2 * pressure_pa * flow_factor

    # Subcritical flow: mass flow depends on the actual pressure ratio between
    # the inside of the vessel and the ambient environment.
    flow_factor = sqrt(
        (2.0 * kappa)
        / (gas_constant * temperature_kelvin * (kappa - 1.0))
        * (
            pressure_ratio ** (2.0 / kappa)
            - pressure_ratio ** ((kappa + 1.0) / kappa)
        )
    )
    return coefficient * area_m2 * pressure_pa * flow_factor


def mass_derivative_kg_s(
    gas_mass_kg: float,
    configuration: SystemConfiguration,
    constants: PhysicalConstants,
) -> float:
    """Defines dm/dt, the rate at which gas mass decreases in the vessel."""

    pressure_pa = pressure_from_mass(gas_mass_kg, configuration, constants)
    return -mass_flow_rate_kg_s(pressure_pa, configuration, constants)


def advance_mass_rk4(
    gas_mass_kg: float,
    time_step_seconds: float,
    configuration: SystemConfiguration,
    constants: PhysicalConstants,
) -> float:
    """Advances the gas mass by one step using 4th-order Runge-Kutta.

    RK4 gives better accuracy than a simple Euler step while remaining fast
    enough for real-time plotting in this small model.
    """

    k1 = mass_derivative_kg_s(gas_mass_kg, configuration, constants)
    k2 = mass_derivative_kg_s(
        gas_mass_kg + 0.5 * time_step_seconds * k1,
        configuration,
        constants,
    )
    k3 = mass_derivative_kg_s(
        gas_mass_kg + 0.5 * time_step_seconds * k2,
        configuration,
        constants,
    )
    k4 = mass_derivative_kg_s(
        gas_mass_kg + time_step_seconds * k3,
        configuration,
        constants,
    )

    # Prevent the vessel from numerically dropping below the ambient-pressure
    # equilibrium state, which would be non-physical for this open vessel.
    next_mass = gas_mass_kg + time_step_seconds * (k1 + 2.0 * k2 + 2.0 * k3 + k4) / 6.0
    return max(next_mass, equilibrium_gas_mass_kg(configuration, constants))


def build_state(
    time_seconds: float,
    gas_mass_kg: float,
    configuration: SystemConfiguration,
    constants: PhysicalConstants,
) -> ModelState:
    """Builds a complete model state from time and current gas mass."""

    pressure_pa = pressure_from_mass(gas_mass_kg, configuration, constants)
    mass_flow = mass_flow_rate_kg_s(pressure_pa, configuration, constants)
    return ModelState(
        time_seconds=time_seconds,
        gas_mass_kg=gas_mass_kg,
        pressure_pa=pressure_pa,
        mass_flow_kg_s=mass_flow,
    )
