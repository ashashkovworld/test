"""configurator_window.py: graphical preprocessor for assembling system models.

The configurator is a dedicated window that appears before the calculation.
It lets the user:
- add and remove blocks;
- connect blocks graphically on a canvas;
- edit block parameters;
- choose which result windows should open later;
- save and load the assembled configuration as JSON.
"""

from __future__ import annotations

import json
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from gas_system_sim.physical_constants import PhysicalConstants
from gas_system_sim.plot_window import show_results_window
from gas_system_sim.settings import SimulationSettings
from gas_system_sim.system_config import (
    BLOCK_EDITABLE_FIELDS,
    BlockKind,
    DEFAULT_SYSTEM_CONFIG,
    SystemConfiguration,
    build_block,
    new_block_id,
)


FIELD_LABELS: dict[str, str] = {
    "name": "Имя",
    "x": "X",
    "y": "Y",
    "temperature_celsius": "Температура, °C",
    "volume_liters": "Объем, л",
    "initial_mass_kg": "Стартовая масса, кг",
    "diameter_mm": "Диаметр, мм",
    "length_m": "Длина, м",
    "pressure_bar": "Давление, bar",
    "is_open": "Открыт",
    "plot_enabled": "Открыть окно графика",
    "plot_parameter": "Параметр графика",
    "flow": "Расход",
}


