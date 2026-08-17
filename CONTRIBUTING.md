# Contributing to viva-ketchup

## Development setup

KETCHUP needs the compiled **IPOPT** solver. The simplest route is the bundled
conda spec:

```bash
mamba env create -f environment.yml
mamba activate viva-ketchup
pip install -e .
pytest
```

Or use a uv venv plus an IDAES-provided IPOPT binary:

```bash
uv venv .venv && source .venv/bin/activate
uv pip install -e ".[dev]" idaes-pse
idaes get-extensions
pytest
```

Tests that drive the real solver `skip` automatically when IPOPT is not on the
PATH, so the structural tests still run everywhere.

## Releasing to PyPI

Tag a commit with `git tag v<VERSION>` and push the tag. The
`.github/workflows/release.yml` workflow publishes to PyPI via trusted
publishing (no tokens after the one-time setup). See
https://docs.pypi.org/trusted-publishers/.
