# SPDX-License-Identifier: GPL-2.0-only
# Qualcomm WALT provider for sheng ACK 6.18; vendor extensions are disabled.
obj-m += sched-walt.o
sched-walt-y := walt.o boost.o sched_avg.o walt_halt.o core_ctl.o trace.o input-boost.o sysctl.o cpufreq_walt.o fixup.o walt_lb.o walt_rt.o walt_cfs.o walt_tp.o walt_config.o voter.o walt_cpufreq_cycle_cntr_driver.o walt_gclk_cycle_counter_driver.o walt_cycles.o debugfs.o pipeline.o smart_freq.o walt_storage_lb.o mvp_locking.o
ccflags-y += -I$(srctree) -I$(src) -I$(src)/../../../include -I$(src)/../../../include/uapi
ccflags-y += -DCONFIG_SCHED_WALT_MODULE=1 -DCONFIG_QCOM_SOCINFO_MODULE=1 -DCONFIG_ARM_QCOM_CPUFREQ_HW_MODULE=1
KBUILD_EXTRA_SYMBOLS += $(src)/../../../Module.symvers