class ConfiguratorWindow:
    """Main preprocessor window used before opening result plots."""

    def __init__(
        self,
        root: tk.Tk,
        settings: SimulationSettings,
        constants: PhysicalConstants,
        configuration: SystemConfiguration | None = None,
    ) -> None:
        self.root = root
        self.settings = settings
        self.constants = constants
        source_configuration = configuration or DEFAULT_SYSTEM_CONFIG
        self.configuration = SystemConfiguration.from_dict(source_configuration.to_dict())
        self.selected_block_id: str | None = None
        self.selected_connection_index: int | None = None
        self.connect_mode_source_id: str | None = None
        self.dragging_block_id: str | None = None
        self.drag_start_pointer: tuple[float, float] | None = None
        self.drag_offset: tuple[float, float] = (0.0, 0.0)
        self.drag_moved = False
        self.block_item_map: dict[int, str] = {}
        self.property_widgets: dict[str, tk.Variable] = {}
        self.connect_button_text = tk.StringVar(value="Соединить мышью")

        self.root.title("Gas System Configurator")
        self.root.geometry("1260x760")

        self._build_ui()
        self._redraw_canvas()
        self._refresh_block_list()
        self._refresh_connection_list()

    def _build_ui(self) -> None:
        """Builds all permanent widgets of the configurator window."""

        container = ttk.Frame(self.root, padding=12)
        container.pack(fill=tk.BOTH, expand=True)

        toolbar = ttk.Frame(container)
        toolbar.pack(fill=tk.X, pady=(0, 8))
        ttk.Button(toolbar, text="Добавить емкость", command=lambda: self.add_block("capacity")).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(toolbar, text="Добавить трубку", command=lambda: self.add_block("tube")).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(toolbar, text="Добавить клапан", command=lambda: self.add_block("valve")).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(toolbar, text="Добавить дроссель", command=lambda: self.add_block("orifice")).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(toolbar, text="Добавить среду", command=lambda: self.add_block("environment")).pack(side=tk.LEFT, padx=(0, 18))
        ttk.Button(toolbar, text="Сохранить", command=self.save_configuration).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(toolbar, text="Загрузить", command=self.load_configuration).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(toolbar, text="Запустить расчет", command=self.run_simulation).pack(side=tk.LEFT, padx=(0, 6))

        body = ttk.Panedwindow(container, orient=tk.HORIZONTAL)
        body.pack(fill=tk.BOTH, expand=True)

        canvas_frame = ttk.Frame(body)
        side_frame = ttk.Frame(body)
        body.add(canvas_frame, weight=3)
        body.add(side_frame, weight=2)

        self.canvas = tk.Canvas(canvas_frame, background="white", highlightthickness=1)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.canvas.bind("<ButtonPress-1>", self.on_canvas_press)
        self.canvas.bind("<B1-Motion>", self.on_canvas_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_canvas_release)

        list_frame = ttk.LabelFrame(side_frame, text="Блоки")
        list_frame.pack(fill=tk.BOTH, expand=False, pady=(0, 8))
        self.block_listbox = tk.Listbox(list_frame, height=10)
        self.block_listbox.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)
        self.block_listbox.bind("<<ListboxSelect>>", self.on_block_list_select)
        ttk.Button(list_frame, text="Удалить выбранный блок", command=self.delete_selected_block).pack(
            anchor=tk.W, padx=6, pady=(0, 6)
        )

        connection_frame = ttk.LabelFrame(side_frame, text="Соединения")
        connection_frame.pack(fill=tk.BOTH, expand=False, pady=(0, 8))
        self.connection_listbox = tk.Listbox(connection_frame, height=8)
        self.connection_listbox.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)
        self.connection_listbox.bind("<<ListboxSelect>>", self.on_connection_select)
        button_row = ttk.Frame(connection_frame)
        button_row.pack(fill=tk.X, padx=6, pady=(0, 6))
        ttk.Button(
            button_row,
            textvariable=self.connect_button_text,
            command=self.toggle_connect_mode,
        ).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(button_row, text="Удалить соединение", command=self.delete_selected_connection).pack(side=tk.LEFT)

        self.properties_frame = ttk.LabelFrame(side_frame, text="Свойства блока")
        self.properties_frame.pack(fill=tk.BOTH, expand=True)

    def add_block(self, kind: BlockKind) -> None:
        """Adds a new block of the requested kind to the configuration."""

        block_id = new_block_id(self.configuration, kind)
        x = 120.0 + 40.0 * len(self.configuration.blocks)
        y = 120.0 + 20.0 * (len(self.configuration.blocks) % 8)
        block = build_block(block_id, kind, x, y)
        self.configuration.blocks.append(block)
        self.select_block(block.block_id)

    def _refresh_block_list(self) -> None:
        """Updates the block listbox from the current configuration."""

        self.block_listbox.delete(0, tk.END)
        for block in self.configuration.blocks:
            self.block_listbox.insert(tk.END, f"{block.name} [{block.kind}]")

    def _refresh_connection_list(self) -> None:
        """Updates the connection listbox from the current configuration."""

        self.connection_listbox.delete(0, tk.END)
        for connection in self.configuration.connections:
            source_name = self.configuration.get_block(connection.source_block_id).name
            target_name = self.configuration.get_block(connection.target_block_id).name
            self.connection_listbox.insert(tk.END, f"{source_name} <-> {target_name}")

    def _redraw_canvas(self) -> None:
        """Redraws the model graph on the canvas."""

        self.canvas.delete("all")
        self.block_item_map.clear()

        for connection in self.configuration.connections:
            source = self.configuration.get_block(connection.source_block_id)
            target = self.configuration.get_block(connection.target_block_id)
            self.canvas.create_line(
                source.x,
                source.y,
                target.x,
                target.y,
                fill="#555555",
                width=2,
            )

        for block in self.configuration.blocks:
            width = 120
            height = 50
            fill = "#d9edf7"
            if block.kind == "capacity":
                fill = "#d6e9c6"
            elif block.kind == "valve":
                fill = "#f2dede" if not block.is_open else "#dff0d8"
            elif block.kind == "environment":
                fill = "#fcf8e3"

            rectangle = self.canvas.create_rectangle(
                block.x - width / 2,
                block.y - height / 2,
                block.x + width / 2,
                block.y + height / 2,
                fill=fill,
                outline="#2c3e50" if block.block_id == self.selected_block_id else "#808080",
                width=3 if block.block_id == self.selected_block_id else 1,
            )
            label = self.canvas.create_text(
                block.x,
                block.y,
                text=f"{block.name}\n{block.kind}",
                justify=tk.CENTER,
            )
            self.block_item_map[rectangle] = block.block_id
            self.block_item_map[label] = block.block_id

    def _block_id_at_canvas_position(self, x: float, y: float) -> str | None:
        """Returns the block under the mouse pointer, if any."""

        overlapping = self.canvas.find_overlapping(x, y, x, y)
        for item_id in reversed(overlapping):
            block_id = self.block_item_map.get(item_id)
            if block_id is not None:
                return block_id
        return None

    def select_block(self, block_id: str) -> None:
        """Selects one block and refreshes all related UI panels."""

        if self.selected_block_id is not None and self.selected_block_id != block_id:
            if not self._commit_property_widgets(show_errors=False):
                return

        self.selected_block_id = block_id
        self.selected_connection_index = None
        self._redraw_canvas()
        self._refresh_block_list()
        self._refresh_connection_list()
        self._show_properties_for_selected_block()

        index = next(
            (
                idx
                for idx, block in enumerate(self.configuration.blocks)
                if block.block_id == block_id
            ),
            None,
        )
        if index is not None:
            self.block_listbox.selection_clear(0, tk.END)
            self.block_listbox.selection_set(index)
            self.block_listbox.see(index)

    def _show_properties_for_selected_block(self) -> None:
        """Rebuilds the right-side property editor for the selected block."""

        for child in self.properties_frame.winfo_children():
            child.destroy()

        if self.selected_block_id is None:
            ttk.Label(self.properties_frame, text="Выберите блок на схеме").pack(
                anchor=tk.W, padx=8, pady=8
            )
            return

        block = self.configuration.get_block(self.selected_block_id)
        editable_fields = BLOCK_EDITABLE_FIELDS[block.kind]
        self.property_widgets.clear()

        editor = ttk.Frame(self.properties_frame, padding=8)
        editor.pack(fill=tk.BOTH, expand=True)
        editor.columnconfigure(1, weight=1)

        ttk.Button(
            editor,
            text="Применить настройки к блоку",
            command=self.apply_properties,
        ).grid(
            row=0,
            column=0,
            columnspan=2,
            sticky=tk.W,
            pady=(0, 10),
        )

        for row, field_name in enumerate(editable_fields, start=1):
            ttk.Label(editor, text=FIELD_LABELS[field_name]).grid(
                row=row,
                column=0,
                sticky=tk.W,
                padx=(0, 8),
                pady=4,
            )
            current_value = getattr(block, field_name)
            if field_name in {"is_open", "plot_enabled"}:
                variable = tk.BooleanVar(value=bool(current_value))
                ttk.Checkbutton(editor, variable=variable).grid(
                    row=row, column=1, sticky=tk.W, pady=4
                )
            elif field_name == "plot_parameter":
                variable = tk.StringVar(value=str(current_value))
                ttk.Combobox(
                    editor,
                    textvariable=variable,
                    values=("pressure", "temperature", "flow"),
                    state="readonly",
                    width=16,
                ).grid(row=row, column=1, sticky=tk.W, pady=4)
            else:
                variable = tk.StringVar(value=str(current_value))
                ttk.Entry(editor, textvariable=variable, width=22).grid(
                    row=row, column=1, sticky=tk.EW, pady=4
                )
            self.property_widgets[field_name] = variable

    def _commit_property_widgets(self, show_errors: bool) -> bool:
        """Copies editor values into the selected block.

        Returns ``True`` when the values were applied successfully.
        """

        if self.selected_block_id is None:
            return True

        block = self.configuration.get_block(self.selected_block_id)
        try:
            for field_name, variable in self.property_widgets.items():
                raw_value = variable.get()
                if field_name in {"name", "plot_parameter"}:
                    setattr(block, field_name, raw_value)
                elif field_name in {"is_open", "plot_enabled"}:
                    setattr(block, field_name, bool(raw_value))
                else:
                    setattr(block, field_name, float(str(raw_value).replace(",", ".")))
        except ValueError:
            if show_errors:
                messagebox.showerror(
                    "Ошибка",
                    "Не удалось применить настройки блока. Проверь числовые поля.",
                    parent=self.root,
                )
            return False

        self._redraw_canvas()
        self._refresh_block_list()
        return True

    def apply_properties(self) -> None:
        """Copies edited widget values back into the selected block."""

        if self._commit_property_widgets(show_errors=True):
            self.status_message("Свойства блока обновлены")

    def on_canvas_press(self, event: tk.Event) -> None:
        """Stores the initial mouse state for click, connect, or drag actions."""

        block_id = self._block_id_at_canvas_position(event.x, event.y)
        if block_id is None:
            self.dragging_block_id = None
            self.drag_start_pointer = None
            self.drag_moved = False
            return

        block = self.configuration.get_block(block_id)
        self.dragging_block_id = block_id
        self.drag_start_pointer = (event.x, event.y)
        self.drag_offset = (block.x - event.x, block.y - event.y)
        self.drag_moved = False

    def on_canvas_drag(self, event: tk.Event) -> None:
        """Moves the selected block with the mouse while dragging."""

        if self.dragging_block_id is None or self.drag_start_pointer is None:
            return
        if self.connect_mode_source_id is not None:
            return

        start_x, start_y = self.drag_start_pointer
        if abs(event.x - start_x) + abs(event.y - start_y) < 4:
            return

        self.drag_moved = True
        block = self.configuration.get_block(self.dragging_block_id)
        block.x = max(60.0, event.x + self.drag_offset[0])
        block.y = max(40.0, event.y + self.drag_offset[1])
        self.selected_block_id = block.block_id
        self._redraw_canvas()

    def on_canvas_release(self, event: tk.Event) -> None:
        """Finishes dragging or handles mouse-based object connection."""

        block_id = self._block_id_at_canvas_position(event.x, event.y)
        dragging_block_id = self.dragging_block_id
        drag_moved = self.drag_moved
        self.dragging_block_id = None
        self.drag_start_pointer = None
        self.drag_moved = False

        if dragging_block_id is not None and drag_moved:
            self.select_block(dragging_block_id)
            self.status_message("Положение блока обновлено")
            return

        if self.connect_mode_source_id is None:
            if block_id is not None:
                self.select_block(block_id)
            return

        if block_id is None:
            self.status_message("Для соединения выбери второй объект мышью")
            return

        if self.connect_mode_source_id == block_id:
            self.status_message("Нужно выбрать второй блок для соединения")
            return

        self.configuration.add_connection(self.connect_mode_source_id, block_id)
        self.connect_mode_source_id = None
        self.connect_button_text.set("Соединить мышью")
        self._redraw_canvas()
        self._refresh_connection_list()
        self.status_message("Соединение добавлено")

    def on_block_list_select(self, _event: tk.Event) -> None:
        """Selects a block when the user clicks it in the listbox."""

        selected_indices = self.block_listbox.curselection()
        if not selected_indices:
            return
        index = selected_indices[0]
        self.select_block(self.configuration.blocks[index].block_id)

    def on_connection_select(self, _event: tk.Event) -> None:
        """Stores the selected connection index from the listbox."""

        selected_indices = self.connection_listbox.curselection()
        if not selected_indices:
            self.selected_connection_index = None
            return
        self.selected_connection_index = selected_indices[0]

    def delete_selected_block(self) -> None:
        """Deletes the currently selected block."""

        if self.selected_block_id is None:
            return
        self.configuration.remove_block(self.selected_block_id)
        self.selected_block_id = None
        self.connect_mode_source_id = None
        self.connect_button_text.set("Соединить мышью")
        self._redraw_canvas()
        self._refresh_block_list()
        self._refresh_connection_list()
        self._show_properties_for_selected_block()
        self.status_message("Блок удален")

    def toggle_connect_mode(self) -> None:
        """Turns mouse-based connection mode on or off."""

        if self.connect_mode_source_id is not None:
            self.connect_mode_source_id = None
            self.connect_button_text.set("Соединить мышью")
            self.status_message("Режим соединения выключен")
            return

        if self.selected_block_id is None:
            self.status_message("Сначала выберите первый объект")
            return

        self.connect_mode_source_id = self.selected_block_id
        self.connect_button_text.set("Отменить соединение")
        source_name = self.configuration.get_block(self.selected_block_id).name
        self.status_message(f"Соединение: выбери второй объект для {source_name}")

    def delete_selected_connection(self) -> None:
        """Deletes the connection highlighted in the connection list."""

        if self.selected_connection_index is None:
            return
        del self.configuration.connections[self.selected_connection_index]
        self.selected_connection_index = None
        self._redraw_canvas()
        self._refresh_connection_list()
        self.status_message("Соединение удалено")

    def _workspace_path(self, candidate: Path) -> Path:
        """Ensures save and load stay inside the repository workspace."""

        workspace_root = Path(__file__).resolve().parents[2]
        resolved = candidate.resolve()
        if workspace_root == resolved or workspace_root in resolved.parents:
            return resolved
        raise ValueError("Operations outside the Codex workspace are not allowed.")

    def save_configuration(self) -> None:
        """Saves the current configuration to a JSON file in the workspace."""

        default_path = Path(__file__).resolve().parents[2] / "configurations"
        default_path.mkdir(exist_ok=True)
        target = filedialog.asksaveasfilename(
            parent=self.root,
            title="Сохранить конфигурацию",
            initialdir=str(default_path),
            defaultextension=".json",
            filetypes=[("JSON", "*.json")],
        )
        if not target:
            return

        try:
            resolved = self._workspace_path(Path(target))
            resolved.write_text(
                json.dumps(self.configuration.to_dict(), indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            self.status_message(f"Конфигурация сохранена: {resolved.name}")
        except ValueError as exc:
            messagebox.showerror("Ошибка", str(exc), parent=self.root)

    def load_configuration(self) -> None:
        """Loads a configuration JSON file from the workspace."""

        default_path = Path(__file__).resolve().parents[2] / "configurations"
        default_path.mkdir(exist_ok=True)
        target = filedialog.askopenfilename(
            parent=self.root,
            title="Загрузить конфигурацию",
            initialdir=str(default_path),
            filetypes=[("JSON", "*.json")],
        )
        if not target:
            return

        try:
            resolved = self._workspace_path(Path(target))
            loaded = SystemConfiguration.from_dict(
                json.loads(resolved.read_text(encoding="utf-8"))
            )
            self.configuration = loaded
            self.selected_block_id = None
            self.selected_connection_index = None
            self.connect_mode_source_id = None
            self.connect_button_text.set("Соединить мышью")
            self._redraw_canvas()
            self._refresh_block_list()
            self._refresh_connection_list()
            self._show_properties_for_selected_block()
            self.status_message(f"Конфигурация загружена: {resolved.name}")
        except ValueError as exc:
            messagebox.showerror("Ошибка", str(exc), parent=self.root)

    def run_simulation(self) -> None:
        """Opens the separate runtime dashboard for the current configuration."""

        if not self.configuration.blocks:
            messagebox.showwarning("Предупреждение", "Конфигурация пуста", parent=self.root)
            return
        if not self._commit_property_widgets(show_errors=True):
            return
        show_results_window(
            parent=self.root,
            settings=self.settings,
            configuration=SystemConfiguration.from_dict(self.configuration.to_dict()),
            constants=self.constants,
        )
        self.status_message("Расчетное окно открыто")

    def status_message(self, message: str) -> None:
        """Shows short feedback in the root window title."""

        self.root.title(f"Gas System Configurator - {message}")


def show_configurator_window(
    settings: SimulationSettings,
    constants: PhysicalConstants,
    configuration: SystemConfiguration | None = None,
) -> None:
    """Starts the dedicated configurator window and enters the Tk event loop."""

    root = tk.Tk()
    ConfiguratorWindow(
        root=root,
        settings=settings,
        constants=constants,
        configuration=configuration,
    )
    root.mainloop()
