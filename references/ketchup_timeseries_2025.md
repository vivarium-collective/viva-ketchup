# KETCHUP time-series extension (reference)

**Hu M, Jilani SB, Olson DG, Maranas CD (2025). Parameterization of cell-free
systems with time-series data using KETCHUP. *PLOS Comput Biol* 21(11):
e1013724.** https://doi.org/10.1371/journal.pcbi.1013724

KETCHUP = *Kinetic Estimation Tool Capturing Heterogeneous datasets Using
Pyomo*. Originally for steady-state (K-FIT) flux fitting; this paper adds the
**dynamic / time-course** capability wrapped by `KetchupDynamicEstimator`.

## What the extension does

Fits kinetic parameters to a measured species trajectory (here NADH(t)) across
several initial conditions, by solving one IPOPT NLP over the time-discretised
ODE system. Two utilities are introduced:

1. **Time-course ingestion** (`data_format: strainer`) — raw NADH(t) is moving-
   averaged (10-pt) and thinned with Ramer–Douglas–Peucker to ~95–105 points
   per dataset for balanced objective weighting.
2. **Time-lag reconciliation** — a bracketing search recommends a per-dataset
   time offset (unaccounted lag between enzyme mixing and the spectrophotometer
   read) that minimises SSR; improved fits ~15%. *(not yet wrapped)*

## Models (bundled here)

| Enzyme | Reaction | Rate law | Datasets |
|---|---|---|---|
| **FDH** (formate dehydrogenase) | NAD⁺ + HCOO⁻ → CO₂ + NADH | Michaelis-Menten (Eq 1) | A1 (benchmark, 9 conditions), B1, B2 |
| **BDH** (2,3-butanediol dehydrogenase) | acetoin + NADH → 2,3-BD + NAD⁺ | convenience kinetics + Haldane (Eq 2-3) | Z1 |

Both include a first-order **NADH decomposition** side reaction (Eq 4),
important for long-time-course accuracy.

## Key numbers

- FDH benchmark (series A1): best **SSR 1.44 mM²**, comparable to MATLAB
  lsqnonlin+ode45 (1.49 mM², 9.27 s) and the gPROMS reported fit — KETCHUP
  9.82 s avg, 79% of 100 multistarts converged.
- Single-enzyme parameters successfully simulate the **binary FDH-BDH**
  fed-batch system (Fig 4) — validating parameter transfer to multi-enzyme
  models. *(forward simulation not yet wrapped)*

## How this maps to the wrapper

`KetchupDynamicEstimator` (in `viva_ketchup/processes.py`) drives the real
`ktools` dynamic path with `data_type=dynamic`, `mechanism_type=custom`,
`data_format=strainer`, and the per-model strainer header in
`runtime.BUNDLED_DYNAMIC_MODELS`. Outputs carry the fitted custom-mechanism
parameters plus per-experiment fitted/measured NADH(t) for Fig-2 reproduction.
