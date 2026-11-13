"""Monte Carlo option-pricing engine with a C++20 core."""

from importlib.metadata import version

from ._core import (
    Average,
    OptionType,
    Payoff,
    PricingResult,
    build_info,
    price_asian,
    price_european,
    price_heston,
    price_qmc,
    price_up_and_out,
)
from .reference import black_scholes, geometric_asian, heston

__version__ = version("mcpricer")
__all__ = [
    "Average",
    "OptionType",
    "Payoff",
    "PricingResult",
    "__version__",
    "black_scholes",
    "build_info",
    "geometric_asian",
    "heston",
    "price_asian",
    "price_european",
    "price_heston",
    "price_qmc",
    "price_up_and_out",
]
