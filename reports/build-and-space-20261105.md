# 2026-11-05 构建事件与空间精简

最新检查点，优先于旧同步等待记录。

- LineageOS24.0完整repo sync已成功，源清单logs/source-manifest.xml已生成。源码不再处于下载阶段。
- 第一轮真实m bacon已运行，Soong bootstrap完成；Android.bp分析因两个重复预编译库的system/vendor分区冲突退出。不是ROM编译成功，无可交付ROM。
- android.hardware.sensors@2.0-ScopedWakelock和libhidltransport均有当前平台vendor_available源码实现。已移除提取清单中对应32/64位共4项重复blob，重新生成并安装vendor，局部预检通过。现在2071项blob、17个原厂板级模块。此修复尚待下一轮真实构建确认。

## 结束事件

- build_lineage.sh持有build.lock后exec build_events.py监督build_lineage_worker.sh；监督器阻塞等待子进程，不读取编译日志。
- logs/build-event.json按run_id原子记录running/finished、退出码、信号、阶段及日志路径。成功事件只有worker全部成功（包括产物验证/导出）之后产生。
- build_events.py probe只查事件和Linux进程身份（含boot_id及start_ticks防PID复用）。WSL关闭或两进程被杀时，下次探测记interrupted，不冒充成功。
- 同步后的首次失败已被该机制捕获，run_id=06bae83205874475ab12ea4120b075e8，returncode=1。
- 既有sheng-lineageos自动化仍每10分钟唤醒：正常构建仅probe后安静等待；未处理的结束/中断事件才读日志，失败继续修复，成功核验交付。不是WSL即时推送；当前工具不支持本地进程直接唤醒聊天。
- 构建另外设C盘20GiB剩余空间底线，每30秒仅查磁盘空间，不读编译日志；不足则终止本轮并记录失败原因，防止写满Windows系统盘。24线程、80GiB swap、10GiB ccache仍按用户选择。

## 空间

- 用户要求精简源码。scripts/slim_prebuilt_history.py仅处理4个任务自有、对象库不共享且所有ref指向当前提交的预编译仓库，显式浅克隆、回收无用历史、验证Git连接完整性与工作区未变，未删除当前源码文件。
- prebuilts/sdk：20.07 -> 1.24GiB；module_sdk/art：16.04 -> 0.79GiB；remoteexecution-client：10.71 -> 0.56GiB；misc：5.98 -> 1.91GiB。
- 本轮回收51870199808字节（约48.3GiB）WSL逻辑占用，完整明细logs/source-cache-slimming.json。另有此前56.25GiB废弃临时下载已清理，两者不能重复计算成Windows实际可用增加。
- Windows C盘本轮压缩前约140GiB可用，ext4.vhdx长度334106722304字节，未设sparse。已sync与fstrim，然后在无构建运行时停止Ubuntu-22.04，执行官方wsl --manage Ubuntu-22.04 --compact。压缩完成后的实际C盘空间需重新读取。
- logs/source-maintenance.pending暂时阻止自动化/构建与Git维护并发。压缩后运行scripts/test_build_events.py，核对空间，再scripts/resume_after_source_maintenance.py解除标记并恢复构建，不要遗留维护标记。
- 不要重复运行reclaim_interrupted_packfiles.py（它只针对已删除的4个具体临时文件）。不要因旧说明重新启动repo sync或一次性设备树/24.0迁移。

## 已完成压缩并恢复构建

- wsl --manage Ubuntu-22.04 --compact返回0。VHDX长度从334106722304降至245573353472字节，Windows C盘重新实测226.33GiB可用。
- test_build_events.py共3个测试方法通过，覆盖成功、退出7、worker SIGKILL、监督器和worker均消失、强制触发磁盘空间底线。它们在隔离临时目录测试，没有伪造真实ROM成功事件。
- resume_after_source_maintenance.py已记录上轮失败的处理ack，移除source-maintenance.pending并恢复build_lineage.sh；当前unified exec session8646。后续只probe结束事件，运行中不读构建日志。
- 本轮精简的完整JSON已复制到Windows reports/source-cache-slimming.json。226GiB是实际C盘空间，不是WSL虚拟df最大容量；是否足够最终整包仍取决于真实输出和swap使用，构建保留20GiB底线。

## 07:05继续与最新检查频率

- 第二轮在06:49因libmemunreachable、libcodec2_soft_common、libstagefright_bufferpool@2.0.1重复预编译库分区冲突退出。已移除清单中的这3项，改由当前vendor_available平台源码提供；prepare_dolby.py也排除这些平台依赖，避免下次重新加入。重新生成vendor后现为2068项blob、44项Dolby输入。
- scripts/retry_lineage_build.sh已于约07:05启动第三轮，run_id=3cd2d28b778645f0b873edfc0a4a7c18，已实际确认running/configuring；unified exec session74963。
- 用户最新要求每30分钟检查一次。既有sheng-lineageos自动化已从10分钟改为30分钟，保持当前聊天，未新建重复任务。运行中只probe事件/进程，不读编译日志；退出后才读取错误并修复或交付。旧文档中的10分钟均被本条取代。

## 07:09日志查看与下一轮

- 用户再次询问状态时，第三轮已经在07:06:25退出；实际错误为libqti_vndfwk_detect与libhwbinder的源/预编译分区冲突。两者已核实当前源码vendor_available=true，移除清单中32/64位4项重复blob，prepare_dolby.py同步排除平台qti依赖，重新提取后2064项blob、44项Dolby输入。
- scripts/retry_lineage_build.sh已直接启动下一轮，unified exec session57562。未等待定时任务。
- 用户可以在PowerShell执行：wsl -d Ubuntu-22.04 -- tail -n 100 -F /root/sheng-lineage/logs/build-lineage.log。Ctrl+C仅退出查看日志，不会中止另一个进程中的构建。

## 连续接管中的检查点（约07:24，尚未达到5分钟）

- 用户最新要求先连续接管并即时处理失败，直到同一轮构建至少5分钟未报错，之后每20分钟检查。自动化已改20分钟，logs/watch-five-minutes.pending尚未解除；满足前不能结束观察。
- 自07:10起连续修复并重试：将sfplugin_ccodec_utils/libdrm及AIDL display.config-V2绑定交由平台对应源码提供；逐个核验68个标准/厂商同版本HIDL接口源码后移除重复绑定（不是移除HAL驱动实现，详reports/source-hidl-interfaces.json）。有明确重命名兼容fixup的7个绑定未按此通用规则移除。
- 从原厂缓存补齐libgps.utils、libdsutils及libdsi_netctrl/qdi/netmgr/configdb/netmgrxfrmutils/rcsconfig1.0/1.1真实依赖。complete_stock_library_deps.py检查ARM/ARM64 DT_NEEDED，区分DSP固件与Android原生库，未禁用ELF或ABI检查。报告stock-library-dependency-closure.json。
- 旧sdm845/sm7250/sm8150 BSP在Android17全局Soong分析中引用已移除的Google light1.0；device.mk用PRODUCT_SOURCE_ROOT_DIRS排除这三个不属于sheng的旧平台，保留CAF SM8550与实际所需wlan。未删工作区源码。
- AIDL V3/V7冲突来自原厂旧libgui_vendor。当前frameworks/native/libs/gui/Android.bp自带vendor:true的libgui_vendor，故移除旧32/64位blob并使用当前源码实现，没有强行改AIDL版本或关闭一致性检查。
- 目前1999项blob、43项Dolby输入、17板级模块。最新实际run_id=a36021f4ff714c02bc9e44bd8e6919a1，约07:22:54开始，session73344，07:23:50仍running；soong_build约986%CPU、90%RAM，进入更深入的构建图分析，尚未宣称已通过或产出固件。持续观察起点以本轮build-phase.txt进入building的mtime为准。

