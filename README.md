# Gas System Simulation

Configurable project for modeling a gas system assembled from reusable blocks.

## Structure

- `src/gas_system_sim/settings.py` - simulation timing and runtime UI settings.
- `src/gas_system_sim/system_config.py` - block graph, block properties, connections, and JSON-ready configuration model.
- `src/gas_system_sim/physical_constants.py` - krypton constants and thermodynamic parameters.
- `src/gas_system_sim/math_model.py` - local mathematical models for capacity, tube, valve, orifice, and environment blocks.
- `src/gas_system_sim/simulation_engine.py` - graph-based time stepping and history accumulation for all blocks.
- `src/gas_system_sim/configurator_window.py` - separate preprocessor window for building and editing the block scheme.
- `src/gas_system_sim/plot_window.py` - runtime dashboard and synchronized result windows for selected blocks.
- `src/gas_system_sim/main.py` - application entry point.
- `tests/test_simulation.py` - basic automated test.

## Run

Run from the repository root:

```powershell
py run_simulation.py
```

If you want to launch the package entry point file directly, this also works:

```powershell
py src/gas_system_sim/main.py
```

## Workflow

1. Open the separate configurator window.
2. Add or remove blocks: capacity, tube, valve, orifice, environment.
3. Connect blocks on the canvas and edit their parameters in the property panel.
4. Choose for each block whether a result window should open and which parameter should be plotted.
5. Save or load configurations as JSON inside the repository workspace.
6. Start the runtime dashboard from the configurator.

## Runtime UI

- The runtime dashboard is separate from the configurator.
- Each selected block opens in its own result window.
- The X axis is synchronized across all open result windows.
- The dashboard lets you start or stop time integration, change speed relative to real time, switch between autoscale and fixed moving time windows, and set a manual pressure scale or restore autoscale.
- Valve blocks can be toggled during the run. When a valve is closed, the corresponding flow stops while the time axis keeps advancing.

## Tests

```powershell
$env:PYTHONPATH="src"
py -m unittest discover -s tests
```
