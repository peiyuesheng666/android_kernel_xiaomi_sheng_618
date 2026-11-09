#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Exercise the production PLL takeover helper against firmware register states."""
from pathlib import Path
import subprocess
import tempfile
from build_sheng618_upstream import K618

source = (K618 / 'soc/drivers/clk/qcom/dispcc-kalama.c').read_text()
start = source.index('static int sheng_dispcc_configure_pll(')
end = source.index('\nstatic int disp_cc_kalama_probe', start)
helper = source[start:end]
preamble = r'''
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#define BIT(n) (1U << (n))
#define PLL_OFF_OPMODE 7
#define dev_info(...) ((void)0)
struct device { int unused; };
struct clk_alpha_pll { unsigned int offset; unsigned int regs[8]; };
struct alpha_pll_config { int unused; };
struct regmap { unsigned int mode, opmode, user_ctl; int reads, calls, fail_read; };
static bool sheng_dispcc_live_splash;
static int regmap_read(struct regmap *m, unsigned int address, unsigned int *value) {
    m->reads++;
    if (m->reads == m->fail_read) return -5;
    assert(address == 0x1000 || address == 0x1004);
    *value = address == 0x1000 ? m->mode : m->opmode;
    return 0;
}
static void clk_lucid_ole_pll_configure(struct clk_alpha_pll *p, struct regmap *m,
                                      const struct alpha_pll_config *c) {
    (void)p; (void)c;
    m->calls++;
    m->user_ctl |= 7; /* The existing helper's unconditional output-mask write. */
}
'''
harness = r'''
int main(void) {
    struct device d = {0};
    struct alpha_pll_config c = {0};
    struct clk_alpha_pll p = {.offset = 0x1000, .regs = {[PLL_OFF_OPMODE] = 4}};
    struct regmap live = {.mode=0xe0000005, .opmode=1, .user_ctl=1};
    sheng_dispcc_live_splash = true;
    assert(sheng_dispcc_configure_pll(&d,&p,&live,&c) == 0);
    assert(live.calls == 0 && live.user_ctl == 1 && live.mode == 0xe0000005);
    for (int which = 0; which < 2; which++) {
        struct regmap inactive = {.mode=which ? 1 : 0, .opmode=which ? 0 : 1};
        assert(sheng_dispcc_configure_pll(&d,&p,&inactive,&c) == 0);
        assert(inactive.calls == 1 && inactive.user_ctl == 7);
    }
    for (int failure = 1; failure <= 2; failure++) {
        struct regmap broken = {.mode=5, .opmode=1, .user_ctl=1, .fail_read=failure};
        assert(sheng_dispcc_configure_pll(&d,&p,&broken,&c) == -5);
        assert(broken.calls == 0 && broken.user_ctl == 1);
    }
    sheng_dispcc_live_splash = false;
    live.reads = live.calls = 0;
    assert(sheng_dispcc_configure_pll(&d,&p,&live,&c) == 0);
    assert(live.calls == 1 && live.reads == 0 && live.user_ctl == 7);
    return 0;
}
'''
with tempfile.TemporaryDirectory(prefix='sheng-dispcc-live-') as directory:
    root = Path(directory)
    (root / 'live.c').write_text(preamble + helper + harness)
    subprocess.run(['gcc', '-std=c11', '-Wall', '-Wextra', '-Werror',
        '-Wno-unused-parameter', '-fsanitize=address,undefined',
        str(root / 'live.c'), '-o', str(root / 'live')], check=True)
    subprocess.run([root / 'live'], check=True)
print('Production helper passed: live output retention, inactive PLL, read failures, ordinary path')
