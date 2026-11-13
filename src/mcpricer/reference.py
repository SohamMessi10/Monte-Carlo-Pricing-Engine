"""Closed-form reference prices used to validate the Monte Carlo engine."""

import math

from ._core import OptionType


def _norm_cdf(x: float) -> float:
    return 0.5 * math.erfc(-x / math.sqrt(2.0))


def black_scholes(
    *,
    option_type: OptionType,
    spot: float,
    strike: float,
    rate: float,
    vol: float,
    maturity: float,
) -> float:
    """Black–Scholes price of a European call or put (no dividends)."""
    for name, value in (("spot", spot), ("strike", strike), ("vol", vol), ("maturity", maturity)):
        if not (value > 0 and math.isfinite(value)):
            raise ValueError(f"{name} must be positive and finite, got {value!r}")
    if not math.isfinite(rate):
        raise ValueError(f"rate must be finite, got {rate!r}")

    std_dev = vol * math.sqrt(maturity)
    d1 = (math.log(spot / strike) + (rate + 0.5 * vol * vol) * maturity) / std_dev
    d2 = d1 - std_dev
    discount = math.exp(-rate * maturity)
    if option_type == OptionType.CALL:
        return spot * _norm_cdf(d1) - strike * discount * _norm_cdf(d2)
    return strike * discount * _norm_cdf(-d2) - spot * _norm_cdf(-d1)
