"""settings.py: stores global settings that control simulation execution.

This file contains settings for:
- total simulated time;
- numerical integration step;
- GUI refresh frequency;
- whether the graphical window should be shown.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class SimulationSettings:
    """Groups together runtime settings for the solver and the GUI."""

    duration_seconds: float = 600.0
    integration_step_seconds: float = 0.05
    frame_interval_ms: int = 50
    integration_steps_per_frame: int = 4
    show_plots: bool = True


# Default settings used by the application entry point.
DEFAULT_SETTINGS = SimulationSettings()
