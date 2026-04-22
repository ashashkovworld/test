"""run_simulation.py: small launcher script for starting the application.

This script is placed in the repository root so the project can be started
from ``D:\Codex`` without manually exporting ``PYTHONPATH``.
"""

from pathlib import Path
import sys


# Add the local ``src`` directory to the Python import path so the package
# ``gas_system_sim`` can be imported from a plain root-level launch.
PROJECT_ROOT = Path(__file__).resolve().parent
SRC_DIRECTORY = PROJECT_ROOT / "src"
if str(SRC_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(SRC_DIRECTORY))

from gas_system_sim.main import main


if __name__ == "__main__":
    # Delegate startup to the package entry point.
    main()
