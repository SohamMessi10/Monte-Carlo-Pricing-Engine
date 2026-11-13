"""Monte Carlo option-pricing engine with a C++20 core."""

from importlib.metadata import version

from ._core import build_info

__version__ = version("mcpricer")
__all__ = ["__version__", "build_info"]
