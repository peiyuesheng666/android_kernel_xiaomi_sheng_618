"""Generate revision-specific tools without modifying prior delivery records."""
from pathlib import Path
w=Path(__file__).resolve().parents[1]
scripts=w/'scripts'
for name in ['verify_sheng_repair_r86_btf.py','package_sheng_repair_r86.py','flash_sheng_repair_r86_wireless.py','finish_sheng_repair_r86_wireless.py','check_sheng_repair_r86_nodes.py','probe_sheng_bypass_r86.py']:
    text=(scripts/name).read_text().replace('r86','r87')
    text=text.replace('/root/sheng-618-repair-r87-build','/root/sheng-618-repair-r86-build')
    if name=='flash_sheng_repair_r86_wireless.py':
        text=text.replace("artifacts/sheng-6.18-qcom-walt-classic-r80/boot.img", "artifacts/sheng-6.18-repair-r86/boot.img")
        text=text.replace('ef96897939a4e8b0a6ab8675cc88e438180f249bd531f340c8b25c54bc416137','a2b1748a1ef9fe71bd9c4598f4985dd5e950785827f825c3de06d46d21dda2f0')
    if name=='package_sheng_repair_r86.py':
        start=text.index("intro='");end=text.index("\npath=project/'README.zh-CN.md'",start)
        text=text[:start]+'''intro='''+repr('''# sheng Linux 6.18.32 · repair r87

基于r76，保留r86的57个充电接口、旁路属性219与32 ms笔触滤波。
r86实机追踪确认batterysecret认证结束后写pd_verifed=0，旧版抑制规则阻止恢复。
r87自动模式下sysfs写0立即触发重新判断；verify_process非0期间优先原厂认证。
非零adapter_id与身份不明/小米SVID的>=100 W能力均保留原厂识别路径。
真实在线PPS、SNK_Ready、有效能力、双电池认证、Good健康且无input_suspend后立即写1。
首写没有固定等待；已接PPS的5秒freezable读取兜底监测固件回0，sysfs/通知即时触发。
已有1不重写；成功清零连续失败预算，连续失败最多3次；参数N可禁用自动写入。
不伪造90/120 W，不修改电流/温控；动画过渡仍需新内核实机验收。
无法明确区分身份的>=100 W第三方源仍保守保留认证流程，此边界未证明全部第三方覆盖。
57节点在r86实机全部存在且读取成功；旁路供电及r87笔休眠恢复尚需实测。
风驰继续暂停，不加载实验调度模块。

此项目复用r86绝对路径的可变构建缓存；r86原交付/源码归档保留。
最终源码由固定哈希基线缓存、既有补丁及patches/sheng-repair-r87.patch组合构成。
完整差异及文件哈希见provenance/repair-r85.json（revision=repair-r87）。

''')+text[end:]
    (scripts/name.replace('r86','r87')).write_text(text)

