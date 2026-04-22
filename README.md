# Gas System Simulation

Simple project for modeling pressure drop in a vessel with krypton flowing out through a small hole.

## Structure

- `src/gas_system_sim/settings.py` - integration step and UI update settings.
- `src/gas_system_sim/system_config.py` - vessel parameters in user units with SI conversion helpers.
- `src/gas_system_sim/physical_constants.py` - krypton constants and thermodynamic parameters.
- `src/gas_system_sim/math_model.py` - ideal-gas pressure and orifice outflow formulas.
- `src/gas_system_sim/simulation_engine.py` - orchestration of time stepping and result accumulation.
- `src/gas_system_sim/plot_window.py` - real-time plot window with `Start` and `Stop`.
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

The window shows pressure in bar versus time in seconds and updates the axes automatically as new points appear.

## Tests

```powershell
$env:PYTHONPATH="src"
py -m unittest discover -s tests
```
