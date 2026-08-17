"""Process-bigraph wrapper for KETCHUP kinetic parameter estimation.

KETCHUP (Maranas group, https://github.com/maranasgroup/KETCHUP) fits the
kinetic parameters of a metabolic network by solving a single nonlinear
program with IPOPT so that the model recapitulates measured steady-state
fluxes and concentrations.  Because estimation is a *one-shot solve* (not a
time-stepped integration), the natural process-bigraph wrapping is a
:class:`process_bigraph.Step`: it fires when its inputs change, runs the real
optimizer, and writes the estimated parameters / fit quality to its outputs.

This is a **real bridge** — ``update()`` drives the genuine ``ktools`` solver
(see :mod:`viva_ketchup.runtime`), it does not reproduce KETCHUP's math.
"""

from __future__ import annotations

import argparse
import os
import time
from typing import Any

from process_bigraph import Step

from .runtime import (
    BUNDLED_DYNAMIC_MODELS,
    BUNDLED_MODELS,
    dataset_dir,
    ensure_ketchup,
    solver_options_file,
)


def _extract_results(model, data_type: str) -> dict[str, Any]:
    """Read solved values out of the KETCHUP Pyomo model.

    Mirrors ``ktools.io.outputs.result_dump`` — this only *reads* the optimizer's
    solution off the model, it does not recompute anything.
    """
    kf = {str(k): _v(model.kf[k]) for k in model.kf}
    kr = {str(k): _v(model.kr[k]) for k in model.kr}

    exp_keys = list(model.data.keys())
    concentrations: dict[str, float] = {}
    enzymes: dict[str, float] = {}
    fluxes: dict[str, float] = {}
    per_experiment_sse: list[float] = []
    total_sse = 0.0

    for count, _key in enumerate(exp_keys):
        cur_exp = getattr(model, f"experiment{count}")
        err = _v(cur_exp.error)
        per_experiment_sse.append(err)
        total_sse += err
        # only surface the first experiment's state on the maps (representative);
        # full per-experiment detail is available via the returned model.
        if count == 0:
            concentrations = {str(i): _v(cur_exp.c[i]) for i in cur_exp.c}
            enzymes = {str(i): _v(cur_exp.e[i]) for i in cur_exp.e}
            fluxes = {str(i): _v(cur_exp.rate[i]) for i in cur_exp.rate}

    return {
        "kf": kf,
        "kr": kr,
        "concentrations": concentrations,
        "enzymes": enzymes,
        "fluxes": fluxes,
        "sse": float(total_sse),
        "per_experiment_sse": per_experiment_sse,
        "n_parameters": len(kf) + len(kr),
        "n_experiments": len(exp_keys),
    }


def _v(var) -> float:
    """Pyomo Var value → float (None solver values become NaN, then 0.0)."""
    val = getattr(var, "value", var)
    try:
        f = float(val)
    except (TypeError, ValueError):
        return 0.0
    return f if f == f else 0.0  # NaN guard


