obj-m += frpc-adsprpc.o
frpc-adsprpc-objs += adsprpc.o adsprpc_rpmsg.o adsprpc_compat.o
ccflags-y += -I$(src) -I$(src)/include -I$(src)/include/uapi
# the soc tree's own headers (secure_buffer, the rproc_qcom tracepoints, ...)
ccflags-y += -I$(SOC)/include -I$(SOC)/include/uapi
# 5.15 vendor code under our stricter build: its %llu/%zu mismatches and one switch fall-through
# are warnings there and errors here, and say nothing about the port
ccflags-y += -Wno-format -Wno-implicit-fallthrough -Wno-missing-prototypes
# the driver's own header hides its exported calls behind this config
ccflags-y += -DCONFIG_MSM_ADSPRPC=1
