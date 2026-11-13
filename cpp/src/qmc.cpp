#include "mcpricer/qmc.hpp"

#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <vector>

#include "mcpricer/brownian_bridge.hpp"
#include "mcpricer/normal.hpp"
#include "mcpricer/parallel.hpp"
#include "mcpricer/rng.hpp"
#include "mcpricer/sobol.hpp"
#include "mcpricer/stats.hpp"
#include "mcpricer/validate.hpp"

namespace mcpricer {

namespace {

constexpr std::int64_t kMaxPoints = std::int64_t{1} << 32;  // Gray-code index fits 32 bits
constexpr int kMaxReplications = 4096;

void validate(const QmcOption& option, const QmcConfig& config) {
    validate_terms(option.terms);
    require(option.n_steps >= 1 && option.n_steps <= kSobolMaxDims,
            "n_steps must be between 1 and 1024 for QMC (one Sobol dimension per step)");
    require(config.n_points >= 1 && config.n_points <= kMaxPoints,
            "n_points must be between 1 and 2^32");
    require(config.n_replications >= 2 && config.n_replications <= kMaxReplications,
            "n_replications must be between 2 and 4096 (independent shifts give the error bar)");
    require(config.n_threads >= 0 && config.n_threads <= kMaxThreads,
            "n_threads must be between 0 and 1024 (0 means one per hardware thread)");
}

// Everything a chunk needs; read-only while threads run.
struct Plan {
    const QmcOption& option;
    const QmcConfig& config;
    const std::vector<SobolDirections>& directions;
    std::vector<std::uint32_t> shifts;  // n_replications x n_steps random digital shifts
    BrownianBridge bridge;
    std::uint64_t chunks_per_rep;
    double log_spot;
    double drift_rate;  // r - vol^2 / 2
    double dt;
    double sqrt_dt;
};

double vanilla_payoff(bool is_call, double strike, double s) noexcept {
    return is_call ? std::max(s - strike, 0.0) : std::max(strike - s, 0.0);
}

// Undiscounted payoffs of one block of up to kPathsPerChunk points of one replication.
RunningStats qmc_chunk(const Plan& plan, std::uint64_t chunk) noexcept {
    const int m = plan.option.n_steps;
    const auto n_dims = static_cast<std::size_t>(m);
    const std::uint64_t rep = chunk / plan.chunks_per_rep;
    const std::uint64_t first = (chunk % plan.chunks_per_rep) * kPathsPerChunk;
    const std::uint64_t count =
        std::min(kPathsPerChunk, static_cast<std::uint64_t>(plan.config.n_points) - first);
    const std::uint32_t* shift = plan.shifts.data() + rep * n_dims;
    const EuropeanOption& terms = plan.option.terms;
    const bool is_call = terms.type == OptionType::Call;

    // Fixed-size buffers on this thread's stack (~20 KB): no allocation inside the hot loop.
    std::array<std::uint32_t, kSobolMaxDims> x{};
    std::array<double, kSobolMaxDims> z{};
    std::array<double, kSobolMaxDims + 1> w{};
    for (std::size_t j = 0; j < n_dims; ++j) {
        x[j] = sobol_component(plan.directions[j], first);
    }

    RunningStats stats;
    for (std::uint64_t i = 0; i < count; ++i) {
        // Digital shift: XOR with a uniform random integer, then the midpoint of the 2^-32
        // cell, so u is in (0, 1) and never exactly 0 or 1.
        for (std::size_t j = 0; j < n_dims; ++j) {
            const double u = (static_cast<double>(x[j] ^ shift[j]) + 0.5) * 0x1.0p-32;
            z[j] = inv_norm_cdf(u);
        }
        if (plan.config.brownian_bridge) {
            plan.bridge.build(z.data(), w.data());
        } else {
            w[0] = 0.0;
            for (std::size_t j = 0; j < n_dims; ++j) {
                w[j + 1] = w[j] + plan.sqrt_dt * z[j];
            }
        }

        // S(t_i) = S_0 exp((r - vol^2 / 2) t_i + vol W(t_i)): exact for GBM at every grid point.
        const auto log_s = [&](std::size_t idx) {
            return plan.log_spot + plan.drift_rate * plan.dt * static_cast<double>(idx) +
                   terms.vol * w[idx];
        };
        double payoff = 0.0;
        switch (plan.option.payoff) {
            case Payoff::European:
                payoff = vanilla_payoff(is_call, terms.strike, std::exp(log_s(n_dims)));
                break;
            case Payoff::ArithmeticAsian: {
                double sum = 0.0;
                for (std::size_t idx = 1; idx <= n_dims; ++idx) {
                    sum += std::exp(log_s(idx));
                }
                payoff = vanilla_payoff(is_call, terms.strike, sum / static_cast<double>(m));
                break;
            }
            case Payoff::GeometricAsian: {
                double sum = 0.0;
                for (std::size_t idx = 1; idx <= n_dims; ++idx) {
                    sum += log_s(idx);
                }
                payoff =
                    vanilla_payoff(is_call, terms.strike, std::exp(sum / static_cast<double>(m)));
                break;
            }
        }
        stats.add(payoff);

        if (i + 1 < count) {  // advance to point first + i + 1 (Gray code: one XOR per dim)
            const unsigned bit = sobol_next_bit(first + i);
            for (std::size_t j = 0; j < n_dims; ++j) {
                x[j] ^= plan.directions[j][bit];
            }
        }
    }
    return stats;
}

}  // namespace

PricingResult price_qmc(const QmcOption& option, const QmcConfig& config) {
    validate(option, config);
    const auto start = std::chrono::steady_clock::now();
    const EuropeanOption& terms = option.terms;
    const auto n_dims = static_cast<std::size_t>(option.n_steps);
    const auto n_reps = static_cast<std::uint64_t>(config.n_replications);
    const auto n_points = static_cast<std::uint64_t>(config.n_points);

    Plan plan{.option = option,
              .config = config,
              .directions = sobol_directions(),
              .shifts = std::vector<std::uint32_t>(n_reps * n_dims),
              .bridge = BrownianBridge(option.n_steps, terms.maturity),
              .chunks_per_rep = (n_points + kPathsPerChunk - 1) / kPathsPerChunk,
              .log_spot = std::log(terms.spot),
              .drift_rate = terms.rate - 0.5 * terms.vol * terms.vol,
              .dt = terms.maturity / static_cast<double>(option.n_steps),
              .sqrt_dt = std::sqrt(terms.maturity / static_cast<double>(option.n_steps))};
    // Replication r's shift depends only on (seed, r), never on the thread count.
    for (std::uint64_t r = 0; r < n_reps; ++r) {
        auto rng = chunk_generator(config.seed, r);
        for (std::size_t j = 0; j < n_dims; ++j) {
            plan.shifts[r * n_dims + j] = static_cast<std::uint32_t>(rng.next() >> 32);
        }
    }

    const std::uint64_t n_chunks = n_reps * plan.chunks_per_rep;
    const auto partial =
        collect_chunks(n_chunks, resolve_thread_count(config.n_threads, n_chunks),
                       [&plan](std::uint64_t chunk) noexcept { return qmc_chunk(plan, chunk); });

    // One estimate per replication (its chunks merged in order); the replications are i.i.d.,
    // so their spread gives an honest standard error.
    RunningStats replications;
    for (std::uint64_t r = 0; r < n_reps; ++r) {
        RunningStats rep;
        for (std::uint64_t b = 0; b < plan.chunks_per_rep; ++b) {
            rep.merge(partial[r * plan.chunks_per_rep + b]);
        }
        replications.add(rep.mean);
    }

    const double discount = std::exp(-terms.rate * terms.maturity);
    const double std_error =
        std::sqrt(replications.variance() / static_cast<double>(n_reps));
    const std::chrono::duration<double> elapsed = std::chrono::steady_clock::now() - start;
    return {discount * replications.mean, discount * std_error, n_points * n_reps,
            elapsed.count()};
}

std::vector<std::vector<double>> sobol_points(std::int64_t n, int dims) {
    require(n >= 0 && n <= kMaxPoints, "n must be between 0 and 2^32");
    require(dims >= 1 && dims <= kSobolMaxDims, "dims must be between 1 and 1024");
    const auto& directions = sobol_directions();
    std::vector<std::vector<double>> points(static_cast<std::size_t>(n));
    for (std::size_t i = 0; i < points.size(); ++i) {
        points[i].reserve(static_cast<std::size_t>(dims));
        for (std::size_t j = 0; j < static_cast<std::size_t>(dims); ++j) {
            points[i].push_back(
                static_cast<double>(sobol_component(directions[j], i)) * 0x1.0p-32);
        }
    }
    return points;
}

}  // namespace mcpricer
