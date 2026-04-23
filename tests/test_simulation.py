"""test_simulation.py: automated checks for the block-based simulation core."""

import unittest

from gas_system_sim.physical_constants import DEFAULT_PHYSICAL_CONSTANTS
from gas_system_sim.settings import SimulationSettings
from gas_system_sim.simulation_engine import SimulationEngine, run_simulation
from gas_system_sim.system_config import (
    DEFAULT_SYSTEM_CONFIG,
    SystemConfiguration,
    build_block,
)


class SimulationTests(unittest.TestCase):
    """Checks the non-GUI parts of the configurable simulation project."""

    def test_configuration_roundtrip_preserves_blocks_and_connections(self) -> None:
        payload = DEFAULT_SYSTEM_CONFIG.to_dict()
        restored = SystemConfiguration.from_dict(payload)

        self.assertEqual(len(restored.blocks), len(DEFAULT_SYSTEM_CONFIG.blocks))
        self.assertEqual(len(restored.connections), len(DEFAULT_SYSTEM_CONFIG.connections))
        self.assertEqual(restored.blocks[0].kind, DEFAULT_SYSTEM_CONFIG.blocks[0].kind)
        environment = next(block for block in restored.blocks if block.kind == "environment")
        self.assertFalse(environment.plot_enabled)

    def test_open_valve_path_reduces_capacity_pressure(self) -> None:
        settings = SimulationSettings(
            duration_seconds=1.0,
            integration_step_seconds=0.05,
            frame_interval_ms=50,
            default_real_time_speed=1.0,
            max_real_time_speed=1_000_000.0,
            show_plots=False,
        )
        configuration = SystemConfiguration.from_dict(DEFAULT_SYSTEM_CONFIG.to_dict())
        valve = next(block for block in configuration.blocks if block.kind == "valve")
        valve.is_open = True

        result = run_simulation(
            settings=settings,
            configuration=configuration,
            constants=DEFAULT_PHYSICAL_CONSTANTS,
        )

        capacity = next(block for block in configuration.blocks if block.kind == "capacity")
        series = result.block_series[capacity.block_id]
        self.assertLess(series.pressure_pa[-1], series.pressure_pa[0])

    def test_closed_valve_keeps_capacity_pressure_constant(self) -> None:
        settings = SimulationSettings(
            duration_seconds=0.2,
            integration_step_seconds=0.05,
            frame_interval_ms=50,
            default_real_time_speed=1.0,
            max_real_time_speed=1_000_000.0,
            show_plots=False,
        )
        engine = SimulationEngine(
            settings=settings,
            configuration=SystemConfiguration.from_dict(DEFAULT_SYSTEM_CONFIG.to_dict()),
            constants=DEFAULT_PHYSICAL_CONSTANTS,
        )

        capacity = next(
            block for block in engine.configuration.blocks if block.kind == "capacity"
        )
        initial_pressure = engine.result.block_series[capacity.block_id].pressure_pa[-1]
        engine.step()
        next_pressure = engine.result.block_series[capacity.block_id].pressure_pa[-1]

        self.assertAlmostEqual(initial_pressure, next_pressure)
        self.assertGreater(engine.time_seconds, 0.0)

    def test_runtime_valve_toggle_changes_pressure_trend(self) -> None:
        settings = SimulationSettings(
            duration_seconds=None,
            integration_step_seconds=0.05,
            frame_interval_ms=50,
            default_real_time_speed=1.0,
            max_real_time_speed=1_000_000.0,
            show_plots=False,
        )
        configuration = SystemConfiguration.from_dict(DEFAULT_SYSTEM_CONFIG.to_dict())
        engine = SimulationEngine(
            settings=settings,
            configuration=configuration,
            constants=DEFAULT_PHYSICAL_CONSTANTS,
        )

        capacity = next(
            block for block in configuration.blocks if block.kind == "capacity"
        )
        valve = next(block for block in configuration.blocks if block.kind == "valve")

        closed_pressure = engine.result.block_series[capacity.block_id].pressure_pa[-1]
        engine.step()
        still_closed_pressure = engine.result.block_series[capacity.block_id].pressure_pa[-1]

        engine.set_valve_open(valve.block_id, True)
        engine.step()
        opened_pressure = engine.result.block_series[capacity.block_id].pressure_pa[-1]

        engine.set_valve_open(valve.block_id, False)
        engine.step()
        closed_again_pressure = engine.result.block_series[capacity.block_id].pressure_pa[-1]

        self.assertAlmostEqual(closed_pressure, still_closed_pressure)
        self.assertLess(opened_pressure, still_closed_pressure)
        self.assertAlmostEqual(opened_pressure, closed_again_pressure, delta=0.1)

    def test_orifice_flow_series_is_available(self) -> None:
        settings = SimulationSettings(
            duration_seconds=0.2,
            integration_step_seconds=0.05,
            frame_interval_ms=50,
            default_real_time_speed=1.0,
            max_real_time_speed=1_000_000.0,
            show_plots=False,
        )
        configuration = SystemConfiguration.from_dict(DEFAULT_SYSTEM_CONFIG.to_dict())
        valve = next(block for block in configuration.blocks if block.kind == "valve")
        orifice = next(block for block in configuration.blocks if block.kind == "orifice")
        valve.is_open = True

        result = run_simulation(
            settings=settings,
            configuration=configuration,
            constants=DEFAULT_PHYSICAL_CONSTANTS,
        )

        self.assertGreater(
            max(result.block_series[orifice.block_id].flow_kg_s),
            0.0,
        )

    def test_direct_connection_does_not_create_hidden_storage(self) -> None:
        settings = SimulationSettings(
            duration_seconds=None,
            integration_step_seconds=0.05,
            frame_interval_ms=50,
            default_real_time_speed=1.0,
            max_real_time_speed=1_000_000.0,
            show_plots=False,
        )
        configuration = SystemConfiguration.from_dict(DEFAULT_SYSTEM_CONFIG.to_dict())
        configuration.remove_block("tube_1")
        configuration.add_connection("capacity_1", "valve_1")

        engine = SimulationEngine(
            settings=settings,
            configuration=configuration,
            constants=DEFAULT_PHYSICAL_CONSTANTS,
        )

        self.assertEqual(
            sorted(engine.storage_masses_kg),
            sorted(
                block.block_id
                for block in configuration.blocks
                if block.kind in {"capacity", "tube"}
            ),
        )

    def test_duration_none_keeps_engine_running(self) -> None:
        settings = SimulationSettings(
            duration_seconds=None,
            integration_step_seconds=0.05,
            frame_interval_ms=50,
            default_real_time_speed=1.0,
            max_real_time_speed=1_000_000.0,
            show_plots=False,
        )
        engine = SimulationEngine(
            settings=settings,
            configuration=SystemConfiguration.from_dict(DEFAULT_SYSTEM_CONFIG.to_dict()),
            constants=DEFAULT_PHYSICAL_CONSTANTS,
        )

        engine.step()
        engine.step()

        self.assertFalse(engine.is_complete())
        self.assertAlmostEqual(engine.time_seconds, 0.1)

    def test_add_connection_avoids_duplicates(self) -> None:
        configuration = SystemConfiguration(
            blocks=[
                build_block("capacity_1", "capacity", 100.0, 100.0),
                build_block("environment_1", "environment", 200.0, 100.0),
            ],
            connections=[],
        )

        configuration.add_connection("capacity_1", "environment_1")
        configuration.add_connection("environment_1", "capacity_1")

        self.assertEqual(len(configuration.connections), 1)


if __name__ == "__main__":
    unittest.main()
