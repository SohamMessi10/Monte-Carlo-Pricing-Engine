cmake_minimum_required(VERSION 3.26...4.4)
project(mcpricer LANGUAGES CXX)

option(MCPRICER_SANITIZE "Build with AddressSanitizer + UndefinedBehaviorSanitizer" OFF)

set(CMAKE_CXX_EXTENSIONS OFF)

set(PYBIND11_FINDPYTHON ON)
find_package(pybind11 CONFIG REQUIRED)

# Record how the extension was built; exposed to Python as mcpricer.build_info().
string(TOUPPER "${CMAKE_BUILD_TYPE}" _build_type_upper)
string(STRIP "${CMAKE_CXX_FLAGS} ${CMAKE_CXX_FLAGS_${_build_type_upper}}" MCPRICER_CXX_FLAGS)
configure_file(cmake/build_info.hpp.in generated/mcpricer/build_info.hpp @ONLY)

pybind11_add_module(_core MODULE cpp/bindings/module.cpp)
target_compile_features(_core PRIVATE cxx_std_20)
target_include_directories(_core PRIVATE "${CMAKE_CURRENT_BINARY_DIR}/generated")

if(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
  target_compile_options(_core PRIVATE -Wall -Wextra -Wpedantic -Wconversion -Wshadow)
endif()

if(MCPRICER_SANITIZE)
  set(_sanitizer_flags -fsanitize=address,undefined -fno-sanitize-recover=all -fno-omit-frame-pointer)
  target_compile_options(_core PRIVATE ${_sanitizer_flags})
  target_link_options(_core PRIVATE ${_sanitizer_flags})
  target_compile_definitions(_core PRIVATE _GLIBCXX_ASSERTIONS)
endif()

install(TARGETS _core LIBRARY DESTINATION mcpricer)
