// SPDX-License-Identifier: Apache-2.0

// The stock Cirrus backend reads the former public HAL logging bitmask.
// Current CAF AudioCommon.h keeps the same ERR/WARN/INFO/DBG default private
// to each translation unit. Expose that exact 32-bit default for the backend.
_Static_assert(sizeof(unsigned int) == 4, "Audio HAL log mask ABI requires 32 bits");
unsigned int ahal_log_lvl = 0x1u | 0x2u | 0x4u | 0x8u;
