"""Composite generators exposing KETCHUP estimation to the dashboard."""

from __future__ import annotations

from viva_superpowers.composite_generator import composite_generator


def _estimation_document(*, model_name, seed, solver_options, output_dir):
    """A one-Step composite: KetchupEstimator wired to result stores + emitter."""
    emit = {
        "kf": "map[string,float]",
        "kr": "map[string,float]",
        "fluxes": "map[string,float]",
        "concentrations": "map[string,float]",
        "sse": "float",
        "status": "string",
        "solve_time": "float",
        "n_parameters": "integer",
    }
    return {
        "ketchup": {
            "_type": "step",
            "address": "local:KetchupEstimator",
            "config": {
                "model_name": model_name,
                "seed": int(seed),
                "solver_options": solver_options,
                "output_dir": output_dir,
            },
            "inputs": {"seed": ["params", "seed"]},
            "outputs": {k: ["results", k] for k in emit},
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


@composite_generator(
    name="ketchup_baseline",
    description="Fit kinetic parameters of a K-FIT metabolic model (k-ecoli74 / "
    "k-ecoli307) with the real KETCHUP IPOPT solver.",
    parameters={
        "model_name": {
            "type": "string",
            "default": "k-ecoli74",
            "description": "Bundled K-FIT model to fit (k-ecoli74 or k-ecoli307).",
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
def ketchup_baseline(core=None, *, model_name="k-ecoli74", seed=0,
                     solver_options="", output_dir=""):
    return _estimation_document(
        model_name=model_name, seed=seed,
        solver_options=solver_options, output_dir=output_dir,
    )


@composite_generator(
    name="ketchup_multistart",
    description="Multistart KETCHUP estimation: re-fit the same model from a "
    "different random seed to probe local-optimum sensitivity.",
    parameters={
        "model_name": {
            "type": "string",
            "default": "k-ecoli74",
            "description": "Bundled K-FIT model to fit.",
        },
        "seed": {
            "type": "integer",
            "default": 7,
            "description": "Alternate seed (vs. the baseline seed 0).",
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
def ketchup_multistart(core=None, *, model_name="k-ecoli74", seed=7,
                       solver_options="", output_dir=""):
    return _estimation_document(
        model_name=model_name, seed=seed,
        solver_options=solver_options, output_dir=output_dir,
    )
