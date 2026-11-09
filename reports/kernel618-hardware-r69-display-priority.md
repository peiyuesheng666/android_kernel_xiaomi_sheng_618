# r69 显示先于 CPAS 接管对照（2026-11-10）

r68 首次欠载发生在 CPAS probe 区间，详见 r68 报告。本轮保持全部 344 个
驱动二进制，只调整内嵌批量模块顺序，让显示建立 Linux 资源投票后再加载
相机，检验能否保护固件画面的接管。

固定 piano、nuwa、MiCode、ACK 和相机来源以及实际差异见 r61–r64、r67、
r68 报告。原厂 vendor_dlkm 顺序也是 camera 在 msm_drm 之前；不把加载顺序
差异伪称为原厂根因。当前集成的资源投票和 CPAS 初始化路径与 5.15 有差异，
此候选只检验在当前 6.18 环境中先建立显示投票是否足以阻止欠载。

## 具体改动

`build_sheng618_layer_variant.py --tag hardware-r69 --base hardware-r68
--prioritize-before msm_drm.ko=camera.ko --smmu-scan-watch-ms 3000`。

按真实 modules.dep 计算依赖闭包，移到 camera 前的模块只有：
`msm_hfi_core.ko`、`msm_hw_fence.ko`、`sync_fence.ko`、`msm_drm.ko`。
所有必要依赖的先后关系检查通过；保留原有模块集合、各模块一次加载和
其余相对顺序。没有省略相机、USB、键盘、触控或其他硬件。

overlay 对照检查确认只变更 `lib/modules/k618_batch.load`；无驱动替换。
默认保持零等待，沿用最多 3000 ms 的只读欠载观察，不自动重启。

## 实机结果

2026-11-10 07:29:13（UTC+8）仅刷入 boot_a 并重启，USB ADB 返回，
Android `sys.boot_completed=1`。日志记录显示驱动于 2.292682 秒开始加载、
2.338893 秒加载完成；随后 camera 于 2.338918 秒开始、2.383927 秒完成。
4.163162 秒只读观察到期，全程未见两路欠载。

用户确认「已经消失了已经消失了」，白屏实机验收通过。此结论限于当前
6.18 集成的显示优先加载方案；尚未单独隔离 CPAS 带宽与电源接管的底层因素。
用户要求关闭测试日志和等待并交付 release。

- boot SHA256：`1e10900e2875641b5eff4fb439668bfc1365cb75ea622a1a2b0d9f290e760ea2`
- Image SHA256：`3f89ecfe1e131a0b1b2a92c1719461a446e99c29b8cab3f3681db355ecb772b7`
- 证据：`reports/device/kernel618-hardware-r69/kernel.txt`。
