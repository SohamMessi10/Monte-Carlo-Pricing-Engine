#pragma once

#include <cstdint>

namespace mcpricer {

// What every pricer returns.
struct PricingResult {
    double estimate;         // discounted Monte Carlo price
    double std_error;        // standard error of the estimate
    std::uint64_t n_paths;   // number of simulated paths
    double elapsed_seconds;  // wall-clock time of the simulation
};

}  // namespace mcpricer
