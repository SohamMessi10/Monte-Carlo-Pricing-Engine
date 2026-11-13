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

// Running means, variances and covariance of pairs (x, y): x is a control variate, y the payoff.
// The y updates are the same operations as RunningStats, so mean_y has the same bits.
struct CovStats {
    std::uint64_t count = 0;
    double mean_x = 0.0;
    double mean_y = 0.0;
    double m2_x = 0.0;  // sum of (x - mean_x)^2
    double m2_y = 0.0;  // sum of (y - mean_y)^2
    double c_xy = 0.0;  // sum of (x - mean_x)(y - mean_y)

    void add(double x, double y) noexcept {
        ++count;
        const double n = static_cast<double>(count);
        const double dx = x - mean_x;
        const double dy = y - mean_y;
        mean_x += dx / n;
        mean_y += dy / n;
        m2_x += dx * (x - mean_x);
        m2_y += dy * (y - mean_y);
        c_xy += dx * (y - mean_y);
    }

    void merge(const CovStats& other) noexcept {
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
        const double dx = other.mean_x - mean_x;
        const double dy = other.mean_y - mean_y;
        mean_x += dx * (n_b / n);
        mean_y += dy * (n_b / n);
        m2_x += other.m2_x + dx * dx * (n_a * n_b / n);
        m2_y += other.m2_y + dy * dy * (n_a * n_b / n);
        c_xy += other.c_xy + dx * dy * (n_a * n_b / n);
        count += other.count;
    }
};

}  // namespace mcpricer
