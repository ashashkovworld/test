"""simulation_engine.py: orchestrates time stepping of the mathematical model.

This module does not contain control logic for valves or regulators.
Its role is to:
- store the evolving simulation results;
- advance the vessel state in time;
- stop the calculation when the configured end condition is reached.
"""

from dataclasses import dataclass, field

from gas_system_sim.math_model import advance_mass_rk4, build_state
from gas_system_sim.physical_constants import PhysicalConstants
from gas_system_sim.settings import SimulationSettings
from gas_system_sim.system_config import SystemConfiguration


@dataclass
class SimulationResult:
    """Accumulates the calculated time series for later plotting or analysis."""

    times_seconds: list[float] = field(default_factory=list)
    pressures_pa: list[float] = field(default_factory=list)
    mass_flows_kg_s: list[float] = field(default_factory=list)
    gas_masses_kg: list[float] = field(default_factory=list)

    def append_state(self, pressure_state) -> None:
        """Copies one computed state into persistent result arrays."""

        self.times_seconds.append(pressure_state.time_seconds)
        self.pressures_pa.append(pressure_state.pressure_pa)
        self.mass_flows_kg_s.append(pressure_state.mass_flow_kg_s)
        self.gas_masses_kg.append(pressure_state.gas_mass_kg)


class SimulationEngine:
    """Drives the model forward one integration step at a time.

    The mathematical formulas stay in ``math_model.py``.
    This class only manages the simulation lifecycle:
    initialization, step-by-step advancement, and completion checks.
    """

    def __init__(
        self,
        settings: SimulationSettings,
        configuration: SystemConfiguration,
        constants: PhysicalConstants,
    ) -> None:
        # Immutable inputs that define how the simulation should run.
        self.settings = settings
        self.configuration = configuration
        self.constants = constants

        # Storage for the generated time history.
        self.result = SimulationResult()

        # The simulation starts at time zero with the initial gas mass
        # specified in the configuration.
        self.time_seconds = 0.0
        self.gas_mass_kg = configuration.initial_gas_mass_kg

        # Save the initial state immediately so the graph can show the
        # starting pressure before any outflow has happened.
        self.result.append_state(
            build_state(
                time_seconds=self.time_seconds,
                gas_mass_kg=self.gas_mass_kg,
                configuration=self.configuration,
                constants=self.constants,
            )
        )

    def is_complete(self) -> bool:
        """Stops when the time limit is reached or pressure equals ambient."""

        latest_pressure = self.result.pressures_pa[-1]
        return (
            self.time_seconds >= self.settings.duration_seconds
            or latest_pressure <= self.configuration.ambient_pressure_pa + 1.0
        )

    def step(self) -> None:
        """Performs one numerical integration step and records the new state."""

        if self.is_complete():
            return

        # Update the gas mass using the RK4 integrator from the math model.
        self.gas_mass_kg = advance_mass_rk4(
            gas_mass_kg=self.gas_mass_kg,
            time_step_seconds=self.settings.integration_step_seconds,
            configuration=self.configuration,
            constants=self.constants,
        )

        # Advance physical time by the same fixed integration step.
        self.time_seconds += self.settings.integration_step_seconds

        # Recalculate pressure and mass flow for the updated state and store them.
        self.result.append_state(
            build_state(
                time_seconds=self.time_seconds,
                gas_mass_kg=self.gas_mass_kg,
                configuration=self.configuration,
                constants=self.constants,
            )
        )


def run_simulation(
    settings: SimulationSettings,
    configuration: SystemConfiguration,
    constants: PhysicalConstants,
) -> SimulationResult:
    """Runs the full simulation from start to finish without the GUI."""

    engine = SimulationEngine(
        settings=settings,
        configuration=configuration,
        constants=constants,
    )
    while not engine.is_complete():
        engine.step()
    return engine.result
