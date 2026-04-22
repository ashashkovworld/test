"""test_simulation.py: automated checks for the example gas-vessel model."""

import unittest

from gas_system_sim.physical_constants import DEFAULT_PHYSICAL_CONSTANTS
from gas_system_sim.settings import SimulationSettings
from gas_system_sim.simulation_engine import run_simulation
from gas_system_sim.system_config import DEFAULT_SYSTEM_CONFIG


class SimulationTests(unittest.TestCase):
    """Verifies that the solver returns physically reasonable results."""

    def test_simulation_produces_time_series(self) -> None:
        # Use plotting-disabled settings so the test stays fully automated.
        settings = SimulationSettings(
            duration_seconds=10.0,
            integration_step_seconds=0.05,
            frame_interval_ms=50,
            integration_steps_per_frame=4,
            show_plots=False,
        )

        result = run_simulation(
            settings=settings,
            configuration=DEFAULT_SYSTEM_CONFIG,
            constants=DEFAULT_PHYSICAL_CONSTANTS,
        )

        # The result should contain a consistent set of synchronized arrays.
        self.assertGreater(len(result.times_seconds), 10)
        self.assertEqual(len(result.pressures_pa), len(result.times_seconds))
        self.assertEqual(len(result.mass_flows_kg_s), len(result.times_seconds))

        # The initial pressure follows from the ideal gas law for the given
        # vessel volume, temperature, krypton molar mass, and initial mass.
        self.assertAlmostEqual(result.pressures_pa[0] / 100_000.0, 13.22037, places=4)

        # Pressure must decrease during discharge, but should never fall below
        # the ambient pressure floor enforced by the model.
        self.assertLess(result.pressures_pa[-1], result.pressures_pa[0])
        self.assertGreaterEqual(
            result.pressures_pa[-1],
            DEFAULT_SYSTEM_CONFIG.ambient_pressure_pa,
        )

    def test_unit_conversions_are_exposed_in_si(self) -> None:
        # These checks make sure the user-facing engineering units are
        # translated correctly before entering the mathematical model.
        self.assertAlmostEqual(DEFAULT_SYSTEM_CONFIG.vessel_volume_m3, 0.022)
        self.assertAlmostEqual(DEFAULT_SYSTEM_CONFIG.vessel_temperature_kelvin, 293.15)
        self.assertAlmostEqual(DEFAULT_SYSTEM_CONFIG.orifice_diameter_m, 0.0001)
        self.assertAlmostEqual(DEFAULT_PHYSICAL_CONSTANTS.molar_mass_kg_mol, 0.083798)


if __name__ == "__main__":
    unittest.main()
