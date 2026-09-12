"""build_core(core=None) — the viva-ketchup core.

Cross-repo convention: create a fresh process-bigraph core (or compose onto the
passed one), then register THIS repo's own process/step classes by name so they
are first-class, browsable dashboard Registry entries.  Uniform across
viva-/pbg- repos.

viva-ketchup's processes are the KETCHUP kinetic-parameter estimators
:class:`KetchupEstimator` and :class:`KetchupDynamicEstimator` (both
:class:`process_bigraph.Step` subclasses in :mod:`viva_ketchup.processes`).
"""
from process_bigraph import allocate_core
from viva_superpowers.core_compose import register_package_processes

from .processes import KetchupEstimator, KetchupDynamicEstimator

# This repo's own top-level package (…/core.py -> "viva_ketchup").
_PACKAGE = __name__.rsplit(".", 1)[0]


def build_core(core=None):
    core = core if core is not None else allocate_core()
    # Register THIS repo's own process/step classes as first-class, browsable
    # Registry entries (a composite that instantiates a process directly does
    # NOT auto-register it by name).
    register_package_processes(core, f"{_PACKAGE}.processes")
    # Belt-and-suspenders: the estimators are top-level imports, so register
    # them explicitly by name too (idempotent with the package scan above).
    for name, cls in (
        ("KetchupEstimator", KetchupEstimator),
        ("KetchupDynamicEstimator", KetchupDynamicEstimator),
    ):
        try:
            core.register_link(name, cls)
        except Exception:
            pass
    return core
