"""Tests for the KetchupDynamicEstimator (time-series) Step.

The real-solve test uses FDH (9 datasets, ~1.5 s to optimal) and is skipped
when IPOPT is unavailable.
"""

import os

import pytest
from process_bigraph import allocate_core

from viva_ketchup import KetchupDynamicEstimator

EXPECTED = {
    "kinetic_parameters", "nadh_time", "nadh_fit", "data_time", "data_nadh",
    "initial_conditions", "sse", "status", "solve_time", "n_parameters",
    "n_experiments",
}


def _ipopt_available() -> bool:
    try:
        from pyomo.environ import SolverFactory
        return bool(SolverFactory("ipopt").available(exception_flag=False))
    except Exception:
        return False


def test_ports():
    step = KetchupDynamicEstimator(config={"model_name": "FDH"}, core=allocate_core())
    assert set(step.outputs()) == EXPECTED
    assert "seed" in step.inputs()


def test_bundled_dynamic_paths_exist():
    from viva_ketchup.runtime import BUNDLED_DYNAMIC_MODELS, dataset_dir
    for name, bundle in BUNDLED_DYNAMIC_MODELS.items():
        d = dataset_dir(name)
        for key in ("filename_model", "filename_mechanism", "filename_data"):
            assert os.path.isfile(os.path.join(d, bundle[key])), \
                f"missing {bundle[key]} for {name}"


@pytest.mark.skipif(not _ipopt_available(), reason="IPOPT solver not installed")
def test_fdh_dynamic_fit(tmp_path):
    opt = tmp_path / "ipopt.opt"
    opt.write_text("tol 0.001\nmax_iter 300\nmax_cpu_time 60\nprint_user_options no\n")
    step = KetchupDynamicEstimator(
        config={"model_name": "FDH", "solver_options": str(opt),
                "output_dir": str(tmp_path)},
        core=allocate_core(),
    )
    cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        r = step.update({"seed": 0})
    finally:
        os.chdir(cwd)

    assert set(r) == EXPECTED
    assert r["n_experiments"] == 9          # FDH dataset series A1: A1..A9
    assert r["n_parameters"] > 0
    assert r["kinetic_parameters"]          # custom-mechanism params present
    # each experiment has a fitted trajectory and measured points
    for key, fit in r["nadh_fit"].items():
        assert len(fit) > 1
        assert len(r["data_nadh"][key]) > 1
    # FDH fits to near-optimal on this benchmark
    assert r["sse"] < 1.0
