// European options under the Heston stochastic-volatility model.
#pragma once

#include "mcpricer/european.hpp"
#include "mcpricer/result.hpp"

namespace mcpricer {

// dS = r S dt + sqrt(v) S dW_1,   dv = kappa (theta - v) dt + xi sqrt(v) dW_2,   dW_1 dW_2 = rho dt
struct HestonOption {
    OptionType type;
    double spot;
    double strike;
    double rate;
    double maturity;
    double v0;     // initial variance
    double kappa;  // mean-reversion speed
    double theta;  // long-run variance
    double xi;     // volatility of variance
    double rho;    // correlation of the two Brownian motions
    int n_steps;   // Euler time steps
};

// Full-truncation Euler (Lord, Koekkoek & van Dijk 2010): v may go negative, but only
// v+ = max(v, 0) enters the drift and the diffusion. S is stepped in log space.
// config.antithetic and config.control_variate are not supported.
PricingResult price_heston(const HestonOption& option, const McConfig& config);

}  // namespace mcpricer
