#include "mcpricer/european.hpp"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <stdexcept>
#include <type_traits>

#include "mcpricer/normal.hpp"
#include "mcpricer/parallel.hpp"
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

// With antithetic variates one sample is a pair of paths (Z, -Z), so there are half as many.
std::uint64_t sample_count(const McConfig& config) {
    const auto n_paths = static_cast<std::uint64_t>(config.n_paths);
    return config.antithetic ? n_paths / 2 : n_paths;
}

void validate(const EuropeanOption& option, const McConfig& config) {
    require(positive_finite(option.spot), "spot must be positive and finite");
    require(positive_finite(option.strike), "strike must be positive and finite");
    require(positive_finite(option.vol), "vol must be positive and finite");
    require(positive_finite(option.maturity), "maturity must be positive and finite");
    require(std::isfinite(option.rate), "rate must be finite");
    require(config.n_paths >= 2, "n_paths must be at least 2 to estimate a standard error");
    require(config.n_threads >= 0 && config.n_threads <= kMaxThreads,
            "n_threads must be between 0 and 1024 (0 means one per hardware thread)");
    if (config.antithetic) {
        require(config.n_paths % 2 == 0 && config.n_paths >= 4,
                "with antithetic=True, n_paths must be even and at least 4 (2 antithetic pairs)");
    }
    if (config.control_variate) {
        require(sample_count(config) >= 3,
                "with control_variate=True, at least 3 samples are needed "
                "(n_paths >= 3, or n_paths >= 6 with antithetic=True)");
    }
}

// Under the risk-neutral measure, S_T = S_0 exp((r - vol^2 / 2) T + vol sqrt(T) Z) exactly.
struct Gbm {
    double spot;
    double strike;
    double drift;      // (r - vol^2 / 2) T
    double diffusion;  // vol sqrt(T)
    bool is_call;

    double terminal(double z) const noexcept { return spot * std::exp(drift + diffusion * z); }
    double payoff(double s_t) const noexcept {
        return is_call ? std::max(s_t - strike, 0.0) : std::max(strike - s_t, 0.0);
    }
};

// Undiscounted payoffs of one chunk of samples. Depends only on (seed, chunk, count).
// RunningStats collects the payoff only; CovStats also collects S_T for the control variate.
template <class Stats>
Stats simulate_chunk(const Gbm& gbm, bool antithetic, std::uint64_t seed, std::uint64_t chunk,
                     std::uint64_t count) noexcept {
    auto rng = chunk_generator(seed, chunk);
    Stats stats;
    for (std::uint64_t i = 0; i < count; ++i) {
        const double z = inv_norm_cdf(rng.uniform_open());
        double s_t = gbm.terminal(z);
        double payoff = gbm.payoff(s_t);
        if (antithetic) {
            // Averaging over (Z, -Z) gives one sample; the pairs are i.i.d., the paths are not.
            const double s_t_anti = gbm.terminal(-z);
            payoff = 0.5 * (payoff + gbm.payoff(s_t_anti));
            s_t = 0.5 * (s_t + s_t_anti);
        }
        if constexpr (std::is_same_v<Stats, CovStats>) {
            stats.add(s_t, payoff);
        } else {
            stats.add(payoff);
        }
    }
    return stats;
}

}  // namespace

PricingResult price_european(const EuropeanOption& option, const McConfig& config) {
    validate(option, config);
    const auto start = std::chrono::steady_clock::now();

    const Gbm gbm{.spot = option.spot,
                  .strike = option.strike,
                  .drift = (option.rate - 0.5 * option.vol * option.vol) * option.maturity,
                  .diffusion = option.vol * std::sqrt(option.maturity),
                  .is_call = option.type == OptionType::Call};

    const std::uint64_t n_samples = sample_count(config);
    const std::uint64_t n_chunks = (n_samples + kPathsPerChunk - 1) / kPathsPerChunk;
    const unsigned n_threads = resolve_thread_count(config.n_threads, n_chunks);
    const auto chunk_size = [n_samples](std::uint64_t chunk) noexcept {
        return std::min(kPathsPerChunk, n_samples - chunk * kPathsPerChunk);
    };

    double mean = 0.0;      // undiscounted price estimate
    double variance = 0.0;  // sample variance of one sample of that estimator
    if (config.control_variate) {
        const CovStats s = run_chunks(n_chunks, n_threads, [&](std::uint64_t chunk) noexcept {
            return simulate_chunk<CovStats>(gbm, config.antithetic, config.seed, chunk,
                                            chunk_size(chunk));
        });
        // Y(b) = Y - b (X - E[X]) with X = S_T and E[X] = S_0 e^{rT}. b = Cov(X, Y) / Var(X)
        // minimizes Var(Y(b)); estimating b from the same sample adds only O(1/n) bias.
        const double expected_s_t = option.spot * std::exp(option.rate * option.maturity);
        const double b = s.m2_x > 0.0 ? s.c_xy / s.m2_x : 0.0;
        mean = s.mean_y - b * (s.mean_x - expected_s_t);
        // Sample variance of Y_i(b) is (m2_y - 2b c_xy + b^2 m2_x) / (n - 1), and with
        // b = c_xy / m2_x that simplifies to (m2_y - b c_xy) / (n - 1).
        variance = std::max(s.m2_y - b * s.c_xy, 0.0) / static_cast<double>(s.count - 1);
    } else {
        const RunningStats s = run_chunks(n_chunks, n_threads, [&](std::uint64_t chunk) noexcept {
            return simulate_chunk<RunningStats>(gbm, config.antithetic, config.seed, chunk,
                                                chunk_size(chunk));
        });
        mean = s.mean;
        variance = s.variance();
    }

    const double discount = std::exp(-option.rate * option.maturity);
    const double std_error = std::sqrt(variance / static_cast<double>(n_samples));
    const std::chrono::duration<double> elapsed = std::chrono::steady_clock::now() - start;
    return {discount * mean, discount * std_error, static_cast<std::uint64_t>(config.n_paths),
            elapsed.count()};
}

}  // namespace mcpricer
