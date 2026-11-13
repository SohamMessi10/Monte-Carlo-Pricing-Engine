// Randomized quasi-Monte Carlo: Sobol points + random digital shifts, GBM paths on a grid.
#pragma once

#include <cstdint>
#include <vector>

#include "mcpricer/european.hpp"
#include "mcpricer/result.hpp"

namespace mcpricer {

enum class Payoff { European, ArithmeticAsian, GeometricAsian };

struct QmcOption {
    EuropeanOption terms;
    int n_steps;  // grid t_i = i T / n_steps; one Sobol dimension per step
    Payoff payoff;
};

struct QmcConfig {
    std::int64_t n_points;  // Sobol points per replication (powers of 2 are best)
    int n_replications;     // independent random digital shifts; gives the error bar
    std::uint64_t seed;
    int n_threads = 0;
    bool brownian_bridge = true;  // false: build W step by step from consecutive dimensions
};

// estimate = mean over replications; std_error = their sample std dev / sqrt(n_replications).
// n_paths in the result is n_points * n_replications.
PricingResult price_qmc(const QmcOption& option, const QmcConfig& config);

// The first n unshifted points in `dims` dimensions, as x / 2^32. Exposed for tests.
std::vector<std::vector<double>> sobol_points(std::int64_t n, int dims);

}  // namespace mcpricer
