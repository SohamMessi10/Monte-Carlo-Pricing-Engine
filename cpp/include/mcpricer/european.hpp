// European options under geometric Brownian motion.
#pragma once

#include <cstdint>

#include "mcpricer/result.hpp"

namespace mcpricer {

enum class OptionType { Call, Put };

struct EuropeanOption {
    OptionType type;
    double spot;
    double strike;
    double rate;      // continuously compounded risk-free rate
    double vol;       // annualized volatility
    double maturity;  // in years
};

struct McConfig {
    std::int64_t n_paths;  // signed so that negative input gives a clear error, not a wrap
    std::uint64_t seed;
    int n_threads = 0;  // 0 means one per hardware thread; results don't depend on it
    bool antithetic = false;       // pair every Z with -Z
    bool control_variate = false;  // use S_T, whose mean S_0 e^{rT} is known, as a control
};

// Exact simulation of S_T. Throws std::invalid_argument on invalid input.
PricingResult price_european(const EuropeanOption& option, const McConfig& config);

}  // namespace mcpricer