## 连续监视、后续错误与最新定时（约07:43）

- 此前libgui_vendor替换后，构建推进到com.xiaomi.immunesystem的sqlite3共享库重名问题。已在extract-files.py将依赖模块名映射到sqlite3-sheng，清单对两个odm/lib*/sqlite3.so设置MODULE=sqlite3-sheng。生成的Soong模块确认为name sqlite3-sheng、stem sqlite3，64位文件SHA256与原厂完全一致。
- run_id=3965185c2dc349dab9cb5edf8060e2c7于07:32:14实际达到building连续308.3秒未失败（reports/build-stability.json），但仍在Soong构建图分析，有换页压力提示，不是整包成功。此轮随后在07:36:30退出：protobuf3.9.1原厂blob与hardware/lineage/compat的vendorcompat同名安装文件重复。
- 已移除原厂protobuf full/lite 3.9.1的32/64位4项，使用现有LOS同版本vendorcompat源码实现；prepare_dolby.py平台依赖集合与closure脚本的compat stem识别同步更新，防止重新加入。当前1995项blob、43项Dolby输入、17板级模块。
- 新一轮run_id=f26a3ef43edc43f19657c4f2103ad274约07:40:27启动，已实际确认running。上次functions.exec被中断，但修改、自动化更新与构建启动均已完成，不要重复启动。
- 用户最终要求不等20分钟，让脚本持续监视，并现在继续修复编译。scripts/wait_build_exit.py用Linux pidfd+poll阻塞等实际进程退出，不读日志也不按20分钟轮询；当前waiter unified exec session98969，构建父命令的session因中断未知，但PID/事件记录完整。本聊天仍连续接管，waiter结束就读取错误并修复。
- 每20分钟自动化已取消，ID仍sheng-lineageos。实际本次额度重置为北京时间2026-11-05 11:24:24，按最新要求设置重置后5分钟，即11:29:24单次唤醒（COUNT=1）。不是每天，不是每20分钟；本自动化仅额度重置后的续作兜底，不代替当前持续接管。若再限额，查询下一次真实重置时间并同样安排重置后5分钟单次。
- 尚无ROM产物，不能交付ACK基线冒充或声称实机启动。当前保留源模块ABI/ELF/VINTF/SELinux及20GiB C盘底线检查。

## 08:02继续：Soong通过，进入Make配置修复

- f26a3ef43edc43f19657c4f2103ad274本轮Soong图生成实际成功（18m29s，日志Build Succeeded），Ninja分片持续增长，说明高换页时仍有进展。未编译完整ROM。
- WSL在Soong约50GiB虚拟内存/20GiB物理限制下曾出现新exec连接WSAETIMEDOUT，Windows UNC文件通道仍可读取/proc/PID/stat，CPU与major-fault计数持续变化；构建未被强制重启。Soong退出释放内存后，wsl --exec /bin/true立即恢复。zswap内核模块不存在，未做任何zswap/GC/平台源码改动。
- 随后Kati在07:59:55因3个PRODUCT_PACKAGES不存在退出：consumerir.qcom、libvsim、vendor.xiaomi.hardware.vsimapp@1.0。它们只有原厂32位blob且并非此Wi-Fi平板的红外/虚拟SIM能力，已从清单移除3项，当前1992项blob、43项Dolby输入、17板级模块。正在重新提取并重启下一轮。
- 用户要求脚本持续监视、不等20分钟；当前处理仍连续接管，wait_build_exit.py阻塞在pidfd/poll，不读编译日志，结束就返回。已完成的waiter98969正常返回本轮exit1，需对新一轮重新启动该脚本等待。
- 定时最新为本次真实重置11:24:24后5分钟，即2026-11-05 11:29:24单次（COUNT=1）；当前继续工作。不能恢复20分钟循环或每天定时。

## 08:28继续：安装路径碰撞审计

- 1608c9279ce44119bae7879da13d64db本轮Soong图生成成功（19m37s），Make模块与包装规则推进至writing make module actions；08:23:18因odm/etc/NOTICE.xml.gz与自动生成通知文件重复退出。
- 原厂通知文件仅重命名安装目标为odm/etc/NOTICE.stock.xml.gz，原厂内容保留。新增audit_install_collisions.py对resolved PRODUCT_COPY_FILES与已有Soong安装目标做交叉检查，一次发现同类14项冲突：原厂odm fs_config_dirs/files、passwd/group、预编译SELinux与hash/context文件。它们应由当前ROM配置生成，故已从blob清单移除；C盘原厂缓存不变，不把旧MIUI编译策略带入新ROM。
- 重新提取后1978项blob、43项Dolby输入、17板级模块；1501条resolved文件复制规则对比88611个已有安装目标，collisions=[]。retry_lineage_build.sh现于重试前强制此检查；这仍是旧Soong快照的局部检查，不取代真实Kati/SELinux。
- 新一轮通过session27506启动，新的wait_build_exit.py已重新接上（session以本聊天最新工具输出为准），不重复启动旧waiter68572。

## 09:07：已进入实际编译并持续监视

- 当前run_id=e74075a0d6a84009b873a928ebfacbbd，08:27:58启动，父命令session27506；退出等待脚本session44141仍阻塞监视该轮，不是20分钟轮询。
- Soong约08:47通过，Make配置/包装规则随后通过，已进入真实C/C++/Rust/Java资源编译。09:06:47约34148/188444个动态构建动作（计数会调整，不能据此精确预估时间），尚无退出失败事件。
- ccache已实测工作：CCACHE_DIR=/root/sheng-lineage/ccache，10GiB上限；首轮约1512次未命中是正常冷缓存。不要误读默认/root/.cache/ccache的5GiB统计。
- C盘09:06约128.85GiB可用，20GiB底线保护仍启用。仍未完成ROM，不能把构建图或动作进度当成产物。17个原厂板级模块的实际新内核ABI检查亦必须通过后才导出。
- 定时保持11:29:24单次，按最新要求是实际额度重置后5分钟，仅作额度重置续作兜底；当前仍连续接管。后续事件失败立即读真实日志修复并重试，成功才导出交付。

## 16:40：修复PAL编译并纠正自动化时区

