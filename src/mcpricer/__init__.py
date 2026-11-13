"""Monte Carlo option-pricing engine with a C++20 core."""

from importlib.metadata import version

from ._core import OptionType, PricingResult, build_info, price_european
from .reference import black_scholes

__version__ = version("mcpricer")
__all__ = [
    "OptionType",
    "PricingResult",
    "__version__",
    "black_scholes",
    "build_info",
    "price_european",
]
