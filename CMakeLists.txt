cmake_minimum_required(VERSION 3.26...4.4)
project(mcpricer LANGUAGES CXX)

option(MCPRICER_BUILD_PYTHON "Build the pybind11 extension module mcpricer._core" ON)
option(MCPRICER_SANITIZE "Build with AddressSanitizer + UndefinedBehaviorSanitizer" OFF)
option(MCPRICER_TSAN_TEST "Build the standalone ThreadSanitizer test (no Python)" OFF)

set(CMAKE_CXX_EXTENSIONS OFF)

find_package(Threads REQUIRED)

set(MCPRICER_SOURCES
  cpp/src/european.cpp
  cpp/src/heston.cpp
  cpp/src/path_dependent.cpp
  cpp/src/qmc.cpp
)

function(mcpricer_set_warnings target)
  if(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
    target_compile_options(${target} PRIVATE -Wall -Wextra -Wpedantic -Wconversion -Wshadow)
  endif()
endfunction()

if(MCPRICER_BUILD_PYTHON)
  set(PYBIND11_FINDPYTHON ON)
  find_package(pybind11 CONFIG REQUIRED)

  # Record how the extension was built; exposed to Python as mcpricer.build_info().
  string(TOUPPER "${CMAKE_BUILD_TYPE}" _build_type_upper)
  string(STRIP "${CMAKE_CXX_FLAGS} ${CMAKE_CXX_FLAGS_${_build_type_upper}}" MCPRICER_CXX_FLAGS)
  configure_file(cmake/build_info.hpp.in generated/mcpricer/build_info.hpp @ONLY)

  pybind11_add_module(_core MODULE cpp/bindings/module.cpp ${MCPRICER_SOURCES})
  target_compile_features(_core PRIVATE cxx_std_20)
  target_link_libraries(_core PRIVATE Threads::Threads)
  target_include_directories(_core PRIVATE
    "${CMAKE_CURRENT_SOURCE_DIR}/cpp/include"
    "${CMAKE_CURRENT_BINARY_DIR}/generated"
  )
  mcpricer_set_warnings(_core)

  if(MCPRICER_SANITIZE)
    set(_sanitizer_flags -fsanitize=address,undefined -fno-sanitize-recover=all -fno-omit-frame-pointer)
    target_compile_options(_core PRIVATE ${_sanitizer_flags})
    target_link_options(_core PRIVATE ${_sanitizer_flags})
    target_compile_definitions(_core PRIVATE _GLIBCXX_ASSERTIONS)
    # GCC's -Warray-bounds gives false positives on ASan-instrumented code (here inside
    # pybind11's headers). Keep it as a warning, but don't let it fail the -Werror build.
    if(CMAKE_CXX_COMPILER_ID STREQUAL "GNU")
      target_compile_options(_core PRIVATE -Wno-error=array-bounds)
    endif()
  endif()

  install(TARGETS _core LIBRARY DESTINATION mcpricer)
endif()

# A plain executable, so ThreadSanitizer instruments everything it runs: under Python, the
# interpreter itself would be uninstrumented.
if(MCPRICER_TSAN_TEST)
  add_executable(tsan_test tests/cpp/tsan_test.cpp ${MCPRICER_SOURCES})
  target_compile_features(tsan_test PRIVATE cxx_std_20)
  target_link_libraries(tsan_test PRIVATE Threads::Threads)
  target_include_directories(tsan_test PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/cpp/include")
  mcpricer_set_warnings(tsan_test)
  target_compile_options(tsan_test PRIVATE -fsanitize=thread -fno-omit-frame-pointer)
  target_link_options(tsan_test PRIVATE -fsanitize=thread)
endif()
