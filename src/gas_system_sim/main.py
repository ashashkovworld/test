"""main.py: application entry point for the block-based gas-system project.

In GUI mode the application starts from a separate configurator window that
acts as a preprocessor before the simulation run.
"""

from pathlib import Path
import sys


# When this file is launched directly, Python may not know about the parent
# ``src`` directory yet. Add it so absolute package imports still work.
if __package__ is None or __package__ == "":
    PACKAGE_ROOT = Path(__file__).resolve().parent.parent
    if str(PACKAGE_ROOT) not in sys.path:
        sys.path.insert(0, str(PACKAGE_ROOT))

from gas_system_sim.configurator_window import show_configurator_window
from gas_system_sim.physical_constants import DEFAULT_PHYSICAL_CONSTANTS
from gas_system_sim.settings import DEFAULT_SETTINGS
from gas_system_sim.simulation_engine import run_simulation
from gas_system_sim.system_config import DEFAULT_SYSTEM_CONFIG


def main() -> None:
    """Starts the configurator in GUI mode or a headless batch run."""

    if DEFAULT_SETTINGS.show_plots:
        show_configurator_window(
            settings=DEFAULT_SETTINGS,
            constants=DEFAULT_PHYSICAL_CONSTANTS,
            configuration=DEFAULT_SYSTEM_CONFIG,
        )
        return

    if DEFAULT_SETTINGS.duration_seconds is None:
        raise RuntimeError(
            "Headless mode requires a finite duration_seconds value in settings."
        )

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
