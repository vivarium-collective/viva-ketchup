"""Runtime helpers for the KETCHUP real bridge.

KETCHUP (the ``ktools`` package) ships no PyPI release and **no license**, so
this package does *not* redistribute its source or datasets.  Instead the
bridge resolves them on demand:

* :func:`ensure_ketchup` makes ``ktools`` importable — from a developer's local
  ``third_party/`` checkout if present, otherwise by cloning the upstream
  repository into a user cache directory.
* :func:`dataset_dir` returns a directory holding a model's K-FIT xlsx files —
  from the repo's ``datasets/`` if present, otherwise copied out of the cloned
  upstream into the cache.

This keeps the published package code-only while remaining fully functional:
the first run clones KETCHUP (~seconds) and everything after is cached.
Developers who place the upstream files under ``third_party/`` and
``datasets/`` (git-ignored) skip the clone entirely.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

UPSTREAM_URL = "https://github.com/maranasgroup/KETCHUP.git"

_PKG_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _PKG_DIR.parent


def _cache_root() -> Path:
    return Path(os.environ.get("KETCHUP_CACHE",
                               Path.home() / ".cache" / "viva-ketchup"))


# ---------------------------------------------------------------- upstream src
def _vendored_src() -> Path | None:
    """Local developer checkout of the ktools source, if present (git-ignored)."""
    for root in (_REPO_ROOT / "third_party",
                 _REPO_ROOT / "third_party" / "KETCHUP" / "KETCHUP_main" / "src"):
        if (root / "ktools").is_dir():
            return root
    return None


def ensure_ketchup_clone() -> Path:
    """Clone the upstream KETCHUP repo into the cache and return its root."""
    import subprocess

    cache = _cache_root()
    cache.mkdir(parents=True, exist_ok=True)
    dest = cache / "KETCHUP"
    if not (dest / "KETCHUP_main" / "src" / "ktools").is_dir():
        subprocess.run(
            ["git", "clone", "--depth", "1", UPSTREAM_URL, str(dest)],
            check=True,
        )
    return dest


def ensure_ketchup() -> Path:
    """Make ``ktools`` importable; return the directory it lives under."""
    vendored = _vendored_src()
    if vendored is not None:
        root = vendored
    else:
        try:
            root = ensure_ketchup_clone() / "KETCHUP_main" / "src"
        except Exception as exc:  # pragma: no cover - network dependent
            raise RuntimeError(
                "ktools (KETCHUP) source not found locally and could not be "
                f"cloned from {UPSTREAM_URL}: {exc}. Set KETCHUP_CACHE or place "
                "the source under third_party/."
            ) from exc
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    return root


# -------------------------------------------------------------- solver options
_DEFAULT_IPOPT_OPT = (
    "tol 0.001\n"
    "constr_viol_tol 0.001\n"
    "compl_inf_tol 0.001\n"
    "mu_strategy adaptive\n"
    "max_iter 5000\n"
)


def solver_options_file() -> str:
    """Path to a default IPOPT options file (self-authored; materialised to cache)."""
    cache = _cache_root()
    cache.mkdir(parents=True, exist_ok=True)
    path = cache / "ipopt.opt"
    if not path.is_file():
        path.write_text(_DEFAULT_IPOPT_OPT)
    return str(path)


# -------------------------------------------------------------------- datasets
# Where each bundled model's K-FIT files live *inside the upstream repo*.
_UPSTREAM_DATA_SUBDIR = {
    "k-ecoli74": "KETCHUP_main/example/data",
    "k-ecoli307": "Manuscript Supplementary Materials/Publication_1/data",
    "FDH": "Manuscript Supplementary Materials/Supplementary Materials SM2/"
           "run FDH and BDH/data",
    "BDH": "Manuscript Supplementary Materials/Supplementary Materials SM2/"
           "run FDH and BDH/data",
}
# The SM2 path has a "Publication_2/" segment; resolve robustly at runtime.
_FDH_BDH_GLOB = "run FDH and BDH/data"


def _model_files(model_name: str) -> list[str]:
    spec = BUNDLED_MODELS.get(model_name) or BUNDLED_DYNAMIC_MODELS.get(model_name, {})
    return [spec[k] for k in ("filename_model", "filename_mechanism", "filename_data")
            if k in spec]


def _copy_from_clone(model_name: str, dest: Path) -> None:
    """Copy a model's K-FIT files out of the cloned upstream into ``dest``."""
    repo = ensure_ketchup_clone()
    files = _model_files(model_name)
    # Find the source dir inside the clone (robust to SM2 path variations).
    if model_name in ("FDH", "BDH"):
        candidates = list(repo.glob(f"**/{_FDH_BDH_GLOB}"))
        src_dirs = candidates or [repo / _UPSTREAM_DATA_SUBDIR[model_name]]
    else:
        src_dirs = [repo / _UPSTREAM_DATA_SUBDIR[model_name]]
    dest.mkdir(parents=True, exist_ok=True)
    for fname in files:
        for sd in src_dirs:
            src = sd / fname
            if src.is_file():
                shutil.copy2(src, dest / fname)
                break
        else:
            raise FileNotFoundError(
                f"{fname} for {model_name} not found in cloned KETCHUP "
                f"(looked in {[str(s) for s in src_dirs]})")


