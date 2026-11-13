// Sobol low-discrepancy sequence with Joe–Kuo direction numbers, as 32-bit integers.
#pragma once

#include <algorithm>
#include <array>
#include <bit>
#include <cstdint>
#include <vector>

#include "mcpricer/sobol_directions.hpp"

namespace mcpricer {

inline constexpr int kSobolMaxDims = static_cast<int>(sobol_data::kDims);
inline constexpr unsigned kSobolBits = 32;

// v[k - 1] is direction number V_k of one dimension, scaled by 2^32.
using SobolDirections = std::array<std::uint32_t, kSobolBits>;

// Direction numbers of all kSobolMaxDims dimensions, built once (thread-safe static init).
// Joe & Kuo's recurrence: V_k = m_k / 2^k for k <= s, and for k > s
//   V_k = a_1 V_{k-1} ^ a_2 V_{k-2} ^ ... ^ a_{s-1} V_{k-s+1} ^ V_{k-s} ^ (V_{k-s} >> s),
// where a_i is bit (s - 1 - i) of the packed coefficient a.
inline const std::vector<SobolDirections>& sobol_directions() {
    static const std::vector<SobolDirections> table = [] {
        std::vector<SobolDirections> v(sobol_data::kDims);
        for (unsigned k = 1; k <= kSobolBits; ++k) {
            v[0][k - 1] = 1u << (kSobolBits - k);  // dimension 1: every m_k = 1
        }
        for (std::uint32_t d = 1; d < sobol_data::kDims; ++d) {
            const sobol_data::Primitive& p = sobol_data::kPrimitives[d - 1];
            SobolDirections& vd = v[d];
            const unsigned s = p.s;
            for (unsigned k = 1; k <= std::min(s, kSobolBits); ++k) {
                vd[k - 1] = sobol_data::kInitialM[p.m_offset + k - 1] << (kSobolBits - k);
            }
            for (unsigned k = s + 1; k <= kSobolBits; ++k) {
                std::uint32_t x = vd[k - s - 1] ^ (vd[k - s - 1] >> s);
                for (unsigned i = 1; i < s; ++i) {
                    if ((p.a >> (s - 1 - i)) & 1u) {
                        x ^= vd[k - i - 1];
                    }
                }
                vd[k - 1] = x;
            }
        }
        return v;
    }();
    return table;
}

// Point n of one dimension, in Gray-code order (the order Joe & Kuo's sobol.cc produces):
// the XOR of V_k over the set bits of gray(n) = n ^ (n >> 1). Needs n < 2^32.
inline std::uint32_t sobol_component(const SobolDirections& v, std::uint64_t n) noexcept {
    std::uint32_t x = 0;
    for (std::uint64_t g = n ^ (n >> 1), k = 0; g != 0; g >>= 1, ++k) {
        if (g & 1u) {
            x ^= v[k];
        }
    }
    return x;
}

// Going from point n to point n + 1 flips exactly one Gray-code bit: number countr_zero(n + 1).
inline unsigned sobol_next_bit(std::uint64_t n) noexcept {
    return static_cast<unsigned>(std::countr_zero(n + 1));
}

}  // namespace mcpricer