- 上一轮e74075a0d6a84009b873a928ebfacbbd于10:21退出，约106885个动作完成；PAL StreamUltraSound.cpp经PayloadBuilder.h找不到gsl_intf.h。原厂libar-gsl预编译库覆盖源码库后没有传递GSL导出头文件目录。只向PAL Android.bp补入GSL api/dls_client_api/hw_rsc_api/rtc_api四个目录，继续使用原厂库，不伪造头文件、不关闭检查。
- scripts/fix_pal_gsl_headers.py已从真实失败命令重编该文件并通过，报告reports/pal-gsl-header-fix.json。补丁patches/pal-gsl-includes.patch；该一次性复现脚本依赖旧失败日志，现在不要重跑。export_lineage.py新增将本地patch及SHA256纳入交付记录，避免只提供manifest遗漏修改。
- 当前run_id=772c319adfd64008855cfc62cde64ff8，16:27:46开始，父命令session77118，supervisorPID1303578、worker1303583。16:37仍在Soong重新生成图；C盘16:15约102.27GiB可用。WSL新exec因换页再次WSAETIMEDOUT，原父命令与UNC通道正常，不要误杀构建。新wait_build_exit.py session98630因WSL连接超时退出，未接上；可直接等待仍活跃的父命令77118，待WSL恢复再接原生退出等待脚本。
- 定时原因已查明并纠正此前“漏跑”的判断：本地只读调度数据库显示旧next_run_at=1793878164000，是北京时间19:29:24，并非原以为的11:29:24。带Asia/Shanghai的开始时间被调度器按UTC计算，导致晚8小时；last_run_at=null、runs=[]是尚未到真正排定时间，不能据此认定调度失效或应用关闭。
- 重新读取真实额度：本轮重置21:15:28，按用户要求重置后5分钟单次，即北京时间2026-11-05 21:20:28。用明确UTC DTSTART更新同一sheng-lineageos自动化后，再核对数据库next_run_at=1793884828000，已与北京时间21:20:28一致。不是每天、不是20分钟，不直接修改应用数据库。此前带TZID的时间配置不要复用。
- 当前继续编译，尚无完整ROM；维持24线程/80GiB swap/10GiB ccache及所有空间、模块ABI和平台一致性检查，不自动刷机。
- 16:42 WSL exec恢复，scripts/export_lineage.py已用Python ast.parse检查通过。已接上原生pidfd退出等待session28193，监视当前run_id772c319adfd64008855cfc62cde64ff8；父命令仍为77118。soong_build PID1304793，运行14分钟时CPU累计29分钟、RSS约18.4GiB/VSZ45.2GiB，构建未退出。

## 17:04：按用户新要求，先集中验证再打整包

- 772c319adfd64008855cfc62cde64ff8于16:58:12失败。新增完成11827个动作、约67757剩余；SELinux在hal_sheng_dolby.te展开typeattribute时找不到vendorcodec。实际vendorcodec.te定义存在，但排在宏调用之后，已把该hal_client_domain调用移到vendorcodec.te定义之后；workspace与实际WSL设备树已同步两文件。
- 用户要求先集中检查、减少一错一编。当前停止直接bacon重试，创建logs/device-audit.pending门禁；先用scripts/validate_lineage.sh验证，所有检查通过才恢复整包构建。该脚本沿用同一build.lock、20GiB磁盘保护和build_events退出事件，不能和整包同时运行。
- 新验证run_id=57edd580baaa456b9a9ccccfd8223b78，17:03:00启动，父命令session30971，原生pidfd等待session44277。phase=validating，与编译成功/ROM产物不同。
- 静态preflight、Dolby资源/配置、安装路径碰撞已再次运行通过；最新C盘80.68GiB。vendor/xiaomi/sheng/Android.bp未发现check_elf_files:false或allow_undefined_symbols:true，不以关闭ELF检查来掩盖问题。
- 本轮用支持的-k0继续独立目标检查，集中请求selinux_policy、check-vintf-all、check-elf-files、kernel、ShengDolby、FrameworkResOverlaySheng/SystemUIResOverlaySheng/SettingsResOverlaySheng/LineageResOverlaySheng/WifiResOverlaySheng，不请求bacon/droid/OTA。部分检查要真实编译对应模块/内核，不能伪称全是静态分析。scripts/summarize_validation.py在退出时生成reports/lineage-validation.json，汇总所有FAILED目标和诊断。
- 原始失败日志已保存在/root/sheng-lineage/logs/failures/772c319adfd64008855cfc62cde64ff8.log。当前主build-lineage.log改为本轮验证日志。验证成功仅标记status=validated、phase=prebuild-validation-passed，不导出ROM、不自动宣称成功；检查通过后移除门禁再继续完整构建。
- 21:20:28单次额度重置续作的prompt已加入本次集中预检要求，不能在门禁期间直接重试bacon。时间仍为已核对UTC epoch的北京时间21:20:28，非每天/20分钟。
- 17:20集中检查已提前捕获3个FAILED目标：vendor_sepolicy.unversioned.cil、sepolicy_neverallows（同一未知类型根因）、内核Image（导出的Cirrus CS35L41头文件含kernel-private结构，用户态C90头文件检查报bool/work_struct/mutex/atomic_t等不完整类型）。此时检查仍继续执行其他独立目标，未打完整ROM。
- scripts/audit_policy_types.py补充扫描展开策略的常用规则，发现两个确切未定义引用vendor_sysfs_usb_c、uinput_device；它不是完整SELinux语法校验，不能替代checkpolicy。电池原厂二进制确认访问/sys/class/typec/port0/data_role，当前AOSP/QTI用sysfs_typec，sheng数据节点另已有vendor_sysfs_usb_supply精确标签和读写权限；workspace batterysecret.te改为r_dir_file(batterysecret,sysfs_typec)。AOSP实际/dev/uinput标签为uhid_device，workspace指纹规则已修正。两文件尚未复制到live，待本轮结束统一部署重验。
- scripts/audit_platform_blob_duplicates.py再次非修改扫描，candidates=[]。
- 新增validation_inputs.py/require_validated.py：分项成功后记录live设备/板级模块/生成vendor配置/PAL输入SHA及3个内核repo HEAD和tracked diff SHA，整包worker强制匹配成功记录。未通过验证或输入已改动时拒绝直接bacon。语法检查通过，不能把这项门禁本身当作native验证成功。

## 17:24：第二轮集中验证与预检门禁

