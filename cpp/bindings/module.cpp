// Python bindings for the mcpricer C++ core (module mcpricer._core).
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include <cstdint>
#include <stdexcept>

#include "mcpricer/build_info.hpp"
#include "mcpricer/european.hpp"
#include "mcpricer/normal.hpp"
#include "mcpricer/path_dependent.hpp"
#include "mcpricer/qmc.hpp"
#include "mcpricer/result.hpp"

namespace py = pybind11;

PYBIND11_MODULE(_core, m) {
    m.doc() = "mcpricer C++ core";

    m.def(
        "build_info",
        [] {
            py::dict info;
            info["compiler"] = mcpricer::build::compiler;
            info["build_type"] = mcpricer::build::build_type;
            info["cxx_flags"] = mcpricer::build::cxx_flags;
            info["cxx_standard"] = __cplusplus;
            info["sanitizers"] = mcpricer::build::sanitizers;
            return info;
        },
        "Compiler, build type, flags and C++ standard this extension was built with.");

    py::enum_<mcpricer::OptionType>(m, "OptionType")
        .value("CALL", mcpricer::OptionType::Call)
        .value("PUT", mcpricer::OptionType::Put);

    py::class_<mcpricer::PricingResult>(m, "PricingResult")
        .def_readonly("estimate", &mcpricer::PricingResult::estimate)
        .def_readonly("std_error", &mcpricer::PricingResult::std_error)
        .def_readonly("n_paths", &mcpricer::PricingResult::n_paths)
        .def_readonly("elapsed_seconds", &mcpricer::PricingResult::elapsed_seconds)
        .def("__repr__", [](const mcpricer::PricingResult& r) {
            return py::str("PricingResult(estimate={!r}, std_error={!r}, n_paths={!r}, "
                           "elapsed_seconds={!r})")
                .format(r.estimate, r.std_error, r.n_paths, r.elapsed_seconds);
        });

    // std::invalid_argument thrown in C++ reaches Python as ValueError.
    // call_guard releases the GIL while C++ runs; it touches no Python objects.
    m.def(
        "price_european",
        [](mcpricer::OptionType option_type, double spot, double strike, double rate,
           double vol, double maturity, std::int64_t n_paths, std::uint64_t seed,
           int n_threads, bool antithetic, bool control_variate) {
            return mcpricer::price_european({.type = option_type,
                                             .spot = spot,
                                             .strike = strike,
                                             .rate = rate,
                                             .vol = vol,
                                             .maturity = maturity},
                                            {.n_paths = n_paths,
                                             .seed = seed,
                                             .n_threads = n_threads,
                                             .antithetic = antithetic,
                                             .control_variate = control_variate});
        },
        py::kw_only(), py::arg("option_type"), py::arg("spot"), py::arg("strike"),
        py::arg("rate"), py::arg("vol"), py::arg("maturity"), py::arg("n_paths"),
        py::arg("seed"), py::arg("n_threads") = 0, py::arg("antithetic") = false,
        py::arg("control_variate") = false, py::call_guard<py::gil_scoped_release>(),
        "Price a European call or put under GBM by exact Monte Carlo simulation.\n\n"
        "n_threads=0 uses one thread per hardware thread. The result is bit-identical for\n"
        "every n_threads. antithetic pairs each normal draw Z with -Z (n_paths must be even).\n"
        "control_variate uses S_T, with known mean S_0 exp(rT), as a control. n_paths always\n"
        "counts simulated terminal prices, so methods compare at equal path counts.");

    py::enum_<mcpricer::Average>(m, "Average")
        .value("ARITHMETIC", mcpricer::Average::Arithmetic)
        .value("GEOMETRIC", mcpricer::Average::Geometric);

    m.def(
        "price_asian",
        [](mcpricer::OptionType option_type, double spot, double strike, double rate,
           double vol, double maturity, int n_steps, std::int64_t n_paths, std::uint64_t seed,
           mcpricer::Average average, int n_threads, bool control_variate) {
            return mcpricer::price_asian(
                {.terms = {.type = option_type,
                           .spot = spot,
                           .strike = strike,
                           .rate = rate,
                           .vol = vol,
                           .maturity = maturity},
                 .n_steps = n_steps,
                 .average = average},
                {.n_paths = n_paths,
                 .seed = seed,
                 .n_threads = n_threads,
                 .control_variate = control_variate});
        },
        py::kw_only(), py::arg("option_type"), py::arg("spot"), py::arg("strike"),
        py::arg("rate"), py::arg("vol"), py::arg("maturity"), py::arg("n_steps"),
        py::arg("n_paths"), py::arg("seed"), py::arg("average") = mcpricer::Average::Arithmetic,
        py::arg("n_threads") = 0, py::arg("control_variate") = false,
        py::call_guard<py::gil_scoped_release>(),
        "Price a discretely monitored Asian call or put under GBM.\n\n"
        "The average is over S(t_i), t_i = i T / n_steps, i = 1..n_steps. control_variate\n"
        "(arithmetic average only) uses the geometric Asian, whose price is known exactly.");

    m.def(
        "price_up_and_out",
        [](mcpricer::OptionType option_type, double spot, double strike, double rate,
           double vol, double maturity, double barrier, int n_steps, std::int64_t n_paths,
           std::uint64_t seed, int n_threads) {
            return mcpricer::price_up_and_out(
                {.terms = {.type = option_type,
                           .spot = spot,
                           .strike = strike,
                           .rate = rate,
                           .vol = vol,
                           .maturity = maturity},
                 .barrier = barrier,
                 .n_steps = n_steps},
                {.n_paths = n_paths, .seed = seed, .n_threads = n_threads});
        },
        py::kw_only(), py::arg("option_type"), py::arg("spot"), py::arg("strike"),
        py::arg("rate"), py::arg("vol"), py::arg("maturity"), py::arg("barrier"),
        py::arg("n_steps"), py::arg("n_paths"), py::arg("seed"), py::arg("n_threads") = 0,
        py::call_guard<py::gil_scoped_release>(),
        "Price a discretely monitored up-and-out call or put under GBM.\n\n"
        "The option pays nothing if S(t_i) >= barrier at any t_i = i T / n_steps.");

    m.def(
        "_geometric_asian",
        [](mcpricer::OptionType option_type, double spot, double strike, double rate,
           double vol, double maturity, int n_steps) {
            return mcpricer::geometric_asian_price({.type = option_type,
                                                    .spot = spot,
                                                    .strike = strike,
                                                    .rate = rate,
                                                    .vol = vol,
                                                    .maturity = maturity},
                                                   n_steps);
        },
        py::kw_only(), py::arg("option_type"), py::arg("spot"), py::arg("strike"),
        py::arg("rate"), py::arg("vol"), py::arg("maturity"), py::arg("n_steps"),
        "C++ geometric Asian closed form (the control variate's mean). Exposed for tests.");

    py::enum_<mcpricer::Payoff>(m, "Payoff")
        .value("EUROPEAN", mcpricer::Payoff::European)
        .value("ARITHMETIC_ASIAN", mcpricer::Payoff::ArithmeticAsian)
        .value("GEOMETRIC_ASIAN", mcpricer::Payoff::GeometricAsian);

    m.def(
        "price_qmc",
        [](mcpricer::OptionType option_type, double spot, double strike, double rate,
           double vol, double maturity, int n_steps, std::int64_t n_points, int n_replications,
           std::uint64_t seed, mcpricer::Payoff payoff, bool brownian_bridge, int n_threads) {
            return mcpricer::price_qmc({.terms = {.type = option_type,
                                                  .spot = spot,
                                                  .strike = strike,
                                                  .rate = rate,
                                                  .vol = vol,
                                                  .maturity = maturity},
                                        .n_steps = n_steps,
                                        .payoff = payoff},
                                       {.n_points = n_points,
                                        .n_replications = n_replications,
                                        .seed = seed,
                                        .n_threads = n_threads,
                                        .brownian_bridge = brownian_bridge});
        },
        py::kw_only(), py::arg("option_type"), py::arg("spot"), py::arg("strike"),
        py::arg("rate"), py::arg("vol"), py::arg("maturity"), py::arg("n_steps"),
        py::arg("n_points"), py::arg("n_replications"), py::arg("seed"),
        py::arg("payoff") = mcpricer::Payoff::European, py::arg("brownian_bridge") = true,
        py::arg("n_threads") = 0, py::call_guard<py::gil_scoped_release>(),
        "Randomized QMC price: Sobol (Joe-Kuo) points with independent random digital shifts.\n\n"
        "Each of n_replications shifts gives an independent unbiased estimate from n_points\n"
        "points; the result is their mean, and std_error comes from their spread.");

    m.def("_sobol_points", &mcpricer::sobol_points, py::arg("n"), py::arg("dims"),
          "First n unshifted Sobol points (Gray-code order) in dims dimensions. For tests.");

    m.def(
        "_norm_inv",
        [](double p) {
            if (!(p > 0.0 && p < 1.0)) {
                throw std::invalid_argument("p must lie in the open interval (0, 1)");
            }
            return mcpricer::inv_norm_cdf(p);
        },
        py::arg("p"), "Inverse standard normal CDF (Wichura AS241). Exposed for tests.");
}