text=(scripts/'test_sheng_pps_auto_r86.py').read_text().replace('r86','r87').replace('/root/sheng-618-repair-r87-build','/root/sheng-618-repair-r86-build')
start=text.index('int main(void){');end=text.index("\n'''\nfolder=",start)
text=text[:start]+r'''int main(void){
    struct battery_chg_dev b;struct sheng_pps_policy p={0};
    struct sheng_pps_sample s={.online=true,.pps=true,.ready=true,.healthy=true,.authenticated=true,.svid=0x12d1,.apdo_watts=90,.power_watts=90};
    assert(sheng_pps_decide(&p,&s)==SHENG_PPS_UNLOCK);
    s.verifying=true;assert(sheng_pps_decide(&p,&s)==SHENG_PPS_BLOCKED);s.verifying=false;
    s.adapter_id=1;assert(sheng_pps_decide(&p,&s)==SHENG_PPS_NATIVE);s.adapter_id=0;
    p.attempts=3;s.online=false;assert(sheng_pps_decide(&p,&s)==SHENG_PPS_OFFLINE && !p.attempts);
    prime(&b);run(&b);assert(writes==1 && notifications==2 && last_delay==5*HZ && !b.sheng_pps.attempts);
    run(&b);assert(writes==1); /* existing one is monitored but never rewritten */
    /* Repeated firmware clears do not consume the successful-write budget. */
    for(int i=0;i<8;i++){b.psy_list[PSY_TYPE_XM].prop[XM_PROP_PD_VERIFED]=0;run(&b);}
    assert(writes==9 && !b.sheng_pps.attempts);
    /* Actual batterysecret sequence: verify1 -> verify0 -> sysfs0 -> immediate restore. */
    b.psy_list[PSY_TYPE_XM].prop[XM_PROP_VERIFY_PROCESS]=1;
    assert(pd_verifed_store(&b.battery_class,NULL,"0",1)==1 && last_delay==0);
    writes=0;run(&b);assert(!writes);
    b.psy_list[PSY_TYPE_XM].prop[XM_PROP_VERIFY_PROCESS]=0;
    assert(pd_verifed_store(&b.battery_class,NULL,"0",1)==1 && last_delay==0);
    writes=0;run(&b);assert(writes==1);
    /* Disabling automatic mode keeps a manual zero; no replug required. */
    sheng_pps_auto_verify=false;assert(pd_verifed_store(&b.battery_class,NULL,"0",1)==1);
    writes=0;reads=0;run(&b);assert(!writes && !reads);
    reset(&b);b.psy_list[PSY_TYPE_USB].prop[USB_ONLINE]=0;run(&b);assert(!writes && !scheduled && !b.sheng_pps.connected);
    reset(&b);b.psy_list[PSY_TYPE_USB].prop[USB_REAL_TYPE]=2;run(&b);assert(!writes && !scheduled);
    reset(&b);b.psy_list[PSY_TYPE_XM].prop[XM_PROP_PD_VERIFED]=1;run(&b);assert(!writes && reads==3);
    reset(&b);b.psy_list[PSY_TYPE_XM].prop[XM_PROP_ADAPTER_SVID]=0x2717;b.psy_list[PSY_TYPE_XM].prop[XM_PROP_ADAPTER_ID]=0xa819;run(&b);assert(!writes);
    reset(&b);b.psy_list[PSY_TYPE_XM].prop[XM_PROP_ADAPTER_SVID]=0x2717;b.psy_list[PSY_TYPE_XM].prop[XM_PROP_APDO_MAX]=90;run(&b);assert(writes==1); /* captured Huawei */
    for(int svid=0;svid<=1;svid++){
        reset(&b);b.psy_list[PSY_TYPE_XM].prop[XM_PROP_ADAPTER_SVID]=svid?0x2717:0;
        b.psy_list[PSY_TYPE_XM].prop[XM_PROP_APDO_MAX]=100;run(&b);assert(!writes);
        b.psy_list[PSY_TYPE_XM].prop[XM_PROP_APDO_MAX]=120;run(&b);assert(!writes);
        b.psy_list[PSY_TYPE_XM].prop[XM_PROP_PD_VERIFED]=1;run(&b);assert(!writes);
    }
    reset(&b);b.psy_list[PSY_TYPE_XM].prop[XM_PROP_CURRENT_STATE]=25;run(&b);assert(!writes);
    reset(&b);b.psy_list[PSY_TYPE_XM].prop[XM_PROP_VERIFY_PROCESS]=1;run(&b);assert(!writes);
    reset(&b);b.psy_list[PSY_TYPE_XM].prop[XM_PROP_ADAPTER_SVID]=0;b.psy_list[PSY_TYPE_XM].prop[XM_PROP_POWER_MAX]=100;run(&b);assert(!writes);
    reset(&b);b.psy_list[PSY_TYPE_XM].prop[XM_PROP_ADAPTER_SVID]=0x291a;b.psy_list[PSY_TYPE_XM].prop[XM_PROP_APDO_MAX]=140;run(&b);assert(writes==1);
    reset(&b);b.psy_list[PSY_TYPE_XM].prop[XM_PROP_APDO_MAX]=0;run(&b);assert(!writes);
    reset(&b);b.psy_list[PSY_TYPE_XM].prop[XM_PROP_SLAVE_AUTHENTIC]=0;run(&b);assert(!writes);
    reset(&b);b.psy_list[PSY_TYPE_XM].prop[XM_PROP_AUTHENTIC]=0;run(&b);assert(!writes);
    reset(&b);b.psy_list[PSY_TYPE_XM].prop[XM_PROP_BATTERY_ADAPT_POWER_MATCH]=0;run(&b);assert(!writes);
    reset(&b);b.psy_list[PSY_TYPE_BATTERY].prop[BATT_HEALTH]=2;run(&b);assert(!writes);
    reset(&b);b.psy_list[PSY_TYPE_XM].prop[XM_PROP_INPUT_SUSPEND]=1;run(&b);assert(!writes);
    prime(&b);drop_at=14;run(&b);assert(!writes && !notifications);
    prime(&b);native_at=14;run(&b);assert(!writes && !notifications);
    prime(&b);notify_at=14;run(&b);assert(!writes && !notifications && last_delay==0);
    prime(&b);disable_at=14;run(&b);assert(!writes && !notifications);
    prime(&b);unplug_on_write=1;run(&b);assert(writes==1 && !notifications);
    prime(&b);write_rc=-EIO;run(&b);run(&b);run(&b);run(&b);assert(writes==3 && b.sheng_pps.attempts==3 && !notifications);
    prime(&b);ack_one=0;run(&b);run(&b);run(&b);run(&b);assert(writes==3 && !notifications);
    reset(&b);remote_rc=-ETIMEDOUT;run(&b);run(&b);run(&b);assert(!writes && b.sheng_pps.attempts==3);
    reset(&b);b.state=0;run(&b);assert(!reads && !writes && !scheduled);
    reset(&b);b.debug_battery_detected=b.block_tx=true;run(&b);assert(!reads && !writes);
    reset(&b);b.sheng_pps_stopping=true;run(&b);sheng_pps_kick(&b);assert(!reads && !writes && !scheduled);
    prime(&b);b.sheng_pps.attempts=3;b.sheng_pps_reset=1;run(&b);assert(writes==1 && !b.sheng_pps.attempts);
    assert(pd_verifed_store(&b.battery_class,NULL,"bad",3)==-EINVAL);
    b.state=0;assert(pd_verifed_store(&b.battery_class,NULL,"1",1)==-ENOTCONN);
    puts("r87 production PPS policy/worker/store: batterysecret zero recovery, native100->120 priority, immediate events, verified monitoring, repeated clears, protection gates and bounded consecutive failures passed");
    return 0;
}'''+text[end:]
text=text.replace('prop[XM_PROP_APDO_MAX]=100;', 'prop[XM_PROP_APDO_MAX]=90;',1)
text=text.replace("'manual zero until detach'", "'batterysecret zero immediately rechecked; N preserves manual zero'")
text=text.replace("'3-attempt limit and readback failure'", "'3 consecutive failures; successful repeated clears reset budget'")
(scripts/'test_sheng_pps_auto_r87.py').write_text(text)
print('Derived r87 tools, production tests and updated package notes')
