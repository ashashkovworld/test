"""plot_window.py: runtime dashboard and independent result windows.

The result UI is split into:
- one control window with Start/Stop and valve control;
- many optional plot windows, one per configured block chosen by the user.

Each plot window now owns its own axis settings so time and pressure scale can
be adjusted independently from other windows.
"""

from __future__ import annotations

from bisect import bisect_left
import os
import tkinter as tk
from time import monotonic
from pathlib import Path
from tkinter import ttk

from gas_system_sim.physical_constants import PhysicalConstants
from gas_system_sim.settings import SimulationSettings
from gas_system_sim.simulation_engine import SimulationEngine
from gas_system_sim.system_config import BlockConfig, PlotParameter, SystemConfiguration


def _prepare_matplotlib_environment() -> None:
    """Redirects matplotlib config into the repository workspace."""

    mpl_config_dir = Path(__file__).resolve().parents[2] / ".matplotlib"
    mpl_config_dir.mkdir(exist_ok=True)
    os.environ.setdefault("MPLCONFIGDIR", str(mpl_config_dir))


_prepare_matplotlib_environment()
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402


class BlockPlotWindow:
    """One separate result window for one configured block."""

    max_points_to_draw = 1500
    min_redraw_interval_seconds = 1.0 / 15.0

    def __init__(
        self,
        parent: tk.Misc,
        block: BlockConfig,
        engine: SimulationEngine,
        parameter: PlotParameter | None = None,
    ) -> None:
        self.block = block
        self.engine = engine
        self.parameter = block.plot_parameter if parameter is None else parameter
        self.window = tk.Toplevel(parent)
        self.window.title(f"{block.name} - {self.parameter}")
        self.window.geometry("760x520")
        self.static_view_enabled = tk.BooleanVar(value=False)
        self.time_window_seconds_var = tk.StringVar(value="30")
        self.pressure_autoscale_enabled = tk.BooleanVar(value=True)
        self.pressure_min_bar_var = tk.StringVar(value="0")
        self.pressure_max_bar_var = tk.StringVar(value="15")
        self.status_var = tk.StringVar(value="Ready")
        self.last_draw_timestamp = 0.0

        container = ttk.Frame(self.window, padding=8)
        container.pack(fill=tk.BOTH, expand=True)

        controls = ttk.Frame(container)
        controls.pack(fill=tk.X, pady=(0, 8))

        time_frame = ttk.LabelFrame(controls, text="Ось времени")
        time_frame.pack(fill=tk.X, pady=(0, 6))
        ttk.Checkbutton(
            time_frame,
            text="Статичное окно времени",
            variable=self.static_view_enabled,
            command=self.apply_axis_settings,
        ).grid(row=0, column=0, columnspan=3, sticky=tk.W, padx=6, pady=4)
        ttk.Label(time_frame, text="Окно, с").grid(row=1, column=0, sticky=tk.W, padx=6, pady=4)
        ttk.Entry(time_frame, textvariable=self.time_window_seconds_var, width=14).grid(
            row=1, column=1, sticky=tk.W, padx=6, pady=4
        )
        ttk.Button(time_frame, text="Применить", command=self.apply_axis_settings).grid(
            row=1, column=2, sticky=tk.W, padx=6, pady=4
        )

        pressure_frame = ttk.LabelFrame(controls, text="Ось давления")
        pressure_frame.pack(fill=tk.X)
        ttk.Checkbutton(
            pressure_frame,
            text="Автоскейл",
            variable=self.pressure_autoscale_enabled,
            command=self.apply_axis_settings,
        ).grid(row=0, column=0, columnspan=3, sticky=tk.W, padx=6, pady=4)
        ttk.Label(pressure_frame, text="P min, bar").grid(row=1, column=0, sticky=tk.W, padx=6, pady=4)
        ttk.Entry(
            pressure_frame,
            textvariable=self.pressure_min_bar_var,
            width=14,
        ).grid(row=1, column=1, sticky=tk.W, padx=6, pady=4)
        ttk.Label(pressure_frame, text="P max, bar").grid(row=2, column=0, sticky=tk.W, padx=6, pady=4)
        ttk.Entry(
            pressure_frame,
            textvariable=self.pressure_max_bar_var,
            width=14,
        ).grid(row=2, column=1, sticky=tk.W, padx=6, pady=4)
        ttk.Button(
            pressure_frame,
            text="Применить",
            command=self.apply_axis_settings,
        ).grid(row=1, column=2, rowspan=2, sticky=tk.NS, padx=6, pady=4)
        ttk.Label(container, textvariable=self.status_var).pack(anchor=tk.W, pady=(0, 6))

        self.figure = Figure(figsize=(6.4, 3.6), dpi=100)
        self.axis = self.figure.add_subplot(111)
        self.line = self.axis.plot([], [], color="#1f77b4", linewidth=2.0)[0]
        self.axis.set_xlabel("Time, s")
        self.axis.grid(True, alpha=0.3)

        self.canvas = FigureCanvasTkAgg(self.figure, master=container)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.closed = False

    def _time_window_seconds(self) -> float:
        """Returns the requested visible time span for this plot window."""

        return float(self.time_window_seconds_var.get().strip().replace(",", "."))

    def _pressure_limits_bar(self) -> tuple[float, float]:
        """Returns the manual pressure limits for this plot window."""

        pressure_min = float(self.pressure_min_bar_var.get().strip().replace(",", "."))
        pressure_max = float(self.pressure_max_bar_var.get().strip().replace(",", "."))
        return pressure_min, pressure_max

    def apply_axis_settings(self) -> None:
        """Validates and applies this window's own axis settings."""

        try:
            time_window = self._time_window_seconds()
            if time_window <= 0.0:
                raise ValueError
            if not self.pressure_autoscale_enabled.get() and self.block.plot_parameter == "pressure":
                pressure_min, pressure_max = self._pressure_limits_bar()
                if pressure_max <= pressure_min:
                    raise ValueError
            self.status_var.set("Настройки осей применены")
            self.update_plot(force=True)
        except ValueError:
            self.status_var.set("Ошибка в настройках осей")

    def _visible_series_slice(
        self,
        times: list[float],
        time_window_seconds: float,
    ) -> int:
        """Returns the first visible sample index for the current time policy."""

        if not times or not self.static_view_enabled.get():
            return 0
        latest_time = times[-1]
        x_min = max(0.0, latest_time - time_window_seconds)
        return bisect_left(times, x_min)

    def _downsample(
        self,
        times: list[float],
        values: list[float],
    ) -> tuple[list[float], list[float]]:
        """Reduces drawn points so many windows can stay responsive."""

        if len(times) <= self.max_points_to_draw:
            return times, values

        stride = max(1, len(times) // self.max_points_to_draw)
        sampled_times = times[::stride]
        sampled_values = values[::stride]

        if sampled_times[-1] != times[-1]:
            sampled_times.append(times[-1])
            sampled_values.append(values[-1])

        return sampled_times, sampled_values

    def close(self) -> None:
        """Marks the window closed and destroys the underlying Tk window."""

        self.closed = True
        self.window.destroy()

    def update_plot(self, force: bool = False) -> None:
        """Refreshes line data and applies this window's own axis policy."""

        if self.closed:
            return

        now = monotonic()
        if not force and now - self.last_draw_timestamp < self.min_redraw_interval_seconds:
            return
        self.last_draw_timestamp = now

        times = self.engine.result.times_seconds
        series = self.engine.result.block_series[self.block.block_id]

        if self.parameter == "temperature":
            y_values = series.temperature_celsius
            self.axis.set_ylabel("Temperature, °C")
        elif self.parameter == "flow":
            y_values = [value * 1_000_000.0 for value in series.flow_kg_s]
            self.axis.set_ylabel("Flow, mg/s")
        else:
            y_values = [value / 100_000.0 for value in series.pressure_pa]
            self.axis.set_ylabel("Pressure, bar")

        try:
            time_window_seconds = self._time_window_seconds()
        except ValueError:
            time_window_seconds = 30.0

        start_index = self._visible_series_slice(times, time_window_seconds)
        visible_times = times[start_index:]
        visible_values = y_values[start_index:]
        sampled_times, sampled_values = self._downsample(visible_times, visible_values)

        self.line.set_data(sampled_times, sampled_values)

        if self.static_view_enabled.get():
            latest_time = times[-1] if times else 0.0
            x_max = max(time_window_seconds, latest_time)
            self.axis.set_xlim(max(0.0, x_max - time_window_seconds), x_max)
        else:
            self.axis.relim()
            self.axis.autoscale_view(scalex=True, scaley=False)

        if self.parameter == "pressure" and not self.pressure_autoscale_enabled.get():
            try:
                pressure_min_bar, pressure_max_bar = self._pressure_limits_bar()
                if pressure_max_bar > pressure_min_bar:
                    self.axis.set_ylim(pressure_min_bar, pressure_max_bar)
            except ValueError:
                self.status_var.set("Ошибка в шкале давления")
        else:
            self.axis.relim()
            self.axis.autoscale_view(
                scalex=not self.static_view_enabled.get(),
                scaley=True,
            )

        self.canvas.draw_idle()


class SimulationDashboard:
    """Shared runtime dashboard that controls all result windows."""

    def __init__(
        self,
        parent: tk.Misc,
        settings: SimulationSettings,
        configuration: SystemConfiguration,
        constants: PhysicalConstants,
    ) -> None:
        self.parent = parent
        self.settings = settings
        self.configuration = configuration
        self.constants = constants
        self.engine = SimulationEngine(settings, configuration, constants)
        self.is_running = False
        self.real_time_speed = settings.default_real_time_speed
        self.time_carryover_seconds = 0.0
        self.plot_windows: list[BlockPlotWindow] = []
        self.timer_handle: str | None = None

        self.window = tk.Toplevel(parent)
        self.window.title("Simulation Dashboard")
        self.window.geometry("540x560")
        self.window.protocol("WM_DELETE_WINDOW", self.close)

        self.status_var = tk.StringVar(value="Status: ready")
        self.speed_var = tk.StringVar(value=f"{self.real_time_speed:g}")
        self.graph_block_var = tk.StringVar()
        self.graph_parameter_var = tk.StringVar(value="pressure")

        self._build_controls()
        self._open_plot_windows()
        self._schedule_timer()

    def _build_controls(self) -> None:
        """Builds the control widgets in the runtime dashboard."""

        frame = ttk.Frame(self.window, padding=12)
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frame, textvariable=self.status_var).pack(anchor=tk.W)

        button_row = ttk.Frame(frame)
        button_row.pack(fill=tk.X, pady=(12, 8))
        ttk.Button(button_row, text="Старт", command=self.start).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(button_row, text="Стоп", command=self.stop).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(button_row, text="Обновить окна", command=self.update_all_plots).pack(
            side=tk.LEFT
        )

        speed_frame = ttk.LabelFrame(frame, text="Скорость")
        speed_frame.pack(fill=tk.X, pady=6)
        ttk.Label(speed_frame, text="Относительно real time").grid(row=0, column=0, sticky=tk.W, padx=6, pady=6)
        ttk.Entry(speed_frame, textvariable=self.speed_var, width=18).grid(
            row=0, column=1, sticky=tk.W, padx=6, pady=6
        )
        ttk.Button(speed_frame, text="Применить", command=self.apply_speed).grid(
            row=0, column=2, sticky=tk.W, padx=6, pady=6
        )

        graph_frame = ttk.LabelFrame(frame, text="Добавить график во время расчета")
        graph_frame.pack(fill=tk.X, pady=6)
        available_blocks = [block.name for block in self.configuration.blocks]
        if available_blocks:
            self.graph_block_var.set(available_blocks[0])
        ttk.Label(graph_frame, text="Элемент").grid(row=0, column=0, sticky=tk.W, padx=6, pady=4)
        self.graph_block_combo = ttk.Combobox(
            graph_frame,
            textvariable=self.graph_block_var,
            values=available_blocks,
            state="readonly",
            width=24,
        )
        self.graph_block_combo.grid(row=0, column=1, sticky=tk.W, padx=6, pady=4)
        self.graph_block_combo.bind("<<ComboboxSelected>>", self.on_graph_block_selected)
        ttk.Label(graph_frame, text="Параметр").grid(row=1, column=0, sticky=tk.W, padx=6, pady=4)
        self.graph_parameter_combo = ttk.Combobox(
            graph_frame,
            textvariable=self.graph_parameter_var,
            values=(),
            state="readonly",
            width=24,
        )
        self.graph_parameter_combo.grid(row=1, column=1, sticky=tk.W, padx=6, pady=4)
        ttk.Button(graph_frame, text="Открыть график", command=self.open_selected_graph).grid(
            row=0, column=2, rowspan=2, sticky=tk.NS, padx=6, pady=4
        )
        self._refresh_graph_parameter_options()

        valves = [block for block in self.configuration.blocks if block.kind == "valve"]
        if valves:
            valve_frame = ttk.LabelFrame(frame, text="Клапаны")
            valve_frame.pack(fill=tk.X, pady=6)
            for row, block in enumerate(valves):
                state_var = tk.StringVar(value=self._valve_button_text(block.block_id))
                button = ttk.Button(
                    valve_frame,
                    textvariable=state_var,
                    command=lambda block_id=block.block_id, var=state_var: self.toggle_valve(block_id, var),
                )
                button.grid(row=row, column=0, sticky=tk.W, padx=6, pady=4)

        info_frame = ttk.LabelFrame(frame, text="Окна графиков")
        info_frame.pack(fill=tk.BOTH, expand=True, pady=6)
        for block in self.configuration.blocks:
            state = "открывается" if block.plot_enabled else "не открывается"
            ttk.Label(
                info_frame,
                text=f"{block.name}: {block.plot_parameter}, {state}",
            ).pack(anchor=tk.W, padx=6, pady=2)

    def _open_plot_windows(self) -> None:
        """Creates separate result windows for blocks marked in the config."""

        for block in self.configuration.blocks:
            if not block.plot_enabled:
                continue
            self.plot_windows.append(
                BlockPlotWindow(
                    self.window,
                    block,
                    self.engine,
                    parameter=block.plot_parameter,
                )
            )
        self.update_all_plots()

    def _block_by_name(self, block_name: str) -> BlockConfig | None:
        """Returns the block matching the visible name in the dashboard."""

        for block in self.configuration.blocks:
            if block.name == block_name:
                return block
        return None

    def _parameter_options_for_block(self, block: BlockConfig) -> list[str]:
        """Returns the supported plot parameters for the selected block."""

        options = ["pressure", "temperature"]
        if block.kind in {"tube", "valve", "orifice"}:
            options.append("flow")
        return options

    def _refresh_graph_parameter_options(self) -> None:
        """Refreshes runtime graph parameter choices for the selected block."""

        block = self._block_by_name(self.graph_block_var.get())
        if block is None:
            self.graph_parameter_combo.configure(values=[])
            return
        options = self._parameter_options_for_block(block)
        self.graph_parameter_combo.configure(values=options)
        if self.graph_parameter_var.get() not in options:
            self.graph_parameter_var.set(options[0])

    def on_graph_block_selected(self, _event: tk.Event) -> None:
        """Updates available plot parameters after a block selection change."""

        self._refresh_graph_parameter_options()

    def open_selected_graph(self) -> None:
        """Opens a new graph window for the chosen block and parameter."""

        block = self._block_by_name(self.graph_block_var.get())
        if block is None:
            self.status_var.set("Status: no block selected for plotting")
            return
        parameter = self.graph_parameter_var.get()
        self.plot_windows.append(
            BlockPlotWindow(
                self.window,
                block,
                self.engine,
                parameter=parameter,
            )
        )
        self.status_var.set(f"Status: graph opened for {block.name} ({parameter})")
        self.update_all_plots(force=True)

    def _valve_button_text(self, block_id: str) -> str:
        """Returns a readable label for one valve toggle button."""

        block = self.configuration.get_block(block_id)
        return f"{block.name}: {'открыт' if block.is_open else 'закрыт'}"

    def start(self) -> None:
        """Starts the simulation timeline."""

        self.is_running = True
        self.status_var.set("Status: running")

    def stop(self) -> None:
        """Stops the simulation timeline."""

        self.is_running = False
        self.status_var.set("Status: stopped")

    def apply_speed(self) -> None:
        """Applies the requested speed multiplier."""

        try:
            candidate = float(self.speed_var.get().strip().replace(",", "."))
            if candidate <= 0.0:
                raise ValueError
            self.real_time_speed = min(candidate, self.settings.max_real_time_speed)
            self.speed_var.set(f"{self.real_time_speed:g}")
            self.status_var.set("Status: speed updated")
        except ValueError:
            self.status_var.set("Status: invalid speed")

    def toggle_valve(self, block_id: str, state_var: tk.StringVar) -> None:
        """Opens or closes one valve block during the running simulation."""

        current_state = self.configuration.get_block(block_id).is_open
        next_state = not current_state
        self.engine.set_valve_open(block_id, next_state)
        self.configuration.get_block(block_id).is_open = next_state
        state_var.set(self._valve_button_text(block_id))
        valve_name = self.configuration.get_block(block_id).name
        valve_state = "opened" if next_state else "closed"
        self.status_var.set(f"Status: {valve_name} {valve_state}")

        # Force an immediate redraw so the user can see that the model has
        # already switched to the new valve state before the next timer tick.
        self.update_all_plots(force=True)

    def update_all_plots(self, force: bool = False) -> None:
        """Refreshes every open block plot using each window's own settings."""

        self.plot_windows = [window for window in self.plot_windows if not window.closed]
        for plot_window in self.plot_windows:
            plot_window.update_plot(force=force)

    def _tick(self) -> None:
        """Advances simulation time according to the chosen real-time speed."""

        if self.is_running:
            self.time_carryover_seconds += (
                self.settings.frame_interval_ms / 1000.0 * self.real_time_speed
            )
            steps_to_run = int(
                self.time_carryover_seconds / self.settings.integration_step_seconds
            )
            self.time_carryover_seconds -= (
                steps_to_run * self.settings.integration_step_seconds
            )

            for _ in range(steps_to_run):
                self.engine.step()

            if steps_to_run > 0:
                self.update_all_plots()

        self._schedule_timer()

    def _schedule_timer(self) -> None:
        """Schedules the next Tk timer callback."""

        self.timer_handle = self.window.after(self.settings.frame_interval_ms, self._tick)

    def close(self) -> None:
        """Stops timers and closes every plot window belonging to this run."""

        self.is_running = False
        if self.timer_handle is not None:
            self.window.after_cancel(self.timer_handle)
            self.timer_handle = None
        for plot_window in list(self.plot_windows):
            if not plot_window.closed:
                plot_window.close()
        self.window.destroy()


def show_results_window(
    parent: tk.Misc,
    settings: SimulationSettings,
    configuration: SystemConfiguration,
    constants: PhysicalConstants,
) -> SimulationDashboard:
    """Creates the runtime dashboard and all requested plot windows."""

    return SimulationDashboard(
        parent=parent,
        settings=settings,
        configuration=configuration,
        constants=constants,
    )
