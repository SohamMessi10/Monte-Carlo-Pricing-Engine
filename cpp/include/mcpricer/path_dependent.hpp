// Path-dependent options under GBM, monitored on the grid t_i = i T / n_steps, i = 1..n_steps.
#pragma once

#include "mcpricer/european.hpp"
#include "mcpricer/result.hpp"

namespace mcpricer {

inline constexpr int kMaxSteps = 100000;

enum class Average { Arithmetic, Geometric };

struct AsianOption {
    EuropeanOption terms;  // type, spot, strike, rate, vol, maturity
    int n_steps;           // number of monitoring dates; S_0 is not part of the average
    Average average;
};

// Knocked out (pays 0) if S(t_i) >= barrier at any monitoring date t_i.
struct UpAndOutOption {
    EuropeanOption terms;
    double barrier;
    int n_steps;
};

// config.control_variate (arithmetic average only) uses the geometric Asian as the control.
// config.antithetic is not supported for path-dependent options.
PricingResult price_asian(const AsianOption& option, const McConfig& config);

PricingResult price_up_and_out(const UpAndOutOption& option, const McConfig& config);

// Kemna–Vorst closed form for the discretely monitored geometric Asian (discounted).
double geometric_asian_price(const EuropeanOption& terms, int n_steps);

}  // namespace mcpricer