class KetchupEstimator(Step):
    """Estimate kinetic parameters for a K-FIT metabolic model with KETCHUP.

    Inputs
    ------
    seed : integer
        Random seed for parameter initialisation.  Different seeds give
        different IPOPT starting points (and possibly different local optima),
        so an upstream sweep/controller process can drive multistart estimation
        by writing successive seeds to this port.

    Outputs
    -------
    kf, kr : map[string, float]
        Estimated forward / reverse elementary-step rate constants.
    concentrations, enzymes, fluxes : map[string, float]
        Fitted metabolite concentrations, enzyme levels, and reaction rates for
        the first experiment block.
    sse : float
        Total sum-of-squared residuals between fitted and measured data
        (the optimizer's objective; lower = better fit).
    status : string
        IPOPT termination condition (e.g. ``optimal``).
    solve_time : float
        Wall-clock seconds spent generating + solving the model.
    n_parameters : integer
        Number of estimated rate constants (len(kf) + len(kr)).
    stability : string
        ``stable`` / ``unstable`` / ``not_evaluated`` — steady-state Jacobian
        eigenvalue check (only run when ``compute_stability`` is set).
    """

    config_schema = {
        # Which bundled K-FIT model to fit. If set and the file fields are left
        # blank, paths are resolved from datasets/<model_name>/.
        "model_name": {"_type": "string", "_default": "k-ecoli74"},
        # Explicit file overrides (otherwise derived from model_name).
        "directory_model": {"_type": "string", "_default": ""},
        "filename_model": {"_type": "string", "_default": ""},
        "filename_mechanism": {"_type": "string", "_default": ""},
        "directory_data": {"_type": "string", "_default": ""},
        "filename_data": {"_type": "string", "_default": ""},
        "data_type": {"_type": "string", "_default": "static"},
        "mechanism_type": {"_type": "string", "_default": "elemental"},
        "distribution": {"_type": "string", "_default": "uniform"},
        "seed": {"_type": "integer", "_default": 0},
        "compute_stability": {"_type": "boolean", "_default": False},
        "output_dir": {"_type": "string", "_default": ""},
        # Path to an IPOPT options file; empty -> vendored ipopt.opt (max_iter 5000).
        # Demos pass a bounded ipopt_demo.opt for fast, honestly-partial solves.
        "solver_options": {"_type": "string", "_default": ""},
    }

    def __init__(self, config=None, core=None):
        super().__init__(config=config, core=core)
        self._ktools_loaded = False

    # ------------------------------------------------------------------ ports
    def inputs(self):
        return {"seed": "integer"}

    def outputs(self):
        return {
            "kf": "map[string,float]",
            "kr": "map[string,float]",
            "concentrations": "map[string,float]",
            "enzymes": "map[string,float]",
            "fluxes": "map[string,float]",
            "sse": "float",
            "status": "string",
            "solve_time": "float",
            "n_parameters": "integer",
            "stability": "string",
        }

    def initial_state(self):
        return {"seed": int(self.config["seed"])}

    # --------------------------------------------------------------- options
    def _resolve_paths(self) -> dict[str, str]:
        name = self.config["model_name"]
        bundled = BUNDLED_MODELS.get(name, {})
        ddir = self.config["directory_model"] or str(dataset_dir(name))
        data_ddir = self.config["directory_data"] or str(dataset_dir(name))
        return {
            "directory_model": ddir,
            "directory_data": data_ddir,
            "filename_model": self.config["filename_model"]
            or bundled.get("filename_model", f"{name}_model.xlsx"),
            "filename_mechanism": self.config["filename_mechanism"]
            or bundled.get("filename_mechanism", f"{name}_mechanism.xlsx"),
            "filename_data": self.config["filename_data"]
            or bundled.get("filename_data", f"{name}_data.xlsx"),
        }

    def _build_options(self, seed: int) -> dict:
        ensure_ketchup()
        from ktools.ketchup.ketchup import ketchup_model_options

        paths = self._resolve_paths()
        out_dir = self.config["output_dir"] or os.getcwd()
        os.makedirs(out_dir, exist_ok=True)
        user_options = {
            "input_format": "kfit",
            "data_type": self.config["data_type"],
            "mechanism_type": self.config["mechanism_type"],
            "distribution": self.config["distribution"],
            "model_name": self.config["model_name"],
            "directory_output": out_dir,
            "seedvalue": int(seed),
            "flag_output_sbml": False,
            "filename_solver_opt": self.config["solver_options"] or solver_options_file(),
            **paths,
        }
        cmd_args = argparse.Namespace(
            seed=None, solver_options=None, program_options=None, time_delay=None
        )
        return ketchup_model_options(user_options, cmd_args)

    # ----------------------------------------------------------------- update
    def update(self, state):
        seed = int(state.get("seed", self.config["seed"]))
        ensure_ketchup()
        from ktools.ketchup import ketchup_generate_model, solve_ketchup_model

        options = self._build_options(seed)

        t0 = time.perf_counter()
        model = ketchup_generate_model(options)
        results = solve_ketchup_model(model, options)
        solve_time = time.perf_counter() - t0

        try:
            status = str(results.Solver[0]["Termination condition"])
        except Exception:
            status = "unknown"

        extracted = _extract_results(model, self.config["data_type"])
        stability = "not_evaluated"
        if self.config["compute_stability"]:
            stability = self._stability(model, options)

        return {
            "kf": extracted["kf"],
            "kr": extracted["kr"],
            "concentrations": extracted["concentrations"],
            "enzymes": extracted["enzymes"],
            "fluxes": extracted["fluxes"],
            "sse": extracted["sse"],
            "status": status,
            "solve_time": float(solve_time),
            "n_parameters": int(extracted["n_parameters"]),
            "stability": stability,
        }

    def _stability(self, model, options) -> str:
        """Best-effort steady-state Jacobian eigenvalue check (optional)."""
        try:
            from pyomo.contrib.pynumero.interfaces.pyomo_nlp import PyomoNLP
            import numpy as np

            nlp = PyomoNLP(model)
            jac = nlp.evaluate_jacobian().toarray()
            kf_idx = nlp.get_primal_indices([model.kf])
            kr_idx = nlp.get_primal_indices([model.kr])
            vf = nlp.get_constraint_indices([model.vf_rate])
            vr = nlp.get_constraint_indices([model.vr_rate])
            rxn_count = len(model.ELEMENTALSTEP_F)
            cols = kf_idx + kr_idx
            sub = jac[vf[:rxn_count] + vr[:rxn_count], :][:, cols]
            eig = np.linalg.eigvals(sub)
            return "stable" if np.all(eig.real <= 1e-3) else "unstable"
        except Exception:
            return "not_evaluated"


