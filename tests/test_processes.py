"""Tests for the KetchupEstimator process-bigraph Step.

Structural tests always run (no solver needed).  The end-to-end real-solve
test is skipped when IPOPT is not installed, so CI without the compiled solver
stays green while a fully-provisioned environment exercises the real bridge.
"""

import os

import pytest
from process_bigraph import allocate_core

from viva_ketchup import KetchupEstimator

EXPECTED_OUTPUTS = {
    "kf", "kr", "concentrations", "enzymes", "fluxes",
    "sse", "status", "solve_time", "n_parameters", "stability",
}


def _ipopt_available() -> bool:
    try:
        from pyomo.environ import SolverFactory
        return bool(SolverFactory("ipopt").available(exception_flag=False))
    except Exception:
        return False


def test_ports_are_dicts():
    step = KetchupEstimator(config={"model_name": "k-ecoli74"}, core=allocate_core())
    assert isinstance(step.inputs(), dict)
    assert isinstance(step.outputs(), dict)
    assert "seed" in step.inputs()
    assert set(step.outputs()) == EXPECTED_OUTPUTS


def test_initial_state_carries_seed():
    step = KetchupEstimator(config={"seed": 3}, core=allocate_core())
    assert step.initial_state()["seed"] == 3


def test_resolve_paths_for_bundled_models():
    for name in ("k-ecoli74", "k-ecoli307"):
        step = KetchupEstimator(config={"model_name": name}, core=allocate_core())
        paths = step._resolve_paths()
        assert paths["filename_model"].endswith("_model.xlsx")
        assert os.path.isfile(os.path.join(paths["directory_model"],
                                           paths["filename_model"]))


@pytest.mark.skipif(not _ipopt_available(), reason="IPOPT solver not installed")
def test_real_estimation_run(tmp_path):
    """Drive the genuine KETCHUP/IPOPT solver through the Step (bounded)."""
    opt = tmp_path / "ipopt_test.opt"
    opt.write_text("tol 0.01\nmax_iter 40\nmax_cpu_time 30\nprint_user_options no\n")

    step = KetchupEstimator(
        config={
            "model_name": "k-ecoli74",
            "solver_options": str(opt),
            "output_dir": str(tmp_path),
        },
        core=allocate_core(),
    )
    cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        result = step.update({"seed": 0})
    finally:
        os.chdir(cwd)

    assert set(result) == EXPECTED_OUTPUTS
    assert result["n_parameters"] > 0
    assert len(result["kf"]) == len(result["kr"]) > 0
    assert len(result["fluxes"]) > 0
    assert result["sse"] == result["sse"]  # not NaN
    assert isinstance(result["status"], str) and result["status"]
    assert result["solve_time"] > 0
