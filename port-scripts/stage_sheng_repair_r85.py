#!/usr/bin/env python3
"""Isolate the r76 baseline and restore the verified shipping bypass control."""
from pathlib import Path
import difflib
import hashlib
import json
import shutil
import subprocess

workspace = Path(__file__).resolve().parents[1]
base_project = Path('/root/sheng-618-ipv6-release-project')
base_build = Path('/root/sheng-618-pen-release-build')
project = Path('/root/sheng-618-repair-r85-project')
build = Path('/root/sheng-618-repair-r85-build')
assert not project.exists() and not build.exists(), 'Preserve existing repair checkout'
baseline = workspace/'artifacts/sheng-6.18-ipv6-release-r76/boot.img'
sha = lambda data: hashlib.sha256(data).hexdigest()
assert sha(baseline.read_bytes()) == 'b5a85f166a4346b85e0ef264274e77d04d70c0adfdd87b432324e30c27ee8417'
shutil.copytree(base_project, project, symlinks=True,
                ignore=shutil.ignore_patterns('.git','dist','logs','__pycache__','*.pyc'))
subprocess.run(['cp','-a','--reflink=auto',str(base_build),str(build)],check=True)
for path in build.rglob('*'):
    if path.is_symlink():
        target = str(path.readlink())
        if target.startswith(str(base_build)+'/'):
            path.unlink()
            path.symlink_to(target.replace(str(base_build)+'/',str(build)+'/',1))
env = project/'scripts/project-env.sh'
env.write_text(env.read_text().replace(str(base_build),str(build))
    .replace('sheng-618-pen-release-build','sheng-618-repair-r85-build')
    .replace('TAG="${TAG:-ipv6-release-r76}"','TAG="${TAG:-repair-r85}"'))
relative = 'k618/soc/drivers/power/supply/qti_battery_charger.c'
path = build/relative
before = path.read_text()
assert sha(before.encode()) == 'aa8c41650da9b97715238bd5a4581f3d003245c990bc0c3aa3ccd347bafbe666'
after = before.replace('XM_PROP_CHARGING_SUSPEND_BATTERY = 220,',
                       'XM_PROP_CHARGING_SUSPEND_BATTERY = 219,')
anchor = 'static ssize_t fastchg_mode_show('
assert after.count(anchor) == 1
callbacks = '''/* Shipping sheng bypass control: property 219, independent of input suspend. */
static ssize_t charging_suspend_battery_show(const struct class *c,
        const struct class_attribute *attr, char *buf)
{
    struct battery_chg_dev *bcdev = container_of(c, struct battery_chg_dev,
                                               battery_class);
    struct psy_state *pst = &bcdev->psy_list[PSY_TYPE_XM];
    int rc;

    if (atomic_read(&bcdev->state) != PMIC_GLINK_STATE_UP ||
        (bcdev->debug_battery_detected && bcdev->block_tx))
        return -ENOTCONN;
    rc = read_property_id(bcdev, pst, XM_PROP_CHARGING_SUSPEND_BATTERY);
    if (rc < 0)
        return rc;
    if (atomic_read(&bcdev->state) != PMIC_GLINK_STATE_UP)
        return -ENOTCONN;
    return scnprintf(buf, PAGE_SIZE, "%u\\n",
        READ_ONCE(pst->prop[XM_PROP_CHARGING_SUSPEND_BATTERY]));
}

static ssize_t charging_suspend_battery_store(const struct class *c,
        const struct class_attribute *attr, const char *buf, size_t count)
{
    struct battery_chg_dev *bcdev = container_of(c, struct battery_chg_dev,
                                               battery_class);
    bool value;
    int rc;

    if (kstrtobool(buf, &value))
        return -EINVAL;
    if (atomic_read(&bcdev->state) != PMIC_GLINK_STATE_UP ||
        (bcdev->debug_battery_detected && bcdev->block_tx))
        return -ENOTCONN;
    rc = write_property_id(bcdev, &bcdev->psy_list[PSY_TYPE_XM],
                          XM_PROP_CHARGING_SUSPEND_BATTERY, value);
    if (rc < 0)
        return rc;
    if (atomic_read(&bcdev->state) != PMIC_GLINK_STATE_UP)
        return -ENOTCONN;
    return count;
}
static CLASS_ATTR_RW(charging_suspend_battery);

'''
after = after.replace(anchor,callbacks+anchor)
anchor = '\t&class_attr_input_suspend.attr,\n'
assert after.count(anchor) == 1
after = after.replace(anchor,anchor+'\t&class_attr_charging_suspend_battery.attr,\n')
path.write_text(after)
patch = project/'patches/sheng-repair-r85.patch'
patch.write_text(''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),
    fromfile='a/'+relative,tofile='b/'+relative)))
receipt = dict(revision='repair-r85',base='ipv6-release-r76',project=str(project),build=str(build),
    files={relative:dict(before=sha(before.encode()),after=sha(after.encode()))},
    patch='patches/'+patch.name,patch_sha256=sha(patch.read_bytes()),
    bypass_property_id=219,default_charging_writes_added=False,
    bypass_runtime_verified=False,pen_fixed=False,pps_fixed=False,flashed=False)
(project/'provenance/repair-r85.json').write_text(json.dumps(receipt,indent=2)+'\n')
# Inherited hash gates accept only the explicitly recorded downstream source hash.
for name in ('apply-charging-fix.py','apply-pen-release-fix.py'):
    p = project/'scripts'/name
    text = p.read_text()
    anchor = "states = set()"
    assert text.count(anchor) == 1
    text = text.replace(anchor,"repair_path = project / 'provenance/repair-r85.json'\n"
        "repair = json.loads(repair_path.read_text())['files'] if repair_path.exists() else {}\n"
        "def repaired(name, got):\n"
        "    return name in repair and got == repair[name]['after']\n"+anchor)
    if name == 'apply-charging-fix.py':
        text = text.replace("if got == hashes['after'] or (downstream and got == downstream['after']):",
            "if got == hashes['after'] or (downstream and got == downstream['after']) or repaired(name, got):")
        text = text.replace("assert got == hashes['after'] or (downstream and got == downstream['after']), name",
            "assert got == hashes['after'] or (downstream and got == downstream['after']) or repaired(name, got), name")
    else:
        text = text.replace("if got == hashes['after']:","if got == hashes['after'] or repaired(name, got):")
        text = text.replace("assert hashlib.sha256((root / name).read_bytes()).hexdigest() == hashes['after'], name",
            "got = hashlib.sha256((root / name).read_bytes()).hexdigest()\n"
            "    assert got == hashes['after'] or repaired(name, got), name")
    p.write_text(text)
(workspace/'reports/kernel618-repair-r85-stage.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps(receipt),flush=True)
