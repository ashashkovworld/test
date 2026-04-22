"""main.py: application entry point for running the simulation project.

This file wires together the default settings, default configuration,
physical constants, the simulation engine, and the plotting window.
"""

from pathlib import Path
import sys


# When this file is launched directly, Python may not know about the parent
# ``src`` directory yet. Add it so absolute package imports still work.
if __package__ is None or __package__ == "":
    PACKAGE_ROOT = Path(__file__).resolve().parent.parent
    if str(PACKAGE_ROOT) not in sys.path:
        sys.path.insert(0, str(PACKAGE_ROOT))

from gas_system_sim.physical_constants import DEFAULT_PHYSICAL_CONSTANTS
from gas_system_sim.plot_window import show_results_window
from gas_system_sim.settings import DEFAULT_SETTINGS
from gas_system_sim.simulation_engine import run_simulation
from gas_system_sim.system_config import DEFAULT_SYSTEM_CONFIG


def main() -> None:
    """Starts the GUI mode or a headless calculation, depending on settings."""

    if DEFAULT_SETTINGS.show_plots:
        show_results_window(
            settings=DEFAULT_SETTINGS,
            configuration=DEFAULT_SYSTEM_CONFIG,
            constants=DEFAULT_PHYSICAL_CONSTANTS,
        )
        return

    # Headless mode is useful for tests or quick console verification.
    result = run_simulation(
        settings=DEFAULT_SETTINGS,
        configuration=DEFAULT_SYSTEM_CONFIG,
        constants=DEFAULT_PHYSICAL_CONSTANTS,
    )
    print("Simulation completed.")
    print(f"Samples: {len(result.times_seconds)}")
    print(f"Final pressure: {result.pressures_pa[-1] / 100_000.0:.3f} bar")


if __name__ == "__main__":
    main()
