"""Closed-form reference prices used to validate the Monte Carlo engine."""

import math

from ._core import OptionType


def _norm_cdf(x: float) -> float:
    return 0.5 * math.erfc(-x / math.sqrt(2.0))


def _validate(spot, strike, rate, vol, maturity):
    for name, value in (("spot", spot), ("strike", strike), ("vol", vol), ("maturity", maturity)):
        if not (value > 0 and math.isfinite(value)):
            raise ValueError(f"{name} must be positive and finite, got {value!r}")
    if not math.isfinite(rate):
        raise ValueError(f"rate must be finite, got {rate!r}")


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
    _validate(spot, strike, rate, vol, maturity)
    std_dev = vol * math.sqrt(maturity)
    d1 = (math.log(spot / strike) + (rate + 0.5 * vol * vol) * maturity) / std_dev
    d2 = d1 - std_dev
    discount = math.exp(-rate * maturity)
    if option_type == OptionType.CALL:
        return spot * _norm_cdf(d1) - strike * discount * _norm_cdf(d2)
    return strike * discount * _norm_cdf(-d2) - spot * _norm_cdf(-d1)


def geometric_asian(
    *,
    option_type: OptionType,
    spot: float,
    strike: float,
    rate: float,
    vol: float,
    maturity: float,
    n_steps: int,
) -> float:
    """Discretely monitored geometric-average Asian option (Kemna–Vorst closed form).

    The average is over S(t_i), t_i = i T / m for i = 1..m (S_0 excluded). log G is then normal:
      mean     log S_0 + (r - vol^2 / 2) T (m + 1) / (2m)
      variance vol^2 T (m + 1)(2m + 1) / (6 m^2)
    so the price is a Black–Scholes-style formula in G. With m = 1 it is Black–Scholes.
    """
    _validate(spot, strike, rate, vol, maturity)
    if n_steps < 1:
        raise ValueError(f"n_steps must be at least 1, got {n_steps!r}")
    m = n_steps
    mean = math.log(spot) + (rate - 0.5 * vol * vol) * maturity * (m + 1) / (2 * m)
    var = vol * vol * maturity * (m + 1) * (2 * m + 1) / (6 * m * m)
    sd = math.sqrt(var)
    d1 = (mean - math.log(strike) + var) / sd
    d2 = d1 - sd
    forward = math.exp(mean + 0.5 * var)  # E[G]
    discount = math.exp(-rate * maturity)
    if option_type == OptionType.CALL:
        return discount * (forward * _norm_cdf(d1) - strike * _norm_cdf(d2))
    return discount * (strike * _norm_cdf(-d2) - forward * _norm_cdf(-d1))
