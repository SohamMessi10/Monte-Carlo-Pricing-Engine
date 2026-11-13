// Runs every multithreaded pricer under ThreadSanitizer and checks that 1 and 8 threads give
// bit-identical results. TSan reports any data race and makes the process exit non-zero.
#include <cstdio>
#include <cstdlib>

#include "mcpricer/european.hpp"
#include "mcpricer/heston.hpp"
#include "mcpricer/path_dependent.hpp"
#include "mcpricer/qmc.hpp"
#include "mcpricer/result.hpp"

using namespace mcpricer;

namespace {

int failures = 0;

void check(const char* name, const PricingResult& one, const PricingResult& many) {
    const bool same = one.estimate == many.estimate && one.std_error == many.std_error;
    std::printf("%-28s 1 thread %.10f, 8 threads %.10f  %s\n", name, one.estimate, many.estimate,
                same ? "identical" : "DIFFERENT");
    if (!same) {
        ++failures;
    }
}

}  // namespace

int main() {
    const EuropeanOption terms{.type = OptionType::Call,
                               .spot = 100.0,
                               .strike = 100.0,
                               .rate = 0.05,
                               .vol = 0.2,
                               .maturity = 1.0};
    const auto config = [](int threads) {
        return McConfig{.n_paths = 200'001, .seed = 7, .n_threads = threads};
    };

    {
        McConfig a = config(1);
        McConfig b = config(8);
        a.antithetic = b.antithetic = true;
        a.n_paths = b.n_paths = 200'002;
        a.control_variate = b.control_variate = true;
        check("european antithetic + cv", price_european(terms, a), price_european(terms, b));
    }
    {
        const AsianOption asian{.terms = terms, .n_steps = 16, .average = Average::Arithmetic};
        McConfig a = config(1);
        McConfig b = config(8);
        a.control_variate = b.control_variate = true;
        check("asian + geometric cv", price_asian(asian, a), price_asian(asian, b));
    }
    {
        const UpAndOutOption barrier{.terms = terms, .barrier = 130.0, .n_steps = 16};
        check("up-and-out", price_up_and_out(barrier, config(1)),
              price_up_and_out(barrier, config(8)));
    }
    {
        const QmcOption qmc{.terms = terms, .n_steps = 16, .payoff = Payoff::ArithmeticAsian};
        const auto qmc_config = [](int threads) {
            return QmcConfig{
                .n_points = 50'000, .n_replications = 4, .seed = 7, .n_threads = threads};
        };
        check("qmc arithmetic asian", price_qmc(qmc, qmc_config(1)), price_qmc(qmc, qmc_config(8)));
    }
    {
        const HestonOption heston{.type = OptionType::Call,
                                  .spot = 100.0,
                                  .strike = 100.0,
                                  .rate = 0.03,
                                  .maturity = 1.0,
                                  .v0 = 0.04,
                                  .kappa = 2.0,
                                  .theta = 0.04,
                                  .xi = 0.3,
                                  .rho = -0.7,
                                  .n_steps = 16};
        check("heston", price_heston(heston, config(1)), price_heston(heston, config(8)));
    }

    std::printf("%s\n", failures == 0 ? "all identical" : "MISMATCH");
    return failures == 0 ? EXIT_SUCCESS : EXIT_FAILURE;
}