- 第一轮集中验证57edd580baaa456b9a9ccccfd8223b78于17:22:12结束，19m01s，完整失败列表为3个目标：vendor_sepolicy.unversioned.cil、sepolicy_neverallows、kernel Image。检查没有在第一个错误停下；报告reports/lineage-validation.json和原始失败日志/logs/failures/57edd580baaa456b9a9ccccfd8223b78.log已保存。VINTF/策略等依赖失败的后续检查不能算通过。
- 电池与指纹两个SELinux类型修复已同步至live。scripts/fix_audio_private_uapi.py已将音频模块cs35l41.h中的纯内核平台数据/驱动结构置于__KERNEL__保护；不更改内部结构布局、不关闭headers检查。实际内核预处理结果与git HEAD原声明一致；通过真实headers_install.sh导出以及clang C90双重include测试。报告reports/audio-private-uapi-fix.json，补丁patches/cs35l41-kernel-private-uapi.patch。第一次单测因headers_install.sh需要在KERNEL_OBJ中运行而失败，已纠正cwd并实际重验通过；修复脚本基于git HEAD比较并可重复运行。
- 第二轮run_id=1b130450f2e34a44bc08efb17c9ec094，17:22:59开始，父命令session74706，退出等待session4133。保留audit.pending，不直接bacon。验证worker已加入实际device.mk中关键音频/显示/指纹/健康/传感器/电源/USB/Wi-Fi/触控/启动等HAL及fastbootd目标，继续-k0集中收集独立错误。
- 第一轮已真实编出/root/sheng-lineage/lineage-24.0/out/target/product/sheng/system_ext/priv-app/ShengDolby/ShengDolby.apk（20703字节，17:20），不再只是资源预检。此为单独应用编译产物，不是ROM，也不能证明实机Dolby生效。
- 新整包门禁require_validated.py已接入build_lineage_worker.sh：必须存在validation_passed=true且当前设备/BSP指纹匹配的receipt才能整包构建。成功分项报告的输入指纹由summarize_validation.py生成；不能把phase=prebuild-validation-passed当作ROM完成。

## 17:37：第二轮结果与统一GSL头文件导出

- 第二轮1b130450f2e34a44bc08efb17c9ec094于17:26:58结束，约3m48s。35个目标中剩余失败为AGM wrapper缺gsl_intf.h、kernel Image的msm_sde_rotator.h间接包含videodev2.h时缺POSIX struct timespec。SELinux完整策略及其测试实际通过，展开策略未知类型扫描unknown_references=[]；原始日志与报告已存/logs/failures/1b130450f2e34a44bc08efb17c9ec094*。
- 不再逐个修GSL调用方。scripts/export_gsl_headers.py在源GSL项目增加libsheng_gsl_headers，向原厂libar-gsl预编译模块添加header_libs和export_header_lib_headers，统一传播原有4个源码API目录。原厂共享库内容不变。PAL临时include路径补丁已撤销、PAL Android.bp恢复git HEAD，旧patch与一次性fix_pal_gsl_headers.py已删除，历史报告仅作历史。有效补丁现在patches/gsl-prebuilt-header-provider.patch及patches/cs35l41-kernel-private-uapi.patch；导出器自动携带所有有效patch。extract_sheng_vendor.sh已接入GSL导出修复，重新提取时不会丢失。validation_inputs.py也纳入GSL Android.bp的SHA。
- scripts/check_vendor_uapi.py复现原timespec错误，并用真实clang --target=aarch64-linux-gnu/C90双include及真实headers_check.pl批量检查当前17个外部模块导出头文件；加入-D_POSIX_C_SOURCE=200809L后全部通过，没有关闭任何头文件测试或改变UAPI布局。已在workspace和live BoardConfig.mk配置受当前LOS BoardConfigKernel.mk支持的TARGET_KERNEL_ADDITIONAL_FLAGS += USERCFLAGS=-D_POSIX_C_SOURCE=200809L。报告reports/vendor-uapi-check.json。
- 第三轮集中验证run_id=cb9ba170ce424df38fa092f27a603078，17:35:28开始，父命令session81840，原生退出等待session60871，supervisor1682663、worker1682668。修改Android.bp后Soong会重新生成图（此前约18分钟），不误杀、不重复启动。当前仍为35个分项目标，非bacon；device-audit.pending仍在，全部通过且receipt匹配后才恢复整包。
- 17:36 C盘约71.15GiB可用，80GiB swap/24线程/10GiB ccache/20GiB空间保护不变。当前仍无ROM。
- 17:39新增verify_agm_gsl_compile.py从第二轮真实失败命令复现AGM wrapper编译，补入GSL header provider所导出的同样4个目录后，实际clang编译返回0。报告reports/agm-gsl-compile.json，完整诊断logs/verify-agm-gsl.log。这证明该源文件可编译，Soong对新header provider的自动传播仍需当前第三轮验证，不能单独冒充整轮通过。

## 18:05：内核链接与Windows侧持续衔接

- 第三轮Soong图于17:53:42重新生成成功，统一GSL头文件导出已通过实际构建，audio.primary.kalama.so于17:56编出。此时约124/132个外层动作，但内核是一个内部很长的动作，不能把该百分比当作ROM进度。
- 17:57起内核在链接。18:03通过UNC读取/proc中kernel make子树，ld.lld PID1769506，RSS15765948KiB、VmSwap15296956KiB，处于D/disk sleep换页等待；整体build-event仍running。C盘17:56约65.61GiB。
- 新增continue_after_validation.py：仅等待指定run_id通过、phase=prebuild-validation-passed且require_validated.py指纹匹配后，移除audit.pending并exec resume_after_source_maintenance.py。绝不在验证失败时开始整包。
- Linux直接启动该controller的session19822因WSL/Service/WSAETIMEDOUT退出，未实际启动（没有validation-continuation.json），不能按其存在判断已衔接。当前ld.lld占用内存/换页期间WSL新exec可能超时，原生waiter60871仍接在老进程上。
- 已实际启动Windows侧scripts/watch_validation_windows.ps1 -RunId cb9ba170ce424df38fa092f27a603078，session75615、WindowsPID17740，reports/validation-continuation-windows.json已确认action=waiting-for-validation。此脚本每2秒只读原子build-event，不读日志，不消耗模型额度。只有该指定验证成功才调用Linux controller并衔接完整构建；失败只标记needs-repair，不绕过门禁。Linux执行连接会在验证结束释放内存后再启动。
- 后续处理：先查Windows continuation记录及对应PID是否活着，防止与其重复手动启动整包。wait_build_exit.py可能在验证退出时返回，也可能跟到紧接的新full run；检查实际全局event/phase，不只看旧session。若本轮验证失败，Windows watcher会退出，修复后新run需要重新启动对应watcher。若检查通过，它会自动开始整包，不需等待下一额度重置。
- 18:16:54已生成KERNEL_OBJ/vmlinux.o（1134516256字节），大内存Full LTO进程1769506结束；18:18 MemAvailable恢复约13.2GiB。18:19原生WSL exec恢复，仍无FAILED目标，已进入后续make动作。实际主机物理内存31.73GiB，18:07可用约1.48GiB，因此没有盲目提高WSL20GiB上限；所有原有swap/线程参数保持。新依赖项目graphservices与sm8550-modules中未发现AGENTS.md。
- 21:20:28单次续作prompt已补充Windows watcher实际有效入口和防止重复衔接要求；原生controller失败与Windows watcher生效已区分清楚。

## 19:00：完整BSP依赖审计与第四轮集中验证

