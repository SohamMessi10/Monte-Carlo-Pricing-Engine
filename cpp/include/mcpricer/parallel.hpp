// Run chunks of paths on a pool of std::threads and merge the results deterministically.
#pragma once

#include <algorithm>
#include <atomic>
#include <cstdint>
#include <system_error>
#include <thread>
#include <type_traits>
#include <vector>

#include "mcpricer/stats.hpp"

namespace mcpricer {

inline constexpr int kMaxThreads = 1024;

// requested == 0 means one thread per hardware thread. Never more threads than chunks.
inline unsigned resolve_thread_count(int requested, std::uint64_t n_chunks) noexcept {
    const std::uint64_t wanted = requested > 0 ? static_cast<std::uint64_t>(requested)
                                               : std::max(1u, std::thread::hardware_concurrency());
    return static_cast<unsigned>(std::min(wanted, n_chunks));
}

// Calls simulate(chunk) once for every chunk in [0, n_chunks) and merges the results in chunk
// order. Threads take chunks from a shared counter, so which thread runs which chunk varies
// from run to run. The result doesn't: each chunk's numbers depend only on its index, and the
// merge order is fixed. So the output is bit-identical for any thread count.
// Stats is whatever simulate returns (RunningStats, CovStats, ...); it needs merge().
template <class ChunkFn>
auto run_chunks(std::uint64_t n_chunks, unsigned n_threads, const ChunkFn& simulate) {
    using Stats = std::invoke_result_t<const ChunkFn&, std::uint64_t>;
    // An exception escaping a std::thread calls std::terminate, so simulate must not throw.
    static_assert(std::is_nothrow_invocable_v<const ChunkFn&, std::uint64_t>);

    std::vector<Stats> partial(n_chunks);
    std::atomic<std::uint64_t> next_chunk{0};

    // Relaxed ordering is enough: fetch_add still hands every chunk index to exactly one
    // thread, and join() below makes each thread's writes to `partial` visible to us.
    const auto work = [&]() noexcept {
        for (std::uint64_t c = next_chunk.fetch_add(1, std::memory_order_relaxed); c < n_chunks;
             c = next_chunk.fetch_add(1, std::memory_order_relaxed)) {
            partial[c] = simulate(c);
        }
    };

    std::vector<std::thread> helpers;
    helpers.reserve(n_threads > 0 ? n_threads - 1 : 0);
    for (unsigned t = 1; t < n_threads; ++t) {
        try {
            helpers.emplace_back(work);
        } catch (const std::system_error&) {
            break;  // The OS refused another thread; the ones we have finish the work.
        }
    }
    work();  // The calling thread works too.
    for (auto& helper : helpers) {
        helper.join();
    }

    Stats total;
    for (const auto& stats : partial) {
        total.merge(stats);
    }
    return total;
}

}  // namespace mcpricer
