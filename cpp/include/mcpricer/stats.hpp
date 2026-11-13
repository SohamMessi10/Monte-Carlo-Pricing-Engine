// Running mean and variance, mergeable across chunks.
#pragma once

#include <cstdint>

namespace mcpricer {

// Welford's algorithm. It avoids the cancellation of sum(x^2) - n * mean^2.
struct RunningStats {
    std::uint64_t count = 0;
    double mean = 0.0;
    double m2 = 0.0;  // sum of squared deviations from the mean

    void add(double x) noexcept {
        ++count;
        const double delta = x - mean;
        mean += delta / static_cast<double>(count);
        m2 += delta * (x - mean);
    }

    // Chan, Golub, LeVeque pairwise merge. Floating-point addition is not associative, so the
    // caller merges chunks in chunk-index order to get the same bits on every run.
    void merge(const RunningStats& other) noexcept {
        if (other.count == 0) {
            return;
        }
        if (count == 0) {
            *this = other;
            return;
        }
        const double n_a = static_cast<double>(count);
        const double n_b = static_cast<double>(other.count);
        const double n = n_a + n_b;
        const double delta = other.mean - mean;
        mean += delta * (n_b / n);
        m2 += other.m2 + delta * delta * (n_a * n_b / n);
        count += other.count;
    }

    // Unbiased sample variance.
    double variance() const noexcept {
        return count > 1 ? m2 / static_cast<double>(count - 1) : 0.0;
    }
};

}  // namespace mcpricer