- 第三轮cb9ba170ce424df38fa092f27a603078于18:22:53退出。内核主体及原计划源码BSP均实际编出，只有最终17个原厂模块的ABI安装检查失败，30项错误（包括panel notifier CRC和Mi调度/触控/键盘/充电接口缺失）。完整日志及报告已存logs/failures/cb9ba170ce424df38fa092f27a603078*。Windows watcher正确保持门禁并退出为needs-repair，没有开始整包。
- 对640份原厂缓存模块（去重419个名字）全部导出/导入进行审计，已编出内核的15524个内建导出对原厂完整模块链无CRC冲突、无缺失，重复文件SHA一致。最初17根模块的依赖闭包实际为67个；继续混用通用phone BSP的398个源码模块时还产生其他硬件变体冲突，不能只给17个模块补空接口或改CRC。
- 首版方案保留官方LineageOS 5.15.220内核主体；417个vendor BSP模块直接使用本机原厂固件，zsmalloc/zram两个GKI模块使用当前源码编译。audit_stock_module_closure.py --all-stock与audit_mixed_module_abi.py --stock-all --source-keep zram.ko zsmalloc.ko已证实实际419个模块的核心/模块间符号、CRC及重复导出检查均为0错误，报告reports/stock-all-module-abi.json、stock-bsp-module-abi.json。不改模块vermagic、CRC或关闭检查。
- 新module-plan.json固定417个原厂模块SHA、两个source_keep及按实际ELF依赖计算的BOOT/RECOVERY集合；prepare_stock_bsp.py已生成并同步配置。实际stock加载清单是first_stage116、vendor304、recovery335；完整闭包BOOT116、RECOVERY336。BOOT与RECOVERY现分开配置，移除了之前通用phone加载表中的不适用引用；SYSTEM_KERNEL_MODULES明确为source zsmalloc/zram。TARGET_KERNEL_EXT_MODULES只执行本设备的严格staging，模块源码repo仍提供内核所需UAPI头文件并保留供后续驱动工作参考。kernel core的Kconfig未改变，现有LTO结果可复用。
- stage.py新增stock-vendor-bsp-source-gki模式：只核对vmlinux内建导出和实际将发往设备的全部419个模块，验证SHA、vermagic标志、导入CRC和重复导出后，才整理生成的分发暂存目录，保留两个源码GKI模块并放入417个原厂BSP；不修改内核源码/原始build outputs/固件输入。旧17模块模式仅保留兼容旧守卫测试。
- verify_stock_bsp_guard.py在隔离目录用真实419个模块测试：正常打包通过，重复执行内容不变；故意篡改临时内核module_layout CRC时正确拒绝，待打包内容未变化。报告reports/stock-bsp-guard-tests.json。完整静态preflight也已再次通过，preparation report当前417 board modules/1978 blobs/43 Dolby inputs。
- 第四轮集中验证run_id=2eab49e4775d44709ddecc0de4543a17，18:57:52启动，父命令session76263，原生退出等待session37556；phase=validating，audit.pending仍在。新的有效Windows watcher：session8911、WindowsPID27296，reports/validation-continuation-windows.json已确认等待该run。旧session75615/PID17740已因第三轮失败退出，不复用。
- 验证全过后该Windows watcher会调用continue_after_validation.py核对成功receipt，自动移除门禁并接整包；不要重复手动启动。若失败修复后新run需重接watcher。直到完整ROM构建及导出成功才交付，不把BSP隔离测试或ShengDolby APK当成ROM。
- export_lineage.py除平台manifest和本地patch，还将打包device/sheng、manifests、patches及构建脚本为sheng-build-configuration.tar.gz并记录SHA，补足未进入平台manifest的自写设备配置记录。当前有效源补丁仍为GSL头文件provider与CS35L41 kernel-private UAPI两项。
- 19:09用户临时要求再清理空间；仅发起只读df/du和C盘占用查询，没有删除任何文件。19:10用户取消清理，表示已自己清理，现只继续原验证/构建任务。C盘19:10读到92.92GiB可用。再次按精确命令行检查时已无该只读du查询的wsl.exe relay，实际终止0个进程，未终止WSL发行版/构建；不要自行继续清理。
- 19:10第四轮2eab49e4775d44709ddecc0de4543a17仍running/validating，在Soong构建图分析，尚未整包。watcher8911/PID27296仍是当前有效自动衔接入口，native waiter37556继续使用；functions.exec等待循环554已因用户插入取消，仅取消编排等待，不代表终止构建。

## 19:20：35项分项验证全部通过，已自动开始完整ROM

- 第四轮2eab49e4775d44709ddecc0de4543a17于19:18:53.514成功结束（returncode0，phase=prebuild-validation-passed）。reports/lineage-validation.json记录validation_passed=true、35目标、failed_targets=[]及当前输入指纹。真实419模块安装守卫通过（417原厂BSP+2当前源码GKI），完整SELinux/VINTF/ELF/关键HAL/Dolby/覆盖配置分项目标均通过。
- Windows watcher8911/PID27296已实际自动调用Linux controller核对成功receipt并移除门禁。19:18:55新整包run_id=78190bfcf26e4bb2895372b8e9ecd43a开始，supervisor1923986、worker1924045；全局status=building，不要重复启动。该full build父入口仍是Windows session8911，其native controller PID1923986已exec成新的build supervisor；旧验证session76263/原生等待37556已经成功结束。
- 当前实际整包的原生退出等待session55700，监视run78190bfcf26e4bb2895372b8e9ecd43a，失败就修复，成功必须等导出结束。尚未产出ROM。
- 成功验证的receipt、419模块ABI报告、原验证session日志及3个VINTF日志已保存logs/validation-evidence/2eab49e4775d44709ddecc0de4543a17/。自动衔接比人工拷贝快：人工原想拷成功日志时主log已被full Make配置覆盖，该文件现正确命名logs/build-start-78190bfcf26e4bb2895372b8e9ecd43a.log，不冒充验证日志。continue_after_validation.py已改为未来衔接前先自动存验证原日志/receipt/ABI，当前成功事实由原生退出事件、receipt和独立验证证据支撑。
- 19:10用户已自行清理C盘，约92.92GiB可用；本次临时空间清理已取消，我方没有删除任何用户文件。不要重新发起无用缓存清理；仅继续构建必要的暂存选择/打包。

## 20:10：WebView LFS实体修复并继续完整构建

