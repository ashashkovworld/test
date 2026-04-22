"""plot_window.py: graphical interface for real-time visualization.

This module creates a matplotlib window that:
- shows vessel pressure versus time;
- provides Start and Stop buttons;
- advances the simulation in small batches to keep the UI responsive.
"""

import os
from pathlib import Path

from gas_system_sim.physical_constants import PhysicalConstants
from gas_system_sim.settings import SimulationSettings
from gas_system_sim.simulation_engine import SimulationEngine
from gas_system_sim.system_config import SystemConfiguration


def show_results_window(
    settings: SimulationSettings,
    configuration: SystemConfiguration,
    constants: PhysicalConstants,
) -> None:
    """Opens the real-time plot window and connects UI events to the engine."""

    # In restricted environments matplotlib may fail when it tries to keep
    # its config under the user profile. We redirect it to a local project
    # folder that is writable from inside this repository.
    mpl_config_dir = Path(__file__).resolve().parents[2] / ".matplotlib"
    mpl_config_dir.mkdir(exist_ok=True)
    os.environ.setdefault("MPLCONFIGDIR", str(mpl_config_dir))

    try:
        import matplotlib.pyplot as plt
        from matplotlib.widgets import Button
    except ImportError as exc:
        raise RuntimeError(
            "matplotlib is required to display plot windows. Install it with 'pip install matplotlib'."
        ) from exc

    # The engine performs the numerical work, while this module only handles UI.
    engine = SimulationEngine(settings=settings, configuration=configuration, constants=constants)

    # Flag indicating whether the timer should keep advancing the model.
    is_running = False

    figure, axis = plt.subplots()
    figure.canvas.manager.set_window_title("Gas Vessel Pressure")

    # Reserve extra space below the plot for the control buttons.
    figure.subplots_adjust(bottom=0.23)

    line, = axis.plot([], [], color="tab:blue", linewidth=2.0)
    axis.set_xlabel("Time, s")
    axis.set_ylabel("Pressure, bar")
    axis.grid(True, alpha=0.3)

    # A small status label helps understand whether the solver is idle,
    # running, stopped, or already complete.
    status = figure.text(0.12, 0.92, "Status: ready", fontsize=10)

    def update_plot() -> None:
        """Refreshes the curve and lets matplotlib rescale the axes."""

        times = engine.result.times_seconds
        pressures_bar = [pressure / 100_000.0 for pressure in engine.result.pressures_pa]
        line.set_data(times, pressures_bar)
        axis.relim()
        axis.autoscale_view()
        figure.canvas.draw_idle()

    def handle_timer() -> None:
        """Timer callback: advances the model in small batches for real time."""

        nonlocal is_running
        if not is_running:
            return

        for _ in range(settings.integration_steps_per_frame):
            if engine.is_complete():
                is_running = False
                status.set_text("Status: completed")
                break
            engine.step()

        update_plot()

    def start_simulation(_event) -> None:
        """Starts or restarts the simulation when the user presses Start."""

        nonlocal engine, is_running
        if engine.is_complete():
            # When the previous run has already ended, create a fresh engine
            # so the next Start begins again from the initial state.
            engine = SimulationEngine(
                settings=settings,
                configuration=configuration,
                constants=constants,
            )
        is_running = True
        status.set_text("Status: running")
        update_plot()

    def stop_simulation(_event) -> None:
        """Pauses further time integration when the user presses Stop."""

        nonlocal is_running
        is_running = False
        status.set_text("Status: stopped")
        figure.canvas.draw_idle()

    # Separate axes are used as containers for the button widgets.
    start_axis = figure.add_axes([0.12, 0.08, 0.16, 0.08])
    stop_axis = figure.add_axes([0.31, 0.08, 0.16, 0.08])
    start_button = Button(start_axis, "Старт")
    stop_button = Button(stop_axis, "Стоп")
    start_button.on_clicked(start_simulation)
    stop_button.on_clicked(stop_simulation)

    # The timer calls ``handle_timer`` periodically without blocking the GUI.
    timer = figure.canvas.new_timer(interval=settings.frame_interval_ms)
    timer.add_callback(handle_timer)
    timer.start()

    # Draw the initial point before entering the GUI event loop.
    update_plot()
    plt.show()
