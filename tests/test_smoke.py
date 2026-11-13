"""Smoke tests: the compiled extension builds, imports and reports how it was built."""

import mcpricer


def test_extension_imports():
    assert mcpricer._core.__name__ == "mcpricer._core"
    assert mcpricer.__version__


def test_built_as_cxx20_or_newer():
    assert mcpricer.build_info()["cxx_standard"] >= 202002


def test_build_info_fields():
    info = mcpricer.build_info()
    assert set(info) == {"compiler", "build_type", "cxx_flags", "cxx_standard", "sanitizers"}
    assert info["compiler"]
