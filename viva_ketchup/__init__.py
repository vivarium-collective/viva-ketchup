"""viva-ketchup: process-bigraph wrapper for KETCHUP kinetic parameter estimation.

KETCHUP (Maranas group) fits the kinetic parameters of a metabolic network by
solving a single IPOPT nonlinear program against measured steady-state fluxes
and concentrations.  This package bridges the *real* ``ktools`` solver as a
process-bigraph :class:`~process_bigraph.Step`.
"""

from .processes import KetchupEstimator, KetchupDynamicEstimator
from .core import build_core

# Importing the composites subpackage fires the @composite_generator decorators.
from . import composites  # noqa: F401
from .composites import ketchup_baseline, ketchup_multistart, ketchup_dynamic

__all__ = [
    "KetchupEstimator",
    "KetchupDynamicEstimator",
    "build_core",
    "ketchup_baseline",
    "ketchup_multistart",
    "ketchup_dynamic",
]
