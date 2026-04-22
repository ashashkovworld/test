"""system_config.py: contains the user-facing configuration of the gas vessel.

The input values are intentionally stored in engineering units convenient for
the user: liters, kilograms, degrees Celsius, and millimeters.
Helper properties convert those values to SI units for the calculations.
"""

from dataclasses import dataclass
from math import pi


@dataclass(frozen=True)
class SystemConfiguration:
    """Defines the physical setup of the simulated vessel."""

    vessel_volume_liters: float = 22.0
    initial_gas_mass_kg: float = 1.0
    vessel_temperature_celsius: float = 20.0
    orifice_diameter_mm: float = 0.1
    ambient_pressure_bar: float = 1.01325
    discharge_coefficient: float = 0.8

    @property
    def vessel_volume_m3(self) -> float:
        """Converts vessel volume from liters to cubic meters."""

        return self.vessel_volume_liters / 1000.0

    @property
    def vessel_temperature_kelvin(self) -> float:
        """Converts Celsius to absolute temperature in kelvin."""

        return self.vessel_temperature_celsius + 273.15

    @property
    def orifice_diameter_m(self) -> float:
        """Converts hole diameter from millimeters to meters."""

        return self.orifice_diameter_mm / 1000.0

    @property
    def orifice_area_m2(self) -> float:
        """Computes the cross-sectional area of the round outlet hole."""

        radius_m = self.orifice_diameter_m / 2.0
        return pi * radius_m * radius_m

    @property
    def ambient_pressure_pa(self) -> float:
        """Converts ambient pressure from bar to pascals."""

        return self.ambient_pressure_bar * 100_000.0


# Default vessel configuration used in the example application.
DEFAULT_SYSTEM_CONFIG = SystemConfiguration()
