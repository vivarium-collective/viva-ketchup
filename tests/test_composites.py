"""Tests that the KETCHUP composite generators are registered and well-formed."""

from viva_ketchup.composites import ketchup_baseline, ketchup_multistart


def test_generators_registered():
    from viva_superpowers.composite_generator import _REGISTRY

    for suffix in ("ketchup_baseline", "ketchup_multistart"):
        matches = [eid for eid in _REGISTRY if eid.endswith(f".{suffix}")]
        assert matches, f"{suffix} missing; have {list(_REGISTRY)[:5]}"


def test_baseline_document_shape():
    doc = ketchup_baseline(model_name="k-ecoli74", seed=0)
    assert doc["ketchup"]["address"] == "local:KetchupEstimator"
    assert doc["ketchup"]["config"]["model_name"] == "k-ecoli74"
    # emitter present and wired to the result store
    assert doc["emitter"]["address"] == "local:RAMEmitter"
    assert doc["ketchup"]["inputs"]["seed"] == ["params", "seed"]
    assert doc["ketchup"]["outputs"]["sse"] == ["results", "sse"]


def test_multistart_uses_alternate_seed():
    doc = ketchup_multistart(model_name="k-ecoli74", seed=11)
    assert doc["ketchup"]["config"]["seed"] == 11
    assert doc["params"]["seed"] == 11