- 完整run78190bfcf26e4bb2895372b8e9ecd43a于19:58:03失败（约39分钟）。当时已新增完成约32000动作、动态剩余约20000；唯一失败是外部预置WebView的enforce_uses_libraries检查，aapt2无法把webview.apk当ZIP打开。原始日志已归档logs/failures/78190bfcf26e4bb2895372b8e9ecd43a.log。
- 根因不是源码编译错误：external/chromium-webview/prebuilt/arm64/webview.apk仅134字节Git LFS指针，期望完整大小260835655，OID sha256=1d2f61832b2596b0046cb82cf3634609ea866098d097a83fac27c35272ac726a。其实际Git project是prebuilt/arm64目录，external/chromium-webview本身不是项目根。
- 已对该原始官方仓库执行git lfs pull --include=webview.apk --exclude=，文件实体取回且OID/size核验通过；通过out/siso_failed_commands.sh原样重跑失败manifest_check，实际退出0（日志logs/verify-webview-manifest.log）。没有关闭uses-library检查。
- 全源码小文件LFS扫描另只发现其他3种架构的WebView和Rust测试数据库指针；它们不是当前arm64 ROM输入，未无端下载。新增audit_prebuilt_apks.py对生产用APK做完整ZIP CRC/AndroidManifest检查及WebView LFS OID核验；39个均通过。libunwindstack/offline_files中的fake.apk经Android.bp确认是离线测试夹具，明确排除而不篡改它们。报告reports/prebuilt-apk-integrity.json。
- preflight_sheng.py已加入APK完整性门禁，防止今后再到整包中段才发现同类问题；sync_lineage.sh会在同步后按需取回arm64 WebView实体。平台Git HEAD未改变，已有BSP35项成功receipt和417+2实际模块输入指纹未变，故继续整包，未重复内核LTO或完整BSP验证。
- 新完整run_id=10c3d5e7c3484c139b1c9c289df9bf4d，20:09:14启动，父命令session52228，supervisor2268919、worker2268924；新的退出等待以本聊天最新工具session为准。旧等待55700已经报告失败；Windows旧入口8911也随上一完整run结束，不承担本次构建。当前仍无完成的ROM可交付。
- C盘20:09约104.59GiB可用。用户已取消空间清理，我方无后续缓存删除计划。全程保持24线程/80GiB swap/10GiB ccache和20GiB C盘保护。

## 20:23：Repo只读沙箱缓存修复，单目标实测通过后继续整包

- run10c3d5e7c3484c139b1c9c289df9bf4d于20:12:19退出，唯一失败product/etc/build-manifest.xml：repo在Siso只读视图里试图写/root/.repo_.gitconfig.json。日志已归档logs/failures/10c3d5e7c3484c139b1c9c289df9bf4d.log。
- 实际/root/.gitconfig不存在，而repo的GitConfig._ReadJson要求JSON缓存比原始配置文件新；配置文件缺失导致每次判定缓存失效并重写，即使预先生成JSON也无效。现仅在缺失时为该WSL构建用户建立空.gitconfig，不覆盖既有用户设置；preflight_sheng.py在沙箱外先生成repo manifest并准备缓存。未关闭构建沙箱。
- verify_build_manifest_target.sh只请求真正的build-manifest.xml目标，沿用build.lock和真实Siso沙箱，20:22已实测退出0、产出XML可解析；日志logs/verify-build-manifest-target.log。预检39个生产APK及BSP输入检查亦通过。
- 新完整run_id=69423c77af6647f28ec9a85324161559，20:22:56启动，父命令session71485，supervisor2334008/worker2334013，status=building。原生退出等待以最新工具session为准；旧55390属于已失败的run10c3，不再等它。已有整包编译结果全部继续复用，尚无完整ROM交付。

## 20:42：补齐4个相机旧C ABI调用，扩展为真实Soong厂商全目录检查

- 完整run69423c77af6647f28ec9a85324161559于20:29:22退出，唯一失败是camera.xiaomi.so的Soong ELF检查，缺少旧C ABI SetTaskProfiles。日志已存logs/failures/69423c77af6647f28ec9a85324161559.log。
- 官方hardware/lineage/compat/libprocessgroup/processgroup.cpp已有真正的兼容实现：C入口转发到当前libprocessgroup的对应C++接口。find_processgroup_compat.py实际扫描943个AArch64动态ELF，集中找出4个调用者：odm/lib64/hw/camera.xiaomi.so、odm/lib64/hw/com.qti.chi.override.so、odm/lib64/libchifeature2.so、odm/lib64/libmialgoengine.so。审计结果reports/processgroup-compat-audit.json与设备processgroup-compat.json。
- extract-files.py已给全部4项添加DT_NEEDED libprocessgroup_shim.so；C缓存原始固件不改。重新提取并安装vendor成功，生成的BP自动声明shim依赖；GSL头文件provider补充也再次正常保留。没有使用allow_undefined_symbols或关闭ELF检查。
- 审查Android17源码后确认RELEASE_SOONG_CHECK_ELF_FILES开启时，旧check-elf-files汇总没有覆盖所有Soong预编译检查。因此此前35个目标成功不能等同于全部原厂ELF都验证过。现新增真实存在的MODULES-IN-vendor-xiaomi-sheng目标，以-k0逐个覆盖厂商目录实际模块，整套验证变为36目标，集中收集错误；不再只靠旧汇总目标。
- 原成功receipt因设备/生成vendor配置变化已过期；已重新设置device-audit.pending，不能绕过它直接整包。第六次左右的当前集中验证run_id=45914d243d64486c928c6ec7d413dda2，20:39:59启动，父命令session21874，supervisor2428179/worker2428184。Android.bp改变后会重新生成Soong图。
- 有效自动衔接Windows watcher：session67693/PID55280，reports/validation-continuation-windows.json确认等待当前45914...；原生pidfd等待session40096。全36目标通过且receipt匹配才自动继续整包，失败则保留门禁。旧完整等待13113已失败结束，勿再等它。
- 20:40实际额度用79%，本轮真实重置仍为21:15:28；现有自动化应在21:20:28单次续作，UTC epoch已修正过，不能改回TZID/每天/20分钟。当前仍继续接管，不因计划定时而停下。没有可交付的完整ROM，仍不刷机。

## 21:16：6个厂商ELF错误已逐个原命令核验通过，新36项验证运行中

- run45914d243d64486c928c6ec7d413dda2于21:02:11结束，真实厂商目录检查一次集中找出6个失败：3个图像库AHardwareBuffer版本/直接依赖，libwrapper_dlengine缺liblog直接依赖，libcrussp引用原HAL公开ahal_log_lvl，c2.dolby.client引用旧HIDL WorkBundle objcpy。之前4个SetTaskProfiles相机库已过。
- 对3个图像库补libnativewindow依赖，并仅对已确认的稳定公开AHardwareBuffer API取消旧的LIBNATIVEWINDOW符号版本需求，绑定同一运行时默认导出；真实system libnativewindow实现仍有@@LIBNATIVEWINDOW，而新vendor LLNDK桩是无版本导出。没有删函数导入或关闭检查。修改保存在extract-files.py。
- libwrapper_dlengine补liblog；c2.dolby.client补已有官方libcodec2_shim，该仓库内WorkBundle.cpp是干净的官方tracked文件，真实转发旧签名到当前模板化BufferPoolSender接口，不是假实现。
- 当前CAF AudioCommon.h的ahal_log_lvl是各TU私有的32位0xf日志掩码，原Cirrus插件需旧公开数据符号。新增自己写的compat/AudioLogLevel.c和libsheng_audio_log_compat，导出相同位宽和相同ERR/WARN/INFO/DBG默认掩码；libcrussp显式依赖它。只恢复日志控制数据ABI，不改音频算法或用空硬件函数。
- verify_vendor_elf_fixes.py从真实失败日志取6条原始ELF检查命令，使用实际已编出的vendor依赖；新日志数据兼容库用相同pinned Clang真实编成AArch64共享库。6条全部实际返回0，报告reports/vendor-elf-fix-verification.json。该报告清楚标记Soong集成仍待验证，不能当作整套通过。内核模块CRC/vermagic保护始终保留。
- 新36项目验证run_id=b739ae1030804f689416c57739e7df04，21:15:31开始，父session50297，supervisor2512913/worker2512918。Android.bp/生成vendor变动后重新Soong分析；audit.pending仍保留。当前有效Windows自动衔接watcher session8107/PID54348，报告已确认等待b739...；原生pidfd等待session63627。旧40096和watcher67693属于已失败45914，不再复用。
- 21:20:28的额度重置单次兜底即将到时；当前一直接管，健康验证不重复开。先看实际event和最新checkpoint，若当前轮成功Windows watcher会先归档验证证据、校验receipt后自动开始完整ROM。仍无完整ROM产物，不刷机。
- 21:22再次只读核对调度数据库：next_run_nominal_at仍为1793884828000（北京时间21:20:28），说明UTC时区修复保留；调度器已把next_run_at顺延至1793884953087（21:22:33.087），last_run_at仍null、runs为空。本聊天当时仍连续接管，实际验证b739...健康运行；不能把该后台顺延误说成又设置错时区，也不未经证据断言具体调度原因。继续当前工作，不为等后台任务停下或开重复构建。

