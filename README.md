# viva-ketchup

A [process-bigraph](https://github.com/vivarium-collective/process-bigraph)
wrapper for **[KETCHUP](https://github.com/maranasgroup/KETCHUP)** (Maranas
group) — kinetic parameter estimation for metabolic networks.

KETCHUP fits the kinetic parameters of a metabolic network by solving a single
nonlinear program with **IPOPT** so that the model recapitulates measured
steady-state fluxes and metabolite concentrations across wild-type and
perturbed conditions. This package bridges the **real** `ktools` solver as a
process-bigraph `Step` — `update()` builds the genuine Pyomo model and calls
IPOPT. Nothing is reimplemented or mocked.

Two modes are wrapped:

- **Steady-state** (`KetchupEstimator`) — large-scale flux fitting. Two K-FIT
  *E. coli* models are bundled: `k-ecoli74` (74-reaction core metabolism) and
  `k-ecoli307` (307 reactions, ~2,500 rate constants).
- **Time-series / dynamic** (`KetchupDynamicEstimator`) — the cell-free
  time-course extension from Hu, Jilani, Olson & Maranas, *PLOS Comput Biol*
  2025 ([10.1371/journal.pcbi.1013724](https://doi.org/10.1371/journal.pcbi.1013724)).
  Fits a custom rate law to a measured NADH(t) trajectory across many initial
  conditions. Two cell-free enzyme models bundled: `FDH` (formate
  dehydrogenase) and `BDH` (2,3-butanediol dehydrogenase).

## Why a `Step` (not a `Process`)?

Parameter estimation is a one-shot solve, not a time-stepped integration. A
process-bigraph `Step` fires when its inputs change, so the wrapper exposes a
`seed` **input port**: an upstream sweep or controller can write successive
seeds to drive **multistart** estimation, and each new seed re-triggers the fit.

## Installation

KETCHUP depends on the **IPOPT** solver, which is a compiled binary. The two
supported ways to provide it:

```bash
# Option A — conda (matches upstream KETCHUP, recommended):
mamba env create -f environment.yml
mamba activate viva-ketchup
pip install -e .            # add this wrapper into the env

# Option B — uv venv + a precompiled IPOPT from IDAES:
uv venv .venv && source .venv/bin/activate
uv pip install -e ".[dev]" idaes-pse
idaes get-extensions       # downloads an ipopt binary onto PATH
```

KETCHUP (`ktools`) ships no PyPI release and **no license**, so this package
does not redistribute its source or datasets. On first use,
`viva_ketchup.runtime` clones KETCHUP into a cache dir (`~/.cache/viva-ketchup`,
override with `KETCHUP_CACHE`) and copies out only the model files it needs;
everything after is cached. Developers may instead drop the upstream `ktools`
source under `third_party/` and the K-FIT xlsx under `datasets/<model>/`
(both git-ignored) to skip the clone.

> Once installed, the `KetchupEstimator` process registers automatically via
> `bigraph_schema.package.discover` — no manual `register_link()` is needed.

## Quick start

```python
import os
from process_bigraph import allocate_core
from viva_ketchup import KetchupEstimator

step = KetchupEstimator(config={"model_name": "k-ecoli74"}, core=allocate_core())
result = step.update({"seed": 0})

print(result["status"])         # IPOPT termination condition
print(result["sse"])            # objective: total sum-of-squared residuals
print(len(result["kf"]))        # estimated forward rate constants
print(result["fluxes"]["R1"])   # fitted reaction rate
```

For a fast, bounded run pass an IPOPT options file capping iterations:

```python
open("fast.opt", "w").write("max_iter 200\nmax_cpu_time 30\n")
step = KetchupEstimator(
    config={"model_name": "k-ecoli307", "solver_options": "fast.opt"},
    core=allocate_core(),
)
```

## API reference

### `KetchupEstimator(Step)`

| Port | Dir | Schema | Meaning |
|---|---|---|---|
| `seed` | in | `integer` | RNG seed for IPOPT initialisation (drivable for multistart) |
| `kf`, `kr` | out | `map[string,float]` | Estimated forward / reverse elementary-step rate constants |
| `concentrations` | out | `map[string,float]` | Fitted metabolite concentrations (experiment 0) |
| `enzymes` | out | `map[string,float]` | Fitted enzyme levels (experiment 0) |
| `fluxes` | out | `map[string,float]` | Fitted reaction rates (experiment 0) |
| `sse` | out | `float` | Total sum-of-squared residuals (objective) |
| `status` | out | `string` | IPOPT termination condition |
| `solve_time` | out | `float` | Wall-clock seconds for generate + solve |
| `n_parameters` | out | `integer` | `len(kf) + len(kr)` |
| `stability` | out | `string` | `stable` / `unstable` / `not_evaluated` (Jacobian eigen-check; opt-in via `compute_stability`) |

Key config: `model_name` (`k-ecoli74` / `k-ecoli307`), explicit
`directory_model` / `filename_*` overrides for your own K-FIT models,
`solver_options` (IPOPT options-file path), `output_dir`, `compute_stability`.

### `KetchupDynamicEstimator(Step)` — time-series fitting

Same `seed` input. Outputs `kinetic_parameters: map[string,float]` (custom-
mechanism params keyed `<group>.<name>`), per-experiment trajectories
`nadh_time` / `nadh_fit` / `data_time` / `data_nadh` (`map[string,list[float]]`)
and `initial_conditions` (`map[string,map[string,float]]`), plus `sse`,
`status`, `solve_time`, `n_parameters`, `n_experiments`. Bundled `model_name`:
`FDH`, `BDH`.

```python
from viva_ketchup import KetchupDynamicEstimator
step = KetchupDynamicEstimator(config={"model_name": "FDH"}, core=allocate_core())
r = step.update({"seed": 0})          # ~1.5 s to optimal, SSE ~0.01
r["nadh_fit"]["A1"]                    # fitted NADH(t) for the first condition
```

### Composite generators (dashboard-visible)

<!-- BEGIN:composites -->
<!-- generated by `vivarium-workbench gen-readme` — edit the source, not this table -->

| Composite | What it is |
|---|---|
| `ketchup_baseline` | Fit kinetic parameters of a K-FIT metabolic model (k-ecoli74 / k-ecoli307) with the real KETCHUP IPOPT solver. |
| `ketchup_dynamic` | Fit enzyme kinetics to time-course NADH data with KETCHUP's dynamic extension (cell-free FDH or BDH). |
| `ketchup_multistart` | Multistart KETCHUP estimation: re-fit the same model from a different random seed to probe local-optimum sensitivity. |
<!-- END:composites -->

## Architecture mapping

| KETCHUP / `ktools` | viva-ketchup |
|---|---|
| `ketchup_generate_model(options)` | built inside `update()` |
| `solve_ketchup_model(model, options)` (IPOPT) | called inside `update()` |
| solved Pyomo vars `kf/kr/c/e/rate/error` | read out to output ports |
| K-FIT `*_model/_mechanism/_data.xlsx` | `datasets/<model>/`, resolved by `runtime` |
| `ipopt.opt` solver options | default written to cache, or per-run `solver_options` override |

## Demo

```bash
python demo/demo_report.py   # runs both models + a multistart, writes demo/report.html
```

The report runs the **real** IPOPT solver on `k-ecoli74` and `k-ecoli307`
(bounded for speed), parses IPOPT's own iteration log into a convergence trace,
and renders interactive Plotly charts, a `bigraph-viz2` architecture diagram, and
a collapsible result-document tree. It opens in your browser automatically.

## Limitations & assumptions

- **Bounded demo solves.** The demo caps `max_iter`/`max_cpu_time`, so reported
  solutions are genuine but *partial* (the IPOPT termination condition is shown
  honestly). Remove the bound for full convergence.
- **IPOPT required.** No solver → no fit. Tests that need it `skip` rather than
  fail when IPOPT is absent.
- The steady-state estimator's scalar/map outputs surface the **first**
  experiment block; full per-experiment detail remains on the Pyomo model.
- The dynamic estimator currently targets NADH-tracked single-enzyme cell-free
  models (FDH/BDH). The paper's time-lag-reconciliation utility and the binary
  FDH-BDH forward simulation are not yet wrapped.

## Provenance

This wrapper does **not** redistribute KETCHUP. The `ktools` source and the
`k-ecoli74` / `k-ecoli307` / `FDH` / `BDH` K-FIT datasets are resolved on
demand from <https://github.com/maranasgroup/KETCHUP> (cloned + cached at
runtime). KETCHUP is the work of the Maranas group and carries no license of
its own — consult the authors regarding terms. Cite their publications:

- Gopalakrishnan, Dash & Maranas, *Metab. Eng.* 2020 (K-FIT / steady-state).
- Hu, Jilani, Olson & Maranas, *PLOS Comput Biol* 2025,
  [10.1371/journal.pcbi.1013724](https://doi.org/10.1371/journal.pcbi.1013724)
  (time-series / cell-free extension).
