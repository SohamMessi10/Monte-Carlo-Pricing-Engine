#include "mcpricer/european.hpp"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <stdexcept>

#include "mcpricer/normal.hpp"
#include "mcpricer/rng.hpp"
#include "mcpricer/stats.hpp"

namespace mcpricer {

namespace {

void require(bool ok, const char* message) {
    if (!ok) {
        throw std::invalid_argument(message);
    }
}

bool positive_finite(double x) { return x > 0.0 && std::isfinite(x); }

void validate(const EuropeanOption& option, const McConfig& config) {
    require(positive_finite(option.spot), "spot must be positive and finite");
    require(positive_finite(option.strike), "strike must be positive and finite");
    require(positive_finite(option.vol), "vol must be positive and finite");
    require(positive_finite(option.maturity), "maturity must be positive and finite");
    require(std::isfinite(option.rate), "rate must be finite");
    require(config.n_paths >= 2, "n_paths must be at least 2 to estimate a standard error");
}

// Undiscounted payoffs of one chunk of paths. Depends only on (seed, chunk, count).
RunningStats simulate_chunk(const EuropeanOption& option, double drift, double diffusion,
                            std::uint64_t seed, std::uint64_t chunk, std::uint64_t count) {
    auto rng = chunk_generator(seed, chunk);
    const bool is_call = option.type == OptionType::Call;
    RunningStats stats;
    for (std::uint64_t i = 0; i < count; ++i) {
        const double z = inv_norm_cdf(rng.uniform_open());
        const double s_t = option.spot * std::exp(drift + diffusion * z);
        const double payoff =
            is_call ? std::max(s_t - option.strike, 0.0) : std::max(option.strike - s_t, 0.0);
        stats.add(payoff);
    }
    return stats;
}

}  // namespace

PricingResult price_european(const EuropeanOption& option, const McConfig& config) {
    validate(option, config);
    const auto start = std::chrono::steady_clock::now();

    // Under the risk-neutral measure, S_T = S_0 exp((r - vol^2 / 2) T + vol sqrt(T) Z) exactly.
    const double drift = (option.rate - 0.5 * option.vol * option.vol) * option.maturity;
    const double diffusion = option.vol * std::sqrt(option.maturity);

    const auto n_paths = static_cast<std::uint64_t>(config.n_paths);
    const std::uint64_t n_chunks = (n_paths + kPathsPerChunk - 1) / kPathsPerChunk;

    RunningStats total;
    for (std::uint64_t chunk = 0; chunk < n_chunks; ++chunk) {
        const std::uint64_t count = std::min(kPathsPerChunk, n_paths - chunk * kPathsPerChunk);
        total.merge(simulate_chunk(option, drift, diffusion, config.seed, chunk, count));
    }

    const double discount = std::exp(-option.rate * option.maturity);
    const double std_error = std::sqrt(total.variance() / static_cast<double>(total.count));
    const std::chrono::duration<double> elapsed = std::chrono::steady_clock::now() - start;
    return {discount * total.mean, discount * std_error, total.count, elapsed.count()};
}

}  // namespace mcpricer
