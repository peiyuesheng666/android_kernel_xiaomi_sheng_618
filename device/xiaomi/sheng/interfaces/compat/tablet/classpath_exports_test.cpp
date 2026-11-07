// SPDX-License-Identifier: Apache-2.0
#include "classpath_exports.h"
#include <gtest/gtest.h>

TEST(ShengClasspath, KeepsAllPlatformAndApexComponentsAsPrefix) {
    std::string input =
        "export BOOTCLASSPATH /apex/art/core.jar:/system/framework/framework.jar:/apex/wifi/wifi.jar\n"
        "export DEX2OATBOOTCLASSPATH /apex/art/core.jar:/system/framework/framework.jar\n"
        "export SYSTEMSERVERCLASSPATH /system/framework/services.jar\n"
        "export STANDALONE_SYSTEMSERVER_JARS /apex/bluetooth/service.jar\n";
    auto output = sheng::AppendTabletClasspath(input);
    ASSERT_TRUE(output.has_value());
    std::string expected(input);
    expected.insert(input.find('\n'), ":" + std::string(sheng::kTabletJar));
    EXPECT_EQ(expected, *output);
    EXPECT_FALSE(sheng::AppendTabletClasspath(*output).has_value());
}

TEST(ShengClasspath, RejectsAmbiguousOrMalformedExports) {
    for (const char* input : {"", "export BOOTCLASSPATH \n", "export BOOTCLASSPATH /a.jar",
                             "export BOOTCLASSPATH /a.jar:\n", "export BOOTCLASSPATH /a.jar::/b.jar\n",
                             "export BOOTCLASSPATH /a jar\n", "xexport BOOTCLASSPATH /a.jar\n",
                             "export BOOTCLASSPATH /a.jar\nexport BOOTCLASSPATH /b.jar\n"}) {
        EXPECT_FALSE(sheng::AppendTabletClasspath(input).has_value()) << input;
    }
}
