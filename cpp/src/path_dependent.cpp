#include "mcpricer/path_dependent.hpp"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <type_traits>

#include "mcpricer/normal.hpp"
#include "mcpricer/parallel.hpp"
#include "mcpricer/rng.hpp"
#include "mcpricer/stats.hpp"
#include "mcpricer/validate.hpp"

namespace mcpricer {

namespace {

using Clock = std::chrono::steady_clock;

// One time step of exact GBM in log space: log S(t + dt) = log S(t) + drift + diffusion Z.
struct Grid {
    double log_spot;
    double drift;      // (r - vol^2 / 2) dt
    double diffusion;  // vol sqrt(dt)
    int n_steps;
};

Grid make_grid(const EuropeanOption& terms, int n_steps) {
    const double dt = terms.maturity / static_cast<double>(n_steps);
    return {.log_spot = std::log(terms.spot),
            .drift = (terms.rate - 0.5 * terms.vol * terms.vol) * dt,
            .diffusion = terms.vol * std::sqrt(dt),
            .n_steps = n_steps};
}

double vanilla_payoff(bool is_call, double strike, double s) noexcept {
    return is_call ? std::max(s - strike, 0.0) : std::max(strike - s, 0.0);
}

void validate_common(const EuropeanOption& terms, int n_steps, const McConfig& config) {
    validate_terms(terms);
    validate_paths_and_threads(config);
    require(n_steps >= 1 && n_steps <= kMaxSteps, "n_steps must be between 1 and 100000");
    require(!config.antithetic, "antithetic=True is not supported for path-dependent options");
}

struct Chunking {
    std::uint64_t n_paths;
    std::uint64_t n_chunks;
    unsigned n_threads;

    explicit Chunking(const McConfig& config)
        : n_paths(static_cast<std::uint64_t>(config.n_paths)),
          n_chunks((n_paths + kPathsPerChunk - 1) / kPathsPerChunk),
          n_threads(resolve_thread_count(config.n_threads, n_chunks)) {}