## 21:40：36项目集中验证全通过，已自动继续完整ROM构建

- b739ae1030804f689416c57739e7df04 于21:39:27成功，validation_passed=true、returncode=0、failed_targets为空；最后真实Siso构建7372步成功，整个验证23分34秒。6个ELF修复已通过Soong集成，不只是单独复验。内核/417+2模块ABI、厂商全目录、SELinux、VINTF及其余验证目标均通过，输入指纹已记录。
- Windows watcher按预期衔接Linux控制器，验证日志/receipt/模块ABI报告已归档到logs/validation-evidence/b739ae1030804f689416c57739e7df04/。新完整run_id=37065e97dbac48fe917ad5733179528c，21:39:29启动，supervisor2598370、worker2598429。勿重复启动。旧63627等待已退出，新的native waiter以最新工具session为准。
- 用户取消空间清理仍有效；21:38只读查询C盘约103.67GiB空余，没有重新清理。构建仍保持24线程、80GiB总swap、10GiB ccache与20GiB空间保护。完整ROM尚未构建/导出，不把验证成功当成ROM或真机启动成功。

## 21:50：首个完整LineageOS24.0 ROM编译及导出成功

- 完整run37065e97dbac48fe917ad5733179528c于21:49:16成功退出，returncode=0、succeeded=true、phase=exported。真实m bacon用时09:10，Siso本轮3319步成功；此前各轮中间结果已复用，不能把本轮时间说成全新源码冷编译耗时。
- 已导出到Windows工作区artifacts/lineage-24.0-20261105-UNOFFICIAL-sheng/。ROM zip1883238740字节，SHA256=76184f072b0b8c9a5144533a2ceb181ff664c8dacdc62a56f68ddf139f907ad9；7个镜像boot/vendor_boot/init_boot/recovery/dtbo/vbmeta/vbmeta_system齐全，另含平台source-manifest.xml、两个真实源码patch、sheng-build-configuration.tar.gz、SHA256SUMS与build-result.json。
- export_lineage.py已对OTA zip完整CRC、payload.bin存在性、417个原厂BSP模块ABI报告与模块清单精确对应做门禁。随后Windows独立读取所有12个SHA256SUMS项目，全部匹配，报告reports/exported-artifact-verification.json；不是仅对WSL源文件计算哈希。OTA元数据pre-device=sheng、AB、Android17/SDK37、2026-11-01安全补丁，官方LOS源码编译内核5.15.220-gf9ca2b71f672。
- 没有做真机启动测试或任何刷写，Dolby/触控/音频/显示等运行效果仍由用户测试确认。原厂E盘固件一直只读，未擅自再清理用户缓存。构建出口已有完整ROM，不再继续重复编译；本次单次兜底在交付时按要求删除。
- 自动化实际于21:41:33执行（last_run_at=1793886093370），本heartbeat就是那次续作；原时区修复有效。其过期单次rrule不能原样update（工具明确拒绝no future runs），在构建健康期间曾按最新真实重置2026-11-06 02:15:36加5分钟重排到02:20:36，已核实next_run_at=1793902836000。现在目标已完成，后续应删除sheng-lineageos而不是保留这次兜底。

## 22:15后续实机反馈：首版启动失败，Recovery r2待测试

- 用户反馈旧recovery临时启动报错，单刷recovery重启回fastboot，随后确认源码内核/DTBO相关启动镜像刷入也回fastboot。首版只有编译完成，不能称为可用ROM。旧产物保留原始文件/SHA，README已追加实机失败记录；完整情况及后续入口见reports/recovery-bringup-20261105.md。
- 用户提供https://github.com/peiyuesheng666/twrp_device_xiaomi_sheng，并授权参考LineageOS官方小米SM8550树；仅参考事实和配置布局，不直接套用他人实现/二进制。
- 原v4 recovery的kernel_size=0不适合fastboot boot；另发现vendor_boot116模块与335项recovery加载索引覆盖问题，源BoardConfig/prepare_stock_bsp.py已修正，但尚未重新编译主ROM。device-audit.pending重新建立，阻止旧receipt被用来盲目重复整包。
- 已自主打包自包含v2 Recovery r2，采用本机官方固件5.15.178内核/336原厂模块/原厂DTB+DTBO和我们已编出的Lineage24 Recovery用户空间。产物artifacts/recovery-sheng-lineage-24.0-r2/lineage-24.0-sheng-recovery-r2.img，100MiB，SHA25643c65078ab22ce7465298b488841e741913d975f38e118fbd36701138840f3b4。AVB实际签名/hash校验、所有嵌入组件解包回读、module加载索引/kmod dry-run、init rc/shell解析、Windows最终文件hash均通过；不是实机启动成功。附自身源配置包/详细报告。
- 下一步只测试r2的fastboot boot并收集完整错误或pstore，先定位/恢复Recovery，再处理源码内核实际失败。不要让用户继续盲刷原ROM或声称单刷配套文件就必定可用。原自动化已删除，不存在后台新整包构建。

## 22:49：r2仍失败，已自编USB串口诊断r3并启动电脑采集