def _flatten_kinetic_parameters(model) -> dict[str, float]:
    """model.kinetic_parameters (custom mechanism) -> {group.name: value}."""
    out: dict[str, float] = {}
    if not hasattr(model, "kinetic_parameters"):
        return out
    kp = model.kinetic_parameters
    for group in kp:
        inner = kp[group]
        try:
            for name in inner:
                out[f"{group}.{name}"] = _v(inner[name])
        except TypeError:
            out[str(group)] = _v(inner)
    return out


class KetchupDynamicEstimator(Step):
    """Fit enzyme kinetics to **time-course** (NADH-vs-time) data with KETCHUP.

    Implements the dynamic / time-series KETCHUP extension (Hu, Jilani, Olson &
    Maranas, *PLOS Comput Biol* 2025): a custom-mechanism rate law is fit to a
    measured species trajectory (NADH) across several initial conditions using
    the 'strainer' time-course data format.  Bundled cell-free models: ``FDH``
    (formate dehydrogenase) and ``BDH`` (2,3-butanediol dehydrogenase).

    Like the steady-state estimator this is a one-shot solve, so it is a
    :class:`process_bigraph.Step` with a drivable ``seed`` input.  Its outputs
    carry both the fitted parameters and the per-experiment NADH(t) trajectories
    (fitted curve + measured points) so downstream consumers — or a report — can
    reproduce the paper's Fig 2 panels.

    Outputs
    -------
    kinetic_parameters : map[string, float]
        Fitted custom-mechanism parameters, keyed ``<group>.<name>``
        (e.g. ``kcat.FDH+f``).
    nadh_time, nadh_fit : map[string, list[float]]
        Per-experiment fitted trajectory: collocation times and predicted NADH.
    data_time, data_nadh : map[string, list[float]]
        Per-experiment measured time-points and NADH values.
    sse : float
        Total sum-of-squared residuals across experiments (objective).
    status : string
        IPOPT termination condition.
    solve_time : float
        Wall-clock seconds for generate + solve.
    n_parameters : integer
        Number of fitted kinetic parameters.
    n_experiments : integer
        Number of initial-condition datasets fit jointly.
    """

    config_schema = {
        "model_name": {"_type": "string", "_default": "FDH"},
        "directory_model": {"_type": "string", "_default": ""},
        "filename_model": {"_type": "string", "_default": ""},
        "filename_mechanism": {"_type": "string", "_default": ""},
        "directory_data": {"_type": "string", "_default": ""},
        "filename_data": {"_type": "string", "_default": ""},
        "target_species": {"_type": "string", "_default": "nadh"},
        "distribution": {"_type": "string", "_default": "uniform"},
        "seed": {"_type": "integer", "_default": 0},
        "time_delay": {"_type": "float", "_default": 0.0},
        "output_dir": {"_type": "string", "_default": ""},
        "solver_options": {"_type": "string", "_default": ""},
    }

    def inputs(self):
        return {"seed": "integer"}

    def outputs(self):
        return {
            "kinetic_parameters": "map[string,float]",
            "nadh_time": "map[string,list[float]]",
            "nadh_fit": "map[string,list[float]]",
            "data_time": "map[string,list[float]]",
            "data_nadh": "map[string,list[float]]",
            "initial_conditions": "map[string,map[string,float]]",
            "sse": "float",
            "status": "string",
            "solve_time": "float",
            "n_parameters": "integer",
            "n_experiments": "integer",
        }

    def initial_state(self):
        return {"seed": int(self.config["seed"])}

    def _bundle(self) -> dict:
        return BUNDLED_DYNAMIC_MODELS.get(self.config["model_name"], {})

    def _build_options(self, seed: int) -> dict:
        ensure_ketchup()
        from ktools.ketchup.ketchup import ketchup_model_options

        bundle = self._bundle()
        name = self.config["model_name"]
        ddir = self.config["directory_model"] or str(dataset_dir(name))
        data_ddir = self.config["directory_data"] or str(dataset_dir(name))
        out_dir = self.config["output_dir"] or os.getcwd()
        os.makedirs(out_dir, exist_ok=True)

        header = bundle.get("strainer_header")
        if header is None:
            raise ValueError(
                f"No bundled strainer header for dynamic model '{name}'. "
                f"Known: {list(BUNDLED_DYNAMIC_MODELS)}")

        user_options = {
            "input_format": "kfit",
            "data_type": "dynamic",
            "data_format": "strainer",
            "mechanism_type": "custom",
            "distribution": self.config["distribution"],
            "model_name": name,
            "directory_model": ddir,
            "directory_data": data_ddir,
            "directory_output": out_dir,
            "filename_model": self.config["filename_model"]
            or bundle.get("filename_model", f"{name}_model.xlsx"),
            "filename_mechanism": self.config["filename_mechanism"]
            or bundle.get("filename_mechanism", f"{name}_mechanism.xlsx"),
            "filename_data": self.config["filename_data"]
            or bundle.get("filename_data", f"{name}_dataset.xlsx"),
            "data_strainer_header": header,
            "time_delay": self.config["time_delay"],
            "seedvalue": int(seed),
            "flag_output_sbml": False,
            "filename_solver_opt": self.config["solver_options"] or solver_options_file(),
        }
        cmd_args = argparse.Namespace(
            seed=None, solver_options=None, program_options=None, time_delay=None
        )
        return ketchup_model_options(user_options, cmd_args)

    def _extract_trajectories(self, model):
        """Per-experiment fitted curve + measured points for the target species."""
        target = self.config["target_species"]
        exp_keys = list(model.data.keys())
        nadh_time, nadh_fit, data_time, data_nadh = {}, {}, {}, {}
        initial_conditions = {}
        total_sse = 0.0
        for i, key in enumerate(exp_keys):
            exp = getattr(model, f"experiment{i}")
            t0 = model.data[key].get("t0", {})
            initial_conditions[key] = {str(k): float(v) for k, v in t0.items()}
            # fitted dense trajectory
            pts = sorted(
                (float(t), _v(exp.c[(t, target)]))
                for (t, s) in exp.c.keys() if s == target)
            nadh_time[key] = [t for t, _ in pts]
            nadh_fit[key] = [v for _, v in pts]
            # measured points from the strainer-parsed data
            meas = model.data[key].get("time", {})
            tname = "Time" if "Time" in meas else next(
                (k for k in meas if k.lower().startswith("time")), None)
            if tname and target in meas:
                data_time[key] = [float(t) for t in meas[tname]]
                data_nadh[key] = [float(v) for v in meas[target]]
            else:
                data_time[key], data_nadh[key] = [], []
            try:
                total_sse += _v(exp.error)
            except Exception:
                pass
        return {
            "nadh_time": nadh_time, "nadh_fit": nadh_fit,
            "data_time": data_time, "data_nadh": data_nadh,
            "initial_conditions": initial_conditions,
            "sse": float(total_sse), "n_experiments": len(exp_keys),
        }

    def update(self, state):
        seed = int(state.get("seed", self.config["seed"]))
        ensure_ketchup()
        from ktools.ketchup import ketchup_generate_model, solve_ketchup_model

        options = self._build_options(seed)
        t0 = time.perf_counter()
        model = ketchup_generate_model(options)
        results = solve_ketchup_model(model, options)
        solve_time = time.perf_counter() - t0

        try:
            status = str(results.Solver[0]["Termination condition"])
        except Exception:
            status = "unknown"

        params = _flatten_kinetic_parameters(model)
        traj = self._extract_trajectories(model)
        return {
            "kinetic_parameters": params,
            "nadh_time": traj["nadh_time"],
            "nadh_fit": traj["nadh_fit"],
            "data_time": traj["data_time"],
            "data_nadh": traj["data_nadh"],
            "initial_conditions": traj["initial_conditions"],
            "sse": traj["sse"],
            "status": status,
            "solve_time": float(solve_time),
            "n_parameters": int(len(params)),
            "n_experiments": int(traj["n_experiments"]),
        }
