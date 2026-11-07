// SPDX-License-Identifier: Apache-2.0
#pragma once

#include <optional>
#include <string>
#include <string_view>

namespace sheng {
inline constexpr std::string_view kTabletJar = "/system_ext/framework/sheng-tablet-compat.jar";

// Preserve the complete generated list as a prefix. Inserting into the platform
// fragment puts the jar before APEX components and invalidates existing images.
// DEX2OATBOOTCLASSPATH must retain the original boot-image input list.
inline std::optional<std::string> AppendTabletClasspath(const std::string& input) {
    constexpr std::string_view prefix = "export BOOTCLASSPATH ";
    size_t start = input.find(prefix);
    if (start == std::string::npos || (start != 0 && input[start - 1] != '\n') ||
        input.find(prefix, start + prefix.size()) != std::string::npos ||
        input.find(kTabletJar) != std::string::npos) {
        return std::nullopt;
    }
    start += prefix.size();
    size_t end = input.find('\n', start);
    if (end == std::string::npos || start == end || input[start] != '/' ||
        input[end - 1] == ':' || input.find_first_of(" \t\r", start) < end ||
        input.find("::", start) < end) {
        return std::nullopt;
    }
    std::string result(input);
    result.insert(end, ":" + std::string(kTabletJar));
    return result;
}
}  // namespace sheng
