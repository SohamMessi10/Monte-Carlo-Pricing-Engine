#include "mcpricer/heston.hpp"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>

#include "mcpricer/normal.hpp"
#include "mcpricer/parallel.hpp"
#include "mcpricer/path_dependent.hpp"
#include "mcpricer/rng.hpp"
#include "mcpricer/stats.hpp"
#include "mcpricer/validate.hpp"

namespace mcpricer {

namespace {

void validate(const HestonOption& o, const McConfig& config) {
    require(positive_finite(o.spot), "spot must be positive and finite");
    require(positive_finite(o.strike), "strike must be positive and finite");
    require(positive_finite(o.maturity), "maturity must be positive and finite");
    require(std::isfinite(o.rate), "rate must be finite");
    require(o.v0 >= 0.0 && std::isfinite(o.v0), "v0 must be non-negative and finite");
    require(positive_finite(o.kappa), "kappa must be positive and finite");
    require(positive_finite(o.theta), "theta must be positive and finite");
    require(positive_finite(o.xi), "xi must be positive and finite");
    require(o.rho >= -1.0 && o.rho <= 1.0, "rho must be in [-1, 1]");
    require(o.n_steps >= 1 && o.n_steps <= kMaxSteps, "n_steps must be between 1 and 100000");
    validate_paths_and_threads(config);
    require(!config.antithetic, "antithetic=True is not supported for Heston");
    require(!config.control_variate, "control_variate=True is not supported for Heston");
}

RunningStats heston_chunk(const HestonOption& o, std::uint64_t seed, std::uint64_t chunk,
                          std::uint64_t count) noexcept {
    auto rng = chunk_generator(seed, chunk);
    const double dt = o.maturity / static_cast<double>(o.n_steps);
    const double sqrt_dt = std::sqrt(dt);
    const double rho_bar = std::sqrt(1.0 - o.rho * o.rho);
    const bool is_call = o.type == OptionType::Call;
    const double log_spot = std::log(o.spot);

    RunningStats stats;
    for (std::uint64_t i = 0; i < count; ++i) {
        double log_s = log_spot;
        double v = o.v0;
        for (int k = 0; k < o.n_steps; ++k) {
            const double z_v = inv_norm_cdf(rng.uniform_open());
            const double z_s = o.rho * z_v + rho_bar * inv_norm_cdf(rng.uniform_open());
            const double v_plus = std::max(v, 0.0);  // full truncation
            const double sd = std::sqrt(v_plus) * sqrt_dt;
            log_s += (o.rate - 0.5 * v_plus) * dt + sd * z_s;
            v += o.kappa * (o.theta - v_plus) * dt + o.xi * sd * z_v;
        }
        const double s_t = std::exp(log_s);
        stats.add(is_call ? std::max(s_t - o.strike, 0.0) : std::max(o.strike - s_t, 0.0));
    }
    return stats;
}

}  // namespace

PricingResult price_heston(const HestonOption& option, const McConfig& config) {
    validate(option, config);
    const auto start = std::chrono::steady_clock::now();

    const auto n_paths = static_cast<std::uint64_t>(config.n_paths);
    const std::uint64_t n_chunks = (n_paths + kPathsPerChunk - 1) / kPathsPerChunk;
    const RunningStats s = run_chunks(
        n_chunks, resolve_thread_count(config.n_threads, n_chunks),
        [&](std::uint64_t chunk) noexcept {
            return heston_chunk(option, config.seed, chunk,
                                std::min(kPathsPerChunk, n_paths - chunk * kPathsPerChunk));
        });

    const double discount = std::exp(-option.rate * option.maturity);
    const double std_error = std::sqrt(s.variance() / static_cast<double>(n_paths));
    const std::chrono::duration<double> elapsed = std::chrono::steady_clock::now() - start;
    return {discount * s.mean, discount * std_error, n_paths, elapsed.count()};
}

}  // namespace mcpricer
