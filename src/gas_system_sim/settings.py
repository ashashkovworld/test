"""settings.py: stores global settings that control simulation execution.

This file contains settings for:
- optional total simulated time;
- numerical integration step;
- GUI refresh frequency;
- default speed relative to real time;
- whether the graphical window should be shown.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class SimulationSettings:
    """Groups together runtime settings for the solver and the GUI."""

    duration_seconds: Optional[float] = None
    integration_step_seconds: float = 0.05
    frame_interval_ms: int = 50
    default_real_time_speed: float = 1.0
    max_real_time_speed: float = 1_000_000.0
    show_plots: bool = True


# Default settings used by the application entry point.
DEFAULT_SETTINGS = SimulationSettings()
