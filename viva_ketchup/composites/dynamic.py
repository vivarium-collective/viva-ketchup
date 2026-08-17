"""Composite generator for KETCHUP dynamic (time-series) estimation."""

from __future__ import annotations

from viva_superpowers.composite_generator import composite_generator


@composite_generator(
    name="ketchup_dynamic",
    description="Fit enzyme kinetics to time-course NADH data with KETCHUP's "
    "dynamic extension (cell-free FDH or BDH).",
    parameters={
        "model_name": {
            "type": "string",
            "default": "FDH",
            "description": "Bundled dynamic model: FDH or BDH.",
        },
        "seed": {
            "type": "integer",
            "default": 0,
            "description": "Random seed for IPOPT parameter initialisation.",
        },
        "solver_options": {
            "type": "string",
            "default": "",
            "description": "IPOPT options file path (blank = vendored default).",
        },
        "output_dir": {
            "type": "string",
            "default": "",
            "description": "Where KETCHUP writes results (blank = cwd).",
        },
    },
)
def ketchup_dynamic(core=None, *, model_name="FDH", seed=0,
                    solver_options="", output_dir=""):
    emit = {
        "kinetic_parameters": "map[string,float]",
        "sse": "float",
        "status": "string",
        "solve_time": "float",
        "n_parameters": "integer",
        "n_experiments": "integer",
    }
    return {
        "ketchup_dynamic": {
            "_type": "step",
            "address": "local:KetchupDynamicEstimator",
            "config": {
                "model_name": model_name,
                "seed": int(seed),
                "solver_options": solver_options,
                "output_dir": output_dir,
            },
            "inputs": {"seed": ["params", "seed"]},
            "outputs": {
                "kinetic_parameters": ["results", "kinetic_parameters"],
                "nadh_time": ["results", "nadh_time"],
                "nadh_fit": ["results", "nadh_fit"],
                "data_time": ["results", "data_time"],
                "data_nadh": ["results", "data_nadh"],
                "initial_conditions": ["results", "initial_conditions"],
                "sse": ["results", "sse"],
                "status": ["results", "status"],
                "solve_time": ["results", "solve_time"],
                "n_parameters": ["results", "n_parameters"],
                "n_experiments": ["results", "n_experiments"],
            },
        },
        "params": {"seed": int(seed)},
        "results": {},
        "emitter": {
            "_type": "step",
            "address": "local:RAMEmitter",
            "config": {"emit": emit},
            "inputs": {k: ["results", k] for k in emit},
        },
    }
