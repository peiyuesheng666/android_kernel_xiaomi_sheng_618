// SPDX-License-Identifier: Apache-2.0
#include "classpath_exports.h"

#include <cerrno>
#include <cstdlib>
#include <cstdio>
#include <sys/wait.h>
#include <unistd.h>

#include <android-base/file.h>
#include <android-base/logging.h>

int main(int argc, char** argv) {
    android::base::InitLogging(argv, android::base::LogdLogger(android::base::SYSTEM));
    if (argc != 1) return EXIT_FAILURE;
    constexpr const char* generator = "/apex/com.android.sdkext/bin/derive_classpath";
    constexpr const char* output = "/data/system/environ/classpath";
    constexpr const char* temporary = "/data/system/environ/classpath.sheng.tmp";
    pid_t child = fork();
    if (child == -1) {
        PLOG(ERROR) << "Cannot start official classpath generator";
        return EXIT_FAILURE;
    }
    if (child == 0) {
        execl(generator, generator, static_cast<char*>(nullptr));
        _exit(EXIT_FAILURE);
    }
    int status = 0;
    pid_t waited;
    do { waited = waitpid(child, &status, 0); } while (waited == -1 && errno == EINTR);
    if (waited != child || !WIFEXITED(status) || WEXITSTATUS(status) != 0) {
        LOG(ERROR) << "Official classpath generator failed";
        return EXIT_FAILURE;
    }
    // On an adapter error leave the valid, just-generated platform file intact.
    // Compatibility may be unavailable, but the standard boot path remains usable.
    std::string generated;
    if (!android::base::ReadFileToString(output, &generated)) {
        PLOG(ERROR) << "Cannot read generated classpath";
        return EXIT_SUCCESS;
    }
    auto amended = sheng::AppendTabletClasspath(generated);
    if (!amended) {
        LOG(ERROR) << "Unexpected classpath exports; leaving platform output intact";
        return EXIT_SUCCESS;
    }
    if (!android::base::WriteStringToFile(*amended, temporary, 0644, getuid(), getgid(),
                                         /*follow_symlinks=*/false)) {
        PLOG(ERROR) << "Cannot stage tablet classpath";
        unlink(temporary);
        return EXIT_SUCCESS;
    }
    if (rename(temporary, output) != 0) {
        PLOG(ERROR) << "Cannot install tablet classpath";
        unlink(temporary);
        return EXIT_SUCCESS;
    }
    LOG(INFO) << "Appended tablet compatibility after all platform and APEX boot jars";
    return EXIT_SUCCESS;
}
