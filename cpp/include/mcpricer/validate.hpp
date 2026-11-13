// Input checks shared by all pricers. std::invalid_argument reaches Python as ValueError.
#pragma once

#include <cmath>
#include <stdexcept>

#include "mcpricer/european.hpp"
#include "mcpricer/parallel.hpp"

namespace mcpricer {

inline void require(bool ok, const char* message) {
    if (!ok) {
        throw std::invalid_argument(message);
    }
}

inline bool positive_finite(double x) { return x > 0.0 && std::isfinite(x); }

// The contract terms every GBM product shares.
inline void validate_terms(const EuropeanOption& option) {
    require(positive_finite(option.spot), "spot must be positive and finite");
    require(positive_finite(option.strike), "strike must be positive and finite");
    require(positive_finite(option.vol), "vol must be positive and finite");
    require(positive_finite(option.maturity), "maturity must be positive and finite");
    require(std::isfinite(option.rate), "rate must be finite");
}

inline void validate_paths_and_threads(const McConfig& config) {
    require(config.n_paths >= 2, "n_paths must be at least 2 to estimate a standard error");
    require(config.n_threads >= 0 && config.n_threads <= kMaxThreads,
            "n_threads must be between 0 and 1024 (0 means one per hardware thread)");
}

}  // namespace mcpricer
