// Brownian-bridge construction of W on the grid t_i = i T / m, i = 1..m.
#pragma once

#include <cmath>
#include <cstddef>
#include <utility>
#include <vector>

namespace mcpricer {

// The first normal sets W(T); each later one fills the midpoint of an interval whose ends are
// already known, breadth first. So the first (best-distributed) Sobol coordinates decide the
// large-scale shape of the path, and later ones only add detail. Each step uses
//   W(t_mid) | W(t_l), W(t_r) ~ N(((t_r - t_mid) W(t_l) + (t_mid - t_l) W(t_r)) / (t_r - t_l),
//                                 (t_mid - t_l)(t_r - t_mid) / (t_r - t_l)).
class BrownianBridge {
public:
    BrownianBridge(int n_steps, double maturity) {
        const double dt = maturity / static_cast<double>(n_steps);
        steps_.reserve(static_cast<std::size_t>(n_steps));
        // W(T) from W(0) = 0: left = right = 0 and both weights 0.
        steps_.push_back({n_steps, 0, 0, 0.0, 0.0, std::sqrt(maturity)});
        std::vector<std::pair<int, int>> queue{{0, n_steps}};
        for (std::size_t head = 0; head < queue.size(); ++head) {
            const auto [l, r] = queue[head];
            if (r - l < 2) {
                continue;
            }
            const int mid = l + (r - l) / 2;
            const double span = static_cast<double>(r - l);
            steps_.push_back({mid, l, r, static_cast<double>(r - mid) / span,
                              static_cast<double>(mid - l) / span,
                              std::sqrt(dt * static_cast<double>(mid - l) *
                                        static_cast<double>(r - mid) / span)});
            queue.emplace_back(l, mid);
            queue.emplace_back(mid, r);
        }
    }

    // Fills w[0..m] (w[0] = 0) from z[0..m-1], z[k] being the normal for construction step k.
    void build(const double* z, double* w) const noexcept {
        w[0] = 0.0;
        for (std::size_t k = 0; k < steps_.size(); ++k) {
            const Step& s = steps_[k];
            w[s.index] = s.w_left * w[s.left] + s.w_right * w[s.right] + s.sigma * z[k];
        }
    }

    std::size_t size() const noexcept { return steps_.size(); }

private:
    struct Step {
        int index;  // which W(t_i) this step sets
        int left;   // index of the known left end (0 means W(0) = 0)
        int right;  // index of the known right end
        double w_left;
        double w_right;
        double sigma;  // conditional standard deviation
    };
    std::vector<Step> steps_;
};

}  // namespace mcpricer
