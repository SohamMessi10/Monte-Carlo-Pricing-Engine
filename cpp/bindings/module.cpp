// Python bindings for the mcpricer C++ core (module mcpricer._core).
#include <pybind11/pybind11.h>

#include <cstdint>
#include <stdexcept>

#include "mcpricer/build_info.hpp"
#include "mcpricer/european.hpp"
#include "mcpricer/normal.hpp"
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
           double vol, double maturity, std::int64_t n_paths, std::uint64_t seed) {
            return mcpricer::price_european(
                {.type = option_type,
                 .spot = spot,
                 .strike = strike,
                 .rate = rate,
                 .vol = vol,
                 .maturity = maturity},
                {.n_paths = n_paths, .seed = seed});
        },
        py::kw_only(), py::arg("option_type"), py::arg("spot"), py::arg("strike"),
        py::arg("rate"), py::arg("vol"), py::arg("maturity"), py::arg("n_paths"),
        py::arg("seed"), py::call_guard<py::gil_scoped_release>(),
        "Price a European call or put under GBM by exact Monte Carlo simulation.");

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