    std::uint64_t size(std::uint64_t chunk) const noexcept {
        return std::min(kPathsPerChunk, n_paths - chunk * kPathsPerChunk);
    }
};

PricingResult finish(const EuropeanOption& terms, double mean, double variance,
                     std::uint64_t n_paths, Clock::time_point start) {
    const double discount = std::exp(-terms.rate * terms.maturity);
    const double std_error = std::sqrt(variance / static_cast<double>(n_paths));
    const std::chrono::duration<double> elapsed = Clock::now() - start;
    return {discount * mean, discount * std_error, n_paths, elapsed.count()};
}

// RunningStats: the payoff of the requested average only.
// CovStats: x = geometric-average payoff (the control), y = arithmetic-average payoff.
template <class Stats>
Stats asian_chunk(const Grid& grid, bool is_call, double strike, Average average,
                  std::uint64_t seed, std::uint64_t chunk, std::uint64_t count) noexcept {
    auto rng = chunk_generator(seed, chunk);
    const double m = static_cast<double>(grid.n_steps);
    Stats stats;
    for (std::uint64_t i = 0; i < count; ++i) {
        double log_s = grid.log_spot;
        double sum_s = 0.0;
        double sum_log_s = 0.0;
        for (int k = 0; k < grid.n_steps; ++k) {
            log_s += grid.drift + grid.diffusion * inv_norm_cdf(rng.uniform_open());
            sum_s += std::exp(log_s);
            sum_log_s += log_s;
        }
        const double arithmetic = vanilla_payoff(is_call, strike, sum_s / m);
        const double geometric = vanilla_payoff(is_call, strike, std::exp(sum_log_s / m));
        if constexpr (std::is_same_v<Stats, CovStats>) {
            stats.add(geometric, arithmetic);
        } else {
            stats.add(average == Average::Arithmetic ? arithmetic : geometric);
        }
    }
    return stats;
}

RunningStats up_and_out_chunk(const Grid& grid, bool is_call, double strike, double log_barrier,
                              std::uint64_t seed, std::uint64_t chunk,
                              std::uint64_t count) noexcept {
    auto rng = chunk_generator(seed, chunk);
    RunningStats stats;
    for (std::uint64_t i = 0; i < count; ++i) {
        double log_s = grid.log_spot;
        bool alive = true;
        // No early exit on knock-out: every path draws exactly n_steps normals, so for a given
        // seed the paths are the same for every barrier level (common random numbers). The
        // price is then monotone in the barrier path by path, not just on average.
        for (int k = 0; k < grid.n_steps; ++k) {
            log_s += grid.drift + grid.diffusion * inv_norm_cdf(rng.uniform_open());
            alive = alive && log_s < log_barrier;
        }
        stats.add(alive ? vanilla_payoff(is_call, strike, std::exp(log_s)) : 0.0);
    }
    return stats;
}

}  // namespace

double geometric_asian_price(const EuropeanOption& terms, int n_steps) {
    validate_terms(terms);
    require(n_steps >= 1 && n_steps <= kMaxSteps, "n_steps must be between 1 and 100000");
    // log G = mean of log S(t_i) is normal (Kemna & Vorst 1990, discrete monitoring).
    const double m = static_cast<double>(n_steps);
    const double mean = std::log(terms.spot) + (terms.rate - 0.5 * terms.vol * terms.vol) *
                                                   terms.maturity * (m + 1.0) / (2.0 * m);
    const double var =
        terms.vol * terms.vol * terms.maturity * (m + 1.0) * (2.0 * m + 1.0) / (6.0 * m * m);
    const double sd = std::sqrt(var);
    const double d1 = (mean - std::log(terms.strike) + var) / sd;
    const double d2 = d1 - sd;
    const double forward = std::exp(mean + 0.5 * var);  // E[G]
    const auto cdf = [](double x) { return 0.5 * std::erfc(-x / std::sqrt(2.0)); };
    const double undiscounted = terms.type == OptionType::Call
                                    ? forward * cdf(d1) - terms.strike * cdf(d2)
                                    : terms.strike * cdf(-d2) - forward * cdf(-d1);
    return std::exp(-terms.rate * terms.maturity) * undiscounted;
}

PricingResult price_asian(const AsianOption& option, const McConfig& config) {
    const EuropeanOption& terms = option.terms;
    validate_common(terms, option.n_steps, config);
    if (config.control_variate) {
        require(option.average == Average::Arithmetic,
                "control_variate=True needs average=ARITHMETIC (the geometric one is the control)");
        require(config.n_paths >= 3, "with control_variate=True, n_paths must be at least 3");
    }
    const auto start = Clock::now();

    const Grid grid = make_grid(terms, option.n_steps);
    const bool is_call = terms.type == OptionType::Call;
    const Chunking chunks(config);

    if (config.control_variate) {
        const CovStats s =
            run_chunks(chunks.n_chunks, chunks.n_threads, [&](std::uint64_t chunk) noexcept {
                return asian_chunk<CovStats>(grid, is_call, terms.strike, option.average,
                                             config.seed, chunk, chunks.size(chunk));
            });
        // E[geometric payoff], undiscounted, from the closed form.
        const double exact_geometric = geometric_asian_price(terms, option.n_steps) *
                                       std::exp(terms.rate * terms.maturity);
        const auto cv = s.control_variate(exact_geometric);
        return finish(terms, cv.mean, cv.variance, chunks.n_paths, start);
    }
    const RunningStats s =
        run_chunks(chunks.n_chunks, chunks.n_threads, [&](std::uint64_t chunk) noexcept {
            return asian_chunk<RunningStats>(grid, is_call, terms.strike, option.average,
                                             config.seed, chunk, chunks.size(chunk));
        });
    return finish(terms, s.mean, s.variance(), chunks.n_paths, start);
}

PricingResult price_up_and_out(const UpAndOutOption& option, const McConfig& config) {
    const EuropeanOption& terms = option.terms;
    validate_common(terms, option.n_steps, config);
    require(positive_finite(option.barrier), "barrier must be positive and finite");
    require(option.barrier > terms.spot, "barrier must be above spot (otherwise already knocked out)");
    require(!config.control_variate, "control_variate=True is not supported for barrier options");
    const auto start = Clock::now();

    const Grid grid = make_grid(terms, option.n_steps);
    const bool is_call = terms.type == OptionType::Call;
    const double log_barrier = std::log(option.barrier);
    const Chunking chunks(config);

    const RunningStats s =
        run_chunks(chunks.n_chunks, chunks.n_threads, [&](std::uint64_t chunk) noexcept {
            return up_and_out_chunk(grid, is_call, terms.strike, log_barrier, config.seed, chunk,
                                    chunks.size(chunk));
        });
    return finish(terms, s.mean, s.variance(), chunks.n_paths, start);
}

}  // namespace mcpricer
