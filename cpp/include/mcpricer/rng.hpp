// Random number generation with reproducible, per-chunk streams.
#pragma once

#include <array>
#include <bit>
#include <cstdint>

namespace mcpricer {

// Paths are simulated in fixed-size chunks. Each chunk has its own generator, seeded from
// (seed, chunk index) only, so a chunk's numbers never depend on which thread runs it.
inline constexpr std::uint64_t kPathsPerChunk = 16384;

// SplitMix64 (Steele, Lea, Flood 2014). We use it only to turn seeds into generator states.
class SplitMix64 {
public:
    explicit constexpr SplitMix64(std::uint64_t state) noexcept : state_(state) {}

    constexpr std::uint64_t next() noexcept {
        state_ += 0x9E3779B97F4A7C15ULL;
        return mix(state_);
    }

    // The SplitMix64 output function. It is a bijection on 64-bit integers.
    static constexpr std::uint64_t mix(std::uint64_t z) noexcept {
        z = (z ^ (z >> 30)) * 0xBF58476D1CE4E5B9ULL;
        z = (z ^ (z >> 27)) * 0x94D049BB133111EBULL;
        return z ^ (z >> 31);
    }

private:
    std::uint64_t state_;
};

// xoshiro256** (Blackman, Vigna 2018), seeded from SplitMix64 as its authors recommend.
class Xoshiro256StarStar {
public:
    explicit constexpr Xoshiro256StarStar(std::uint64_t seed) noexcept {
        SplitMix64 seeder(seed);
        for (auto& word : s_) {
            word = seeder.next();
        }
    }

    constexpr std::uint64_t next() noexcept {
        const std::uint64_t result = std::rotl(s_[1] * 5, 7) * 9;
        const std::uint64_t t = s_[1] << 17;
        s_[2] ^= s_[0];
        s_[3] ^= s_[1];
        s_[1] ^= s_[2];
        s_[0] ^= s_[3];
        s_[2] ^= t;
        s_[3] = std::rotl(s_[3], 45);
        return result;
    }

    // Uniform double in the open interval (0, 1): the top 53 bits plus half a step,
    // so the result is never exactly 0 or 1 (the inverse normal CDF needs that).
    constexpr double uniform_open() noexcept {
        return (static_cast<double>(next() >> 11) + 0.5) * 0x1.0p-53;
    }

private:
    std::array<std::uint64_t, 4> s_{};
};

// Generator for one chunk. For a fixed seed, chunk -> mix(seed) + chunk is injective and
// mix is a bijection, so different chunks always start from different seeds.
inline Xoshiro256StarStar chunk_generator(std::uint64_t seed, std::uint64_t chunk) noexcept {
    return Xoshiro256StarStar(SplitMix64::mix(SplitMix64::mix(seed) + chunk));
}

}  // namespace mcpricer
