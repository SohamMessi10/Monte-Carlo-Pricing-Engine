// Python bindings for the mcpricer C++ core (module mcpricer._core).
#include <pybind11/pybind11.h>

#include "mcpricer/build_info.hpp"

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
}