- 用户实测r2仍在Recovery界面出现前重启回fastboot。用户明确要求自己做串口，不再把pstore当作现成可取节点。现有树只能称编译通过的移植初稿，不能称适配成功；已直接承认实际遗漏，原ROM/r2均不是可用版。
- 详细报告reports/recovery-serial-20261105.md。自写静态AArch64诊断/init在Android init之前记录逐模块加载结果、使用原厂已启用的ACM/configfs提供USB串口，保留8MiB日志缓冲，收到电脑GO后再exec原Lineage init。无远程shell/自动刷写。
- 原厂模块黑名单此前漏保留；r3恢复（包括llcc_perfmon）。另从匹配源码确认mtdoops_init在mtddev为空时明确返回EINVAL，r2缺此参数；r3加入mtdoops.mtddev=0，并将模块参数传给pre-init finit_module。具体实机失败链尚待日志，不将此单点检查冒充完整根因。
- 真正编出的AArch64静态程序在QEMU+LinuxPTY中完成494667字节完整传输与GO握手，无INTERP；随后r3镜像AVB签名/hash、内嵌原厂kernel/DTB/DTBO一致性及Windows独立SHA校验均通过。USB实机枚举/Recovery界面仍待测试，不再用这些电脑测试承诺能启动。
- 产物artifacts/recovery-sheng-lineage-24.0-r3-serial/lineage-24.0-sheng-recovery-r3-serial.img，100MiB，SHA2564367acd06b61b6d3699134865b622220411a81e9167ee40c95e867d3ce57f90a。含自身源包/报告/校验/采集启动器；只作临时诊断，不作正式Recovery刷入。
- Windows采集已实际运行：22:47:43开始，PID16088、session41137，reports/serial/capture-state.json记录waiting-for-sheng-usb-serial/bytes0。当前日志reports/serial/sheng-r3-20261105-224743.log。脚本识别VID1D6B/PID0104 COM口，只有先收到HOLD日志且保存前序日志后才发送GO；断线重连，120分钟后退出。重启入口会拒绝重复采集。此原生监视不消耗模型轮询额度，但不会凭空产生硬件信号或保证唤醒聊天。
- 下一步需要用户临时fastboot boot该r3，然后读真实串口日志。若没有USB枚举，普通USB线不能覆盖控制器初始化前故障，硬件UART需要真实板级接线/测试点。没有自动运行任何boot/flash/reboot命令；主ROM仍由device-audit.pending门禁阻止盲目重编，额度自动化仍已删除。

## 23:11：最新实测修正，源码220可启动；已抓到r3诊断交接错误并交付r4

- 用户最新明确重测源码内核可开机，系统显示5.15.220；先前“源码内核无法启动”的概括已撤回。尚未确认使用哪套Android用户空间，不能扩大成整包Lineage已启动。用户认为Recovery可能能启动但显示异常，黑屏有背光；以最新结果修正README/记录。
- USB串口已经在实机枚举COM6并实际传回日志，传输不再仅是QEMU测试。原collector16088捕获reports/serial/sheng-r3-20261105-224743.log。因r3自己的kmsg阶段标记未见，自动GO没触发，那个阶段还停在诊断前置，不能用其黑屏证明Recovery绘制失败。
- 验证旧PID后换collector47136/session20124，22:57:04通过既定串口GO命令放行，实际日志reports/serial/sheng-r3-20261105-225659.log显示Lineage first-stage mount(sysfs,/sys)失败EBUSY，InitFatalReboot signal6后重启。明确是我方诊断pre-init提前挂/sys而未交接释放所致，不是证明原内核/普通Recovery不工作。已向用户直接说明。
- 实际显示日志绑定默认Visionox R66451，与本平板不符。r3的直接模块加载只带打包时静态参数，遗漏bootloader在/proc/cmdline追加的运行时模块参数，可能让msm_drm丢失真实dsi_display0。原厂DTB与用户参考TWRP的DTB SHA完全一致，没有引入别人的DTB或猜一个面板硬编码。
- r4已修自有pre-init：交接前detach诊断/sys及/proc；按实际/proc/cmdline转发每个模块参数、保留引号并兼容连字符/下划线；自身阶段信息走独立pipe转串口，避免依赖未观测到的user-kmsg写入。参数解析回归和AArch64静态/QEMU/PTy494667字节/GO测试、AVB、Windows SHA校验都过，硬件仍待r4测试。
- r4产物artifacts/recovery-sheng-lineage-24.0-r4-serial/lineage-24.0-sheng-recovery-r4-serial.img，100MiB，SHA256f7387c1d24826cf86e64f6db35372cee752c09834362c8f48f88dd7b50cc76d9。完整报告reports/recovery-r4-20261105.md，源包/校验在产物目录。用户已经收到临时启动r4的链接与命令；不自动刷写设备。
- 当前collector为PID69332/session3050，23:08:31开始，默认等待原生HOLD握手（不再ContinueNow）。状态reports/serial/capture-state.json，日志reports/serial/sheng-r3-20261105-230831.log，23:10仍waiting-for-sheng-usb-serial/bytes0。文件前缀和USBserial仍保留r3以保持COM6分配；native新阶段记录是sheng-diag-r4。
- 下一步观察r4连接后日志，先确认sysfs交接错误消失及实际面板参数，再处理Recovery显示/输入。注意post-policy logger权限可能需依据实际AVC再补作用域有限的诊断服务；不要盲目禁用SELinux、继续换内核或说完整ROM已适配成功。

## 2026-11-06 00:25：Recovery已运行但实体屏花屏；开始r6高通显示后端实测

- r5实际临时启动成功，ADB root与Recovery服务均正常；内核仍是用于隔离显示问题的原厂5.15.178，不是源码220。用户已另外确认源码5.15.220可启动，完整Lineage ZIP仍未实测。
- 实际读取DRM framebuffer得到3048×2032正常Lineage Recovery菜单，reports/device/20261105-232505/fb-73.png；PPM SHA256=8a50a36837d701d5b4334f674dacfae036f5aef92f7c09c45bfc2841e6c21c53。实体屏却白屏/密集彩色条纹，dmesg含DSI underrun；不能仅据照片归咎GPU3D。
- 一次受控DPMS关/开恢复原On值，未解决。用户随后自行切回Fastboot。未刷分区、安装ROM或格式化数据；所有临时文件与替换计划限Recovery RAM。
- QTI后端首轮旧make变量未生效，已在装机前识别；改用recovery的typed Soong bool，实际编译run=2d8f1b686d6d4c8ba1084821b931c2a3于00:15:35成功。minui实际位于共享librecovery_ui.so，不能只换recovery主程序。新库SHA256=de6aa42386b584f8ab7d0373672d2f067a3091d8f6b2a877e58b25aa40e7ec7c，依赖库列表未变，见reports/qti-candidate.json。
- hotswap控制器15304因Windows到WSL路径转换正则错误在设备操作前退出，没有换库；错误已修，当前改用完整r6临时镜像。不得把其旧waiting状态当活进程。
- r6保留r5内核、DTB、DTBO、模块、cmdline，仅更新编译后的Recovery UI组件与诊断variant。AVB和组件解包校验、Windows独立SHA通过：14b129e555f29ae87a09f6432fb7341bdd410aab796fe331b46838a92678eafc；镜像artifacts/recovery-sheng-lineage-24.0-r6-qti/lineage-24.0-sheng-recovery-r6-qti.img。00:25:08启动autoboot控制器53984/session75285，仅fastboot boot，待实际日志与实体屏确认，未宣称修复。
- r5缺/dev/block/bootdevice别名，fstab旧路径导致BCB读取/挂载失败；此项还需修，不格式化用户数据。生成ro.debuggable=0来自Android17的ProductNotDebuggableInUserdebug逻辑，不能未经证据称为原厂属性污染；诊断镜像单独启用ADB root。
- 主整包仍有device-audit.pending，旧验证指纹已失效，禁止盲目重跑完整bacon；没有重复健康构建或删除缓存。
