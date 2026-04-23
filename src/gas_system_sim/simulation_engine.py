"""simulation_engine.py: orchestrates the block-based gas-system calculation.

The engine owns the evolving physical state:
- gas masses inside every explicit storage-like block, including tubes;
- open or closed state of every valve;
- history arrays used by plotting windows.

The actual local formulas stay in ``math_model.py``. This module combines them
across the block graph assembled by the configurator.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from math import ceil

from gas_system_sim.math_model import (
    PathFlowReport,
    block_effective_area_m2,
    block_has_flow_model,
    block_is_storage,
    capacity_equilibrium_mass_kg,
    capacity_pressure_pa,
    compressible_mass_flow_kg_s,
    environment_pressure_pa,
    representative_path_temperature_kelvin,
    tube_equilibrium_mass_kg,
    tube_pressure_pa,
)
from gas_system_sim.physical_constants import PhysicalConstants
from gas_system_sim.settings import SimulationSettings
from gas_system_sim.system_config import BlockConfig, ConnectionConfig, SystemConfiguration


MAX_INTERNAL_INTEGRATION_STEP_SECONDS = 0.001


@dataclass
class BlockTimeSeries:
    """Stores the simulated time series for one block."""

    pressure_pa: list[float] = field(default_factory=list)
    temperature_celsius: list[float] = field(default_factory=list)
    mass_kg: list[float] = field(default_factory=list)
    flow_kg_s: list[float] = field(default_factory=list)


@dataclass
class SimulationResult:
    """Stores the common time axis and all block-level histories."""

    times_seconds: list[float] = field(default_factory=list)
    block_series: dict[str, BlockTimeSeries] = field(default_factory=dict)


class SimulationEngine:
    """Advances the configured block network in time."""

    def __init__(
        self,
        settings: SimulationSettings,
        configuration: SystemConfiguration,
        constants: PhysicalConstants,
    ) -> None:
        self.settings = settings
        self.configuration = configuration
        self.constants = constants
        self.time_seconds = 0.0

        self._explicit_blocks_by_id: dict[str, BlockConfig] = {
            block.block_id: block for block in self.configuration.blocks
        }
        self._all_blocks_by_id: dict[str, BlockConfig] = dict(self._explicit_blocks_by_id)

        # Valve state is copied from the configuration so runtime toggles do not
        # mutate the saved configuration object unless the caller chooses to.
        self.valve_states: dict[str, bool] = {
            block.block_id: block.is_open
            for block in self.configuration.blocks
            if block.kind == "valve"
        }

        self._adjacency = self._build_adjacency(self.configuration.connections)
        self._storage_ids = [
            block_id
            for block_id, block in self._all_blocks_by_id.items()
            if block_is_storage(block)
        ]

        # Every finite-volume element owns its own gas mass state.
        self.storage_masses_kg: dict[str, float] = {}
        for block_id in self._storage_ids:
            block = self._all_blocks_by_id[block_id]
            if block.kind == "capacity":
                self.storage_masses_kg[block_id] = block.initial_mass_kg
            elif block.kind == "tube":
                self.storage_masses_kg[block_id] = self._initial_explicit_tube_mass_kg(
                    block_id
                )

        self._storage_segments = self._discover_storage_segments()

        self.result = SimulationResult(
            block_series={
                block.block_id: BlockTimeSeries() for block in self.configuration.blocks
            }
        )
        self._record_current_state()

    def _build_adjacency(
        self,
        connections: list[ConnectionConfig],
    ) -> dict[str, list[str]]:
        """Builds an undirected adjacency list from graph connections."""

        adjacency: dict[str, list[str]] = defaultdict(list)
        for connection in connections:
            adjacency[connection.source_block_id].append(connection.target_block_id)
            adjacency[connection.target_block_id].append(connection.source_block_id)
        return dict(adjacency)

    def _block_by_id(self, block_id: str) -> BlockConfig:
        """Short helper for looking up blocks inside the active graph."""

        return self._all_blocks_by_id[block_id]

    def _storage_pressures_pa(
        self,
        masses_kg: dict[str, float] | None = None,
    ) -> dict[str, float]:
        """Returns current pressures for every storage-like node."""

        active_masses = self.storage_masses_kg if masses_kg is None else masses_kg
        pressures: dict[str, float] = {}
        for block_id in self._storage_ids:
            block = self._block_by_id(block_id)
            if block.kind == "environment":
                pressures[block_id] = environment_pressure_pa(block)
            elif block.kind == "capacity":
                pressures[block_id] = capacity_pressure_pa(
                    block,
                    active_masses[block_id],
                    self.constants,
                )
            else:
                pressures[block_id] = tube_pressure_pa(
                    block,
                    active_masses[block_id],
                    self.constants,
                )
        return pressures

    def _initial_storage_pressure_pa(self, block_id: str) -> float:
        """Returns an initial reference pressure for already-configured storages."""

        block = self._block_by_id(block_id)
        if block.kind == "capacity":
            return capacity_pressure_pa(block, block.initial_mass_kg, self.constants)
        if block.kind == "environment":
            return environment_pressure_pa(block)
        if block.kind == "tube":
            return 101_325.0
        return 101_325.0

    def _initial_explicit_tube_mass_kg(self, block_id: str) -> float:
        """Seeds explicit tubes from neighboring storage pressure when possible.

        This keeps a user-visible tube that is already part of the assembled
        tract from starting as an artificial vacuum.
        """

        reference_pressures_pa: list[float] = []
        for neighbor_id in self._adjacency.get(block_id, []):
            neighbor = self._block_by_id(neighbor_id)
            if neighbor.kind in {"capacity", "environment"}:
                reference_pressures_pa.append(
                    self._initial_storage_pressure_pa(neighbor_id)
                )

        if not reference_pressures_pa:
            return 0.0

        return tube_equilibrium_mass_kg(
            block=self._block_by_id(block_id),
            ambient_pressure_pa=sum(reference_pressures_pa) / len(reference_pressures_pa),
            constants=self.constants,
        )

    def _discover_storage_segments(self) -> list[list[str]]:
        """Finds graph segments that connect one storage node to another."""

        segments: list[list[str]] = []
        seen_signatures: set[tuple[str, ...]] = set()

        def dfs(start_id: str, current_id: str, visited: set[str], trail: list[str]) -> None:
            for neighbor_id in self._adjacency.get(current_id, []):
                if neighbor_id in visited:
                    continue

                neighbor_block = self._block_by_id(neighbor_id)
                if current_id != start_id and block_is_storage(self._block_by_id(current_id)):
                    return

                next_trail = trail + [neighbor_id]
                if block_is_storage(neighbor_block):
                    if neighbor_id == start_id:
                        continue
                    signature = tuple(next_trail)
                    canonical = min(signature, tuple(reversed(signature)))
                    if canonical not in seen_signatures:
                        seen_signatures.add(canonical)
                        segments.append(next_trail)
                    continue

                visited.add(neighbor_id)
                dfs(start_id, neighbor_id, visited, next_trail)
                visited.remove(neighbor_id)

        for start_id in self._storage_ids:
            dfs(start_id, start_id, {start_id}, [start_id])

        return segments

    def _segment_effective_area_m2(self, segment_ids: list[str]) -> float:
        """Returns the bottleneck area for one storage-to-storage segment."""

        areas_m2: list[float] = []
        for index, block_id in enumerate(segment_ids):
            block = self._block_by_id(block_id)
            is_endpoint = index in {0, len(segment_ids) - 1}
            if block.kind == "tube":
                areas_m2.append(block_effective_area_m2(block))
                continue
            if not is_endpoint and block_has_flow_model(block):
                areas_m2.append(block_effective_area_m2(block))

        if not areas_m2:
            return float("inf")
        return min(areas_m2)

    def _resolve_segment_reports(
        self,
        masses_kg: dict[str, float] | None = None,
    ) -> list[PathFlowReport]:
        """Builds resolved flow reports for every active segment."""

        storage_pressures = self._storage_pressures_pa(masses_kg)
        reports: list[PathFlowReport] = []

        for segment_ids in self._storage_segments:
            start_id = segment_ids[0]
            end_id = segment_ids[-1]
            start_pressure_pa = storage_pressures[start_id]
            end_pressure_pa = storage_pressures[end_id]
            if start_pressure_pa == end_pressure_pa:
                continue

            if start_pressure_pa > end_pressure_pa:
                upstream_id = start_id
                downstream_id = end_id
                upstream_pressure_pa = start_pressure_pa
                downstream_pressure_pa = end_pressure_pa
                traversed_ids = segment_ids
            else:
                upstream_id = end_id
                downstream_id = start_id
                upstream_pressure_pa = end_pressure_pa
                downstream_pressure_pa = start_pressure_pa
                traversed_ids = list(reversed(segment_ids))

            traversed_blocks = [self._block_by_id(block_id) for block_id in traversed_ids]
            effective_area_m2 = self._segment_effective_area_m2(traversed_ids)
            representative_temperature_kelvin = representative_path_temperature_kelvin(
                traversed_blocks
            )
            mass_flow_kg_s = compressible_mass_flow_kg_s(
                upstream_pressure_pa=upstream_pressure_pa,
                downstream_pressure_pa=downstream_pressure_pa,
                effective_area_m2=effective_area_m2,
                representative_temperature_kelvin=representative_temperature_kelvin,
                constants=self.constants,
            )
            reports.append(
                PathFlowReport(
                    upstream_block_id=upstream_id,
                    downstream_block_id=downstream_id,
                    traversed_block_ids=traversed_ids,
                    upstream_pressure_pa=upstream_pressure_pa,
                    downstream_pressure_pa=downstream_pressure_pa,
                    mass_flow_kg_s=mass_flow_kg_s,
                    representative_temperature_kelvin=representative_temperature_kelvin,
                )
            )

        return reports

    def _storage_mass_derivatives_kg_s(
        self,
        masses_kg: dict[str, float] | None = None,
    ) -> dict[str, float]:
        """Returns ``dm/dt`` for every finite-volume node in the graph."""

        derivatives = {block_id: 0.0 for block_id in self.storage_masses_kg}
        for report in self._resolve_segment_reports(masses_kg):
            if report.upstream_block_id in derivatives:
                derivatives[report.upstream_block_id] -= report.mass_flow_kg_s
            if report.downstream_block_id in derivatives:
                derivatives[report.downstream_block_id] += report.mass_flow_kg_s
        return derivatives

    def _equilibrium_mass_kg(self, block_id: str, target_pressure_pa: float) -> float:
        """Returns storage mass that corresponds to ``target_pressure_pa``."""

        block = self._block_by_id(block_id)
        if block.kind == "capacity":
            return capacity_equilibrium_mass_kg(
                block=block,
                ambient_pressure_pa=target_pressure_pa,
                constants=self.constants,
            )
        if block.kind == "tube":
            return tube_equilibrium_mass_kg(
                block=block,
                ambient_pressure_pa=target_pressure_pa,
                constants=self.constants,
            )
        return 0.0

    def _advance_storage_masses(self) -> None:
        """Advances all finite-volume nodes using stable internal substeps."""

        total_step_seconds = self.settings.integration_step_seconds
        substep_count = max(
            1,
            ceil(total_step_seconds / MAX_INTERNAL_INTEGRATION_STEP_SECONDS),
        )
        substep_seconds = total_step_seconds / substep_count

        for _ in range(substep_count):
            mass_deltas_kg = {block_id: 0.0 for block_id in self.storage_masses_kg}
            for report in self._resolve_segment_reports():
                transferred_mass_kg = report.mass_flow_kg_s * substep_seconds

                if report.upstream_block_id in self.storage_masses_kg:
                    available_mass_kg = self.storage_masses_kg[report.upstream_block_id]
                    available_until_equilibrium_kg = available_mass_kg - self._equilibrium_mass_kg(
                        report.upstream_block_id,
                        report.downstream_pressure_pa,
                    )
                    transferred_mass_kg = min(
                        transferred_mass_kg,
                        max(available_mass_kg, 0.0),
                        max(available_until_equilibrium_kg, 0.0),
                    )

                if report.downstream_block_id in self.storage_masses_kg:
                    downstream_capacity_kg = self._equilibrium_mass_kg(
                        report.downstream_block_id,
                        report.upstream_pressure_pa,
                    ) - self.storage_masses_kg[report.downstream_block_id]
                    transferred_mass_kg = min(
                        transferred_mass_kg,
                        max(downstream_capacity_kg, 0.0),
                    )

                if transferred_mass_kg <= 0.0:
                    continue

                if report.upstream_block_id in mass_deltas_kg:
                    mass_deltas_kg[report.upstream_block_id] -= transferred_mass_kg
                if report.downstream_block_id in mass_deltas_kg:
                    mass_deltas_kg[report.downstream_block_id] += transferred_mass_kg

            for block_id, delta_mass_kg in mass_deltas_kg.items():
                self.storage_masses_kg[block_id] = max(
                    self.storage_masses_kg[block_id] + delta_mass_kg,
                    0.0,
                )

    def _estimate_nonstorage_pressure_pa(
        self,
        block_id: str,
        reports: list[PathFlowReport],
        storage_pressures_pa: dict[str, float],
    ) -> float:
        """Estimates display pressure for non-storage blocks.

        These blocks do not own mass state, so the displayed pressure is a
        weighted midpoint of the storage pressures around the active segment.
        """

        weighted_sum = 0.0
        total_flow = 0.0
        for report in reports:
            if block_id not in report.traversed_block_ids:
                continue
            midpoint_pressure = 0.5 * (
                report.upstream_pressure_pa + report.downstream_pressure_pa
            )
            weighted_sum += midpoint_pressure * report.mass_flow_kg_s
            total_flow += report.mass_flow_kg_s

        if total_flow > 0.0:
            return weighted_sum / total_flow

        neighbor_pressures: list[float] = []
        for neighbor_id in self._adjacency.get(block_id, []):
            if neighbor_id in storage_pressures_pa:
                neighbor_pressures.append(storage_pressures_pa[neighbor_id])

        if neighbor_pressures:
            return sum(neighbor_pressures) / len(neighbor_pressures)

        return 101_325.0

    def _record_current_state(self) -> None:
        """Converts the current engine state into plot-friendly history arrays."""

        reports = self._resolve_segment_reports()
        storage_pressures_pa = self._storage_pressures_pa()
        block_flows_kg_s: dict[str, float] = defaultdict(float)

        for report in reports:
            for block_id in report.traversed_block_ids:
                if block_id in self.result.block_series:
                    block_flows_kg_s[block_id] += report.mass_flow_kg_s

        self.result.times_seconds.append(self.time_seconds)

        for block in self.configuration.blocks:
            series = self.result.block_series[block.block_id]
            series.temperature_celsius.append(block.temperature_celsius)
            series.flow_kg_s.append(block_flows_kg_s.get(block.block_id, 0.0))

            if block.kind == "environment":
                series.mass_kg.append(0.0)
                series.pressure_pa.append(environment_pressure_pa(block))
                continue

            if block.kind in {"capacity", "tube"}:
                mass_kg = self.storage_masses_kg[block.block_id]
                series.mass_kg.append(mass_kg)
                series.pressure_pa.append(storage_pressures_pa[block.block_id])
                continue

            series.mass_kg.append(0.0)
            series.pressure_pa.append(
                self._estimate_nonstorage_pressure_pa(
                    block_id=block.block_id,
                    reports=reports,
                    storage_pressures_pa=storage_pressures_pa,
                )
            )

    def is_complete(self) -> bool:
        """Returns ``True`` only when a finite horizon is configured and reached."""

        if self.settings.duration_seconds is None:
            return False
        return self.time_seconds >= self.settings.duration_seconds

    def set_valve_open(self, block_id: str, is_open: bool) -> None:
        """Updates one valve state during the running simulation."""

        if block_id not in self.valve_states:
            return
        self.valve_states[block_id] = is_open
        self._block_by_id(block_id).is_open = is_open

    def step(self) -> None:
        """Advances the network by one integration step and records histories."""

        if self.is_complete():
            return

        self._advance_storage_masses()
        self.time_seconds += self.settings.integration_step_seconds
        self._record_current_state()


def run_simulation(
    settings: SimulationSettings,
    configuration: SystemConfiguration,
    constants: PhysicalConstants,
) -> SimulationResult:
    """Runs the full simulation until the configured end time."""

    if settings.duration_seconds is None:
        raise RuntimeError(
            "run_simulation requires a finite duration_seconds value in settings."
        )

    engine = SimulationEngine(
        settings=settings,
        configuration=configuration,
        constants=constants,
    )
    while not engine.is_complete():
        engine.step()
    return engine.result
