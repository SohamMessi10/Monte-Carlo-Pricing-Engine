"""Monte Carlo option-pricing engine with a C++20 core."""

from importlib.metadata import version

from ._core import (
    Average,
    OptionType,
    PricingResult,
    build_info,
    price_asian,
    price_european,
    price_up_and_out,
)
from .reference import black_scholes, geometric_asian

__version__ = version("mcpricer")
__all__ = [
    "Average",
    "OptionType",
    "PricingResult",
    "__version__",
    "black_scholes",
    "build_info",
    "geometric_asian",
    "price_asian",
    "price_european",
    "price_up_and_out",
]