def dataset_dir(model_name: str) -> Path:
    """Directory holding the K-FIT xlsx files for ``model_name``.

    Prefers a repo-local ``datasets/<model>/`` (developer checkout); otherwise
    copies the files out of the cloned upstream into the cache once.
    ``KETCHUP_DATASETS`` overrides the local root.
    """
    override = os.environ.get("KETCHUP_DATASETS")
    local = (Path(override) if override else (_REPO_ROOT / "datasets")) / model_name
    files = _model_files(model_name)
    if files and (local / files[0]).is_file():
        return local

    cached = _cache_root() / "datasets" / model_name
    if not (files and (cached / files[0]).is_file()):
        _copy_from_clone(model_name, cached)
    return cached


# Canonical K-FIT filename triples for the (static) models supported here.
BUNDLED_MODELS = {
    "k-ecoli74": {
        "filename_model": "k-ecoli74_model.xlsx",
        "filename_mechanism": "k-ecoli74_mechanism.xlsx",
        "filename_data": "k-ecoli74_data.xlsx",
    },
    "k-ecoli307": {
        "filename_model": "k-ecoli307_model.xlsx",
        "filename_mechanism": "k-ecoli307_mechanism.xlsx",
        "filename_data": "k-ecoli307_data.xlsx",
    },
}

# Dynamic (time-series) cell-free models from the KETCHUP time-series paper
# (Hu, Jilani, Olson & Maranas, PLOS Comput Biol 2025). Each fits an enzyme's
# kinetic parameters to a measured NADH(t) trajectory via the 'strainer'
# time-course data format and a custom rate law.
BUNDLED_DYNAMIC_MODELS = {
    "FDH": {  # formate dehydrogenase: NAD+ + HCOO- -> CO2 + NADH
        "filename_model": "FDH_model.xlsx",
        "filename_mechanism": "FDH_mechanism.xlsx",
        "filename_data": "FDH_dataset_series_A1.xlsx",
        "target_species": "nadh",
        "strainer_header": {
            "t_0": ["fdh", "23bdo", "actn", "nad", "formate", "nadh", "co2"],
            "time": ["nadh"],
            "type": ["e", "c", "c", "c", "c", "c", "c", "c"],
            "status": ["i", "g", "g", "i", "i", "i", "i", "d"],
        },
    },
    "BDH": {  # 2,3-butanediol dehydrogenase: acetoin + NADH -> 23BD + NAD+
        "filename_model": "BDH_model.xlsx",
        "filename_mechanism": "BDH_mechanism.xlsx",
        "filename_data": "BDH_dataset_series_Z1.xlsx",
        "target_species": "nadh",
        "strainer_header": {
            "t_0": ["bdh", "23bdo", "actn", "nad", "formate", "nadh", "pyr"],
            "time": ["nadh"],
            "type": ["e", "c", "c", "c", "c", "c", "c", "c"],
            "status": ["i", "g", "g", "i", "i", "i", "i", "d"],
        },
    },
}
