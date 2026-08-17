"""The pbg_ketchup import name stays working (deprecated) after the rename."""
import warnings


def test_pbg_ketchup_still_imports_and_warns():
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        import pbg_ketchup  # noqa: F401
    assert any(issubclass(x.category, DeprecationWarning) for x in w)


def test_pbg_ketchup_submodule_redirects_to_viva_ketchup():
    import viva_ketchup.runtime as real
    import pbg_ketchup.runtime as shimmed
    assert shimmed is real            # meta-path finder aliases to the real module
