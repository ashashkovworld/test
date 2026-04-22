"""physical_constants.py: stores gas properties and universal constants.

These values define the thermodynamic behavior of the working gas, krypton.
Derived helper properties convert the molar mass to SI units and compute the
specific gas constant needed by the ideal gas law.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class PhysicalConstants:
    """Collects physical constants used by the mathematical model."""

    molar_mass_g_mol: float = 83.798
    adiabatic_index: float = 1.4
    universal_gas_constant: float = 8.314

    @property
    def molar_mass_kg_mol(self) -> float:
        """Converts molar mass from grams per mole to kilograms per mole."""

        return self.molar_mass_g_mol / 1000.0

    @property
    def specific_gas_constant(self) -> float:
        """Computes the individual gas constant for krypton."""

        return self.universal_gas_constant / self.molar_mass_kg_mol


# Default physical constants used in the example simulation.
DEFAULT_PHYSICAL_CONSTANTS = PhysicalConstants()
